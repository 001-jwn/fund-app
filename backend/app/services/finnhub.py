"""
fun(d) M1 — Finnhub REST client (offline-safe).

Adapted from the teammate client:
- Reads FINNHUB_API_KEY from the environment only (never hardcode).
- File TTL cache under backend/cache/finnhub/ (gitignored). Never writes
  prices, news, or logos back into the seed file.
- Throttles to stay under free-tier 60 calls/min and global 30 calls/sec.
- Does not call the live API unless an API key is set and live calls are
  allowed. The app allows live calls when a key is set, unless
  FUN_D_FINNHUB_LIVE is 0. Direct use of this class still defaults to
  dry-run unless FUN_D_FINNHUB_LIVE=1 or allow_live=True.

Quote cache is 5 minutes, news 45 minutes, profile 7 days.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

BASE_URL = "https://finnhub.io/api/v1"

# backend/app/services/finnhub.py -> backend/cache/finnhub
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "finnhub"

# Stay under 60/min: ~1.1s between calls ≈ 54/min. Also << 30/sec.
DEFAULT_MIN_INTERVAL_SEC = 1.1

# TTLs (seconds). Prices ~5 min, news 30–60 min, profile ~weekly.
TTL_QUOTE = 5 * 60
TTL_PROFILE = 7 * 24 * 60 * 60
TTL_NEWS = 45 * 60
TTL_EARNINGS = 7 * 24 * 60 * 60


@dataclass
class CacheEntry:
    data: Any
    fetched_at: float
    expires_at: float


class FinnhubClient:
    """Thin Finnhub REST helper with disk TTL cache + request throttle."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        min_interval_sec: float = DEFAULT_MIN_INTERVAL_SEC,
        allow_live: Optional[bool] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("FINNHUB_API_KEY", "").strip()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_sec = min_interval_sec
        self._last_request_at = 0.0
        if allow_live is None:
            # Opt-in for direct use, so import and tests never hit the network.
            allow_live = os.environ.get("FUN_D_FINNHUB_LIVE", "").strip() in {"1", "true", "TRUE", "yes"}
        self.allow_live = bool(allow_live)

    def get_quote(self, symbol: str) -> dict[str, Any]:
        """GET /quote → current_price (c), price_change_percent (dp)."""
        return self._get("quote", {"symbol": symbol.upper()}, ttl=TTL_QUOTE)

    def get_profile(self, symbol: str) -> dict[str, Any]:
        """GET /stock/profile2 → logo (logo). Company name stays from the seed."""
        return self._get("stock/profile2", {"symbol": symbol.upper()}, ttl=TTL_PROFILE)

    def get_company_news(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> list[Any]:
        """GET /company-news → list of articles (headline, summary, datetime)."""
        return self._get(
            "company-news",
            {"symbol": symbol.upper(), "from": from_date, "to": to_date},
            ttl=TTL_NEWS,
        )

    def get_earnings(self, symbol: str, limit: int = 4) -> list[Any]:
        """GET /stock/earnings → fallback only, when the seed has no quarter date."""
        return self._get(
            "stock/earnings",
            {"symbol": symbol.upper(), "limit": str(limit)},
            ttl=TTL_EARNINGS,
        )

    def card_live_fields(
        self,
        symbol: str,
        news_from: str,
        news_to: str,
        include_earnings: bool = False,
    ) -> dict[str, Any]:
        """
        Assemble live fields for one ticker.

        Missing key, dry-run, or a failed call leaves fields null.
        Does not invent prices, news, holder_count, or prose.
        Earnings (last_quarter_date) are fetched only when include_earnings
        is true — the seed date is preferred by the caller.
        """
        out: dict[str, Any] = {
            "ticker": symbol.upper(),
            "current_price": None,
            "price_change_percent": None,
            "logo_url": None,
            "latest_news_headline": None,
            "latest_news_summary": None,
            "latest_news_date": None,
            "last_quarter_date": None,
            "holder_count": None,  # never filled from Finnhub free tier
            "error": None,
        }
        if not self.api_key:
            out["error"] = "FINNHUB_API_KEY not set"
            return out
        if not self.allow_live:
            out["error"] = "live calls disabled (set FUN_D_FINNHUB_LIVE=1 to enable)"
            return out

        errors: list[str] = []

        quote = self._safe_get("quote", {"symbol": symbol.upper()}, TTL_QUOTE)
        if isinstance(quote, dict):
            price, pct = _price_from_quote(quote)
            out["current_price"] = price
            out["price_change_percent"] = pct
        elif quote is not None:
            errors.append(str(quote))

        profile = self._safe_get("stock/profile2", {"symbol": symbol.upper()}, TTL_PROFILE)
        if isinstance(profile, dict):
            logo = profile.get("logo") or None
            out["logo_url"] = logo if isinstance(logo, str) and logo.strip() else None
        elif profile is not None:
            errors.append(str(profile))

        news = self._safe_get(
            "company-news",
            {"symbol": symbol.upper(), "from": news_from, "to": news_to},
            TTL_NEWS,
        )
        if isinstance(news, list):
            headline, summary, news_date = _newest_news(news)
            out["latest_news_headline"] = headline
            out["latest_news_summary"] = summary
            out["latest_news_date"] = news_date
        elif news is not None:
            errors.append(str(news))

        if include_earnings:
            earnings = self._safe_get(
                "stock/earnings",
                {"symbol": symbol.upper(), "limit": "4"},
                TTL_EARNINGS,
            )
            if isinstance(earnings, list) and earnings:
                period = earnings[0].get("period") if isinstance(earnings[0], dict) else None
                if isinstance(period, str) and period.strip():
                    out["last_quarter_date"] = period.strip()
            elif earnings is not None and not isinstance(earnings, list):
                errors.append(str(earnings))

        if errors:
            out["error"] = "; ".join(errors)
        return out

    def _safe_get(self, endpoint: str, params: dict[str, str], ttl: int) -> Any:
        try:
            return self._get(endpoint, params, ttl)
        except Exception as exc:  # noqa: BLE001 — one failed call must not sink the card
            return exc

    def _cache_path(self, endpoint: str, params: dict[str, str]) -> Path:
        raw = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        safe_ep = endpoint.replace("/", "_")
        return self.cache_dir / f"{safe_ep}_{digest}.json"

    def _read_cache(self, path: Path) -> Optional[CacheEntry]:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = float(payload["expires_at"])
            if time.time() > expires_at:
                return None
            return CacheEntry(
                data=payload["data"],
                fetched_at=float(payload["fetched_at"]),
                expires_at=expires_at,
            )
        except (KeyError, ValueError, json.JSONDecodeError, OSError):
            return None

    def _write_cache(self, path: Path, data: Any, ttl: int) -> None:
        now = time.time()
        payload = {
            "fetched_at": now,
            "expires_at": now + ttl,
            "data": data,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.min_interval_sec:
            time.sleep(self.min_interval_sec - elapsed)

    def _get(self, endpoint: str, params: dict[str, str], ttl: int) -> Any:
        path = self._cache_path(endpoint, params)
        cached = self._read_cache(path)
        if cached is not None:
            return cached.data

        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY not set; cannot fetch " + endpoint)
        if not self.allow_live:
            raise RuntimeError(
                f"cache miss for {endpoint} and live calls disabled "
                "(set FUN_D_FINNHUB_LIVE=1 after exporting FINNHUB_API_KEY)"
            )

        return self._request_with_retry(endpoint, params, path, ttl)

    def _request_with_retry(
        self,
        endpoint: str,
        params: dict[str, str],
        cache_path: Path,
        ttl: int,
        max_retries: int = 4,
    ) -> Any:
        query = dict(params)
        # Token goes in a header, not the URL, so it does not land in logs.
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(query)}"
        backoff = 2.0

        for attempt in range(max_retries + 1):
            self._throttle()
            req = urllib.request.Request(
                url,
                headers={
                    "X-Finnhub-Token": self.api_key,
                    "User-Agent": "fun(d)-m1/0.1 (personal research)",
                },
                method="GET",
            )
            try:
                self._last_request_at = time.time()
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                self._write_cache(cache_path, data, ttl)
                return data
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < max_retries:
                    retry_after = err.headers.get("Retry-After")
                    sleep_for = float(retry_after) if retry_after and str(retry_after).isdigit() else backoff
                    time.sleep(sleep_for)
                    backoff = min(backoff * 2, 30.0)
                    continue
                raise RuntimeError(f"Finnhub HTTP {err.code} for {endpoint}: {err.reason}") from err
            except urllib.error.URLError as err:
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
                raise RuntimeError(f"Finnhub network error for {endpoint}: {err}") from err

        raise RuntimeError(f"Finnhub request failed after retries: {endpoint}")


def _price_from_quote(quote: dict[str, Any]) -> tuple[float | None, float | None]:
    """Finnhub uses 0 for 'no price'. Do not turn that into a fake price."""
    raw = quote.get("c")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        return None, None
    pct_raw = quote.get("dp")
    pct = float(pct_raw) if isinstance(pct_raw, (int, float)) and not isinstance(pct_raw, bool) else None
    return float(raw), pct


def _newest_news(articles: list[Any]) -> tuple[str | None, str | None, str | None]:
    usable = [item for item in articles if isinstance(item, dict)]
    if not usable:
        return None, None, None
    usable.sort(key=lambda item: item.get("datetime") or 0, reverse=True)
    newest = usable[0]
    headline = newest.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        return None, None, None
    summary = newest.get("summary")
    summary_text = summary.strip() if isinstance(summary, str) and summary.strip() else None
    dt = newest.get("datetime")
    news_date = time.strftime("%Y-%m-%d", time.gmtime(dt)) if isinstance(dt, (int, float)) and not isinstance(dt, bool) else None
    return headline.strip(), summary_text, news_date
