"""Finnhub client stays quiet without a key and never invents prices."""

from __future__ import annotations

from pathlib import Path

from app.services.finnhub import DEFAULT_CACHE_DIR, FinnhubClient


def test_no_key_returns_nulls(tmp_path):
    client = FinnhubClient(api_key="", allow_live=False, cache_dir=tmp_path)
    fields = client.card_live_fields("MSFT", "2026-10-01", "2026-11-03")
    assert fields["current_price"] is None
    assert fields["price_change_percent"] is None
    assert fields["latest_news_headline"] is None
    assert fields["logo_url"] is None
    assert fields["holder_count"] is None
    assert fields["last_quarter_date"] is None
    assert "FINNHUB_API_KEY" in (fields["error"] or "")


def test_zero_quote_and_empty_news_are_unavailable(tmp_path):
    client = FinnhubClient(api_key="dummy", allow_live=True, cache_dir=tmp_path)
    calls = []

    def fake_get(endpoint, params, ttl):
        calls.append(endpoint)
        if endpoint == "quote":
            return {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0}
        if endpoint == "stock/profile2":
            return {"name": "Should Not Replace Seed", "logo": ""}
        if endpoint == "company-news":
            return [{"headline": "   ", "summary": "nope", "datetime": 1}]
        raise AssertionError(f"unexpected endpoint {endpoint}")

    client._get = fake_get  # type: ignore[method-assign]
    fields = client.card_live_fields("MSFT", "2026-10-01", "2026-11-03", include_earnings=False)
    assert fields["current_price"] is None
    assert fields["price_change_percent"] is None
    assert fields["logo_url"] is None
    assert fields["latest_news_headline"] is None
    assert "stock/earnings" not in calls


def test_news_is_sorted_and_a_failed_call_does_not_wipe_other_fields(tmp_path):
    client = FinnhubClient(api_key="dummy", allow_live=True, cache_dir=tmp_path)

    def fake_get(endpoint, params, ttl):
        if endpoint == "quote":
            raise RuntimeError("quote failed")
        if endpoint == "stock/profile2":
            return {"logo": "https://example.com/logo.png"}
        if endpoint == "company-news":
            return [
                {"headline": "Older", "summary": "Old summary", "datetime": 100},
                {"headline": "Newer", "summary": "New summary", "datetime": 500},
            ]
        raise AssertionError(endpoint)

    client._get = fake_get  # type: ignore[method-assign]
    fields = client.card_live_fields("SPOT", "2026-10-01", "2026-11-03")
    assert fields["current_price"] is None
    assert fields["logo_url"] == "https://example.com/logo.png"
    assert fields["latest_news_headline"] == "Newer"
    assert fields["latest_news_summary"] == "New summary"
    assert fields["latest_news_date"] == "1970-01-01"
    assert fields["holder_count"] is None
    assert fields["error"]


def test_cache_directory_is_ignored_by_git():
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "cache/" in gitignore
    assert "live-check" in gitignore
    assert "live-results" in gitignore
    assert ".env" in gitignore
    assert "*.db" in gitignore
    assert "__pycache__" in gitignore
    assert "node_modules" in gitignore
    assert DEFAULT_CACHE_DIR.as_posix().endswith("backend/cache/finnhub")
    relative = DEFAULT_CACHE_DIR.relative_to(repo_root).as_posix()
    assert relative.startswith("backend/cache/")
