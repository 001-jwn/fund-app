"""For-you digest. Prices and headlines here are fixtures, not market data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.catalysts import NEW_YORK
from app.services.digest import DIGEST_TEMPLATES, build_digest

NOW = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)  # Thu Nov 5, 10:00 p.m. ET
QUIET = (
    "Quiet one: no price moves of 2% or more and no new headlines "
    "for your liked stocks in the last day."
)
ADVICE = (
    "buy",
    "sell",
    "hold",
    "soared",
    "crashed",
    "plunged",
    "skyrocketed",
    "tanked",
    "huge",
    "today",
    "tomorrow",
    "yesterday",
    "big move",
    "time to",
    "should you",
    "don't miss",
)


def _companies(*tickers):
    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    found = []
    for ticker in tickers:
        company = session.get(Company, ticker)
        assert company is not None
        found.append(company)
    return session, found


def _quote(company, when: datetime, price: float, pct: float):
    company.current_price = price
    company.price_change_percent = pct
    company.latest_quote_at = when.replace(tzinfo=None)


def _news(company, when: datetime, headline: str, source: str | None = "Example Wire"):
    company.latest_news_headline = headline
    company.latest_news_unix = when.timestamp()
    company.latest_news_source = source
    # Stored UTC calendar day, on purpose different from the New York date.
    company.latest_news_date = "2026-11-06"


def _digest(companies, now=NOW, has_likes=True):
    return build_digest(companies, now, has_likes=has_likes)


def _assert_plain(line: str):
    lowered = line.lower()
    for word in ADVICE:
        assert word not in lowered


def test_move_threshold_and_quote_window(client):
    session, (nvda,) = _companies("NVDA")
    recent = NOW - timedelta(hours=1)
    _quote(nvda, recent, 10, 1.99)
    assert _digest([nvda])["items"] == []
    assert _digest([nvda])["empty_line"] == QUIET

    # 1.96 formats as 2.0, but the gate uses the raw value, so it stays out.
    assert f"{abs(1.96):.1f}" == "2.0"
    _quote(nvda, recent, 10, 1.96)
    assert _digest([nvda])["items"] == []

    _quote(nvda, recent, 10, 2.0)
    item = _digest([nvda])["items"][0]
    assert item["ticker"] == "NVDA"
    assert item["short_name"] == "NVIDIA"
    assert item["line"] == "NVIDIA is up 2.0% (as of Nov 5), at US$10.00."
    _assert_plain(item["line"])

    _quote(nvda, recent, 10, -2.0)
    assert _digest([nvda])["items"][0]["line"] == (
        "NVIDIA is down 2.0% (as of Nov 5), at US$10.00."
    )

    _quote(nvda, NOW - timedelta(hours=24), 10, 3)
    assert _digest([nvda])["items"] == []
    _quote(nvda, NOW - timedelta(hours=24) + timedelta(seconds=1), 10, 3)
    assert _digest([nvda])["items"][0]["line"].startswith("NVIDIA is up 3.0%")

    _quote(nvda, NOW + timedelta(minutes=10), 10, 3)
    assert _digest([nvda])["items"] == []
    nvda.current_price = float("inf")
    nvda.price_change_percent = 3
    nvda.latest_quote_at = recent.replace(tzinfo=None)
    assert _digest([nvda])["items"] == []
    nvda.current_price = 10
    nvda.price_change_percent = float("nan")
    assert _digest([nvda])["items"] == []
    nvda.price_change_percent = 3
    nvda.latest_quote_at = None
    assert _digest([nvda])["items"] == []
    session.close()


def test_news_window_uses_the_new_york_date_and_quotes(client):
    from app.services import catalysts, digest as digest_mod

    assert digest_mod._single_quotes is catalysts._single_quotes
    session, (nvda,) = _companies("NVDA")
    # 02:00 UTC on Nov 6 is 21:00 ET on Nov 5. The stored UTC day is Nov 6.
    published = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)
    _news(nvda, published, 'NVIDIA earnings say "hello" and \u201cgoodbye\u201d')
    item = _digest([nvda])["items"][0]
    assert item["line"] == (
        "In the news for NVIDIA: \"NVIDIA earnings say 'hello' and 'goodbye'\" "
        "(Example Wire, Nov 5)."
    )
    assert "Nov 6" not in item["line"]
    _assert_plain(item["line"])

    nvda.latest_news_source = "  "
    no_source = _digest([nvda])["items"][0]["line"]
    assert no_source == (
        "In the news for NVIDIA: \"NVIDIA earnings say 'hello' and 'goodbye'\" (Nov 5)."
    )

    nvda.latest_news_source = "Example Wire"
    nvda.latest_news_unix = (NOW - timedelta(hours=24)).timestamp()
    assert _digest([nvda])["items"] == []
    nvda.latest_news_unix = (NOW - timedelta(hours=24) + timedelta(seconds=1)).timestamp()
    assert _digest([nvda])["items"]

    nvda.latest_news_unix = (NOW + timedelta(minutes=10)).timestamp()
    assert _digest([nvda])["items"] == []
    nvda.latest_news_headline = "__no_recent_company_news__"
    nvda.latest_news_unix = published.timestamp()
    assert _digest([nvda])["items"] == []
    session.close()


def test_combined_line_order_and_cap(client):
    session, companies = _companies("NVDA", "AMD", "SONY", "MSFT", "RBLX", "TTWO", "AAPL")
    recent = NOW - timedelta(hours=2)
    older = NOW - timedelta(hours=5)
    moves = {
        "NVDA": 3.0,
        "AMD": 5.0,
        "SONY": 2.0,
        "MSFT": 4.0,
        "RBLX": 6.0,
        "TTWO": 2.5,
    }
    for company in companies:
        if company.ticker == "AAPL":
            _news(company, recent, "Apple earnings are out")
            continue
        _quote(company, recent, 20, moves[company.ticker])
    # Same move as AMD would tie; SONY is news-only after we clear its quote below.
    sony = next(company for company in companies if company.ticker == "SONY")
    sony.current_price = None
    _news(sony, recent, "Sony earnings are out", source=None)
    aapl = next(company for company in companies if company.ticker == "AAPL")
    _news(aapl, older, "Apple results are out", source="Wire")

    nvda = next(company for company in companies if company.ticker == "NVDA")
    _news(nvda, recent, "NVIDIA guidance stays steady", source="Wire")

    digest = _digest(companies)
    tickers = [item["ticker"] for item in digest["items"]]
    # Price moves 6, 5, 4, 3, 2.5 fill the cap. SONY and AAPL are news-only and drop off.
    assert tickers == ["RBLX", "AMD", "MSFT", "NVDA", "TTWO"]
    assert len(digest["items"]) == 5
    combined = next(item for item in digest["items"] if item["ticker"] == "NVDA")
    assert combined["line"] == (
        "NVIDIA is up 3.0% (as of Nov 5), at US$20.00. "
        'In the news: "NVIDIA guidance stays steady" (Wire, Nov 5).'
    )
    assert "In the news for" not in combined["line"]
    assert digest["empty_line"] is None
    for item in digest["items"]:
        _assert_plain(item["line"])

    # Without the larger moves, news-only items sort newest first, then ticker.
    news_only = _digest([sony, aapl])
    assert [item["ticker"] for item in news_only["items"]] == ["SONY", "AAPL"]
    assert news_only["items"][0]["line"] == (
        'In the news for Sony: "Sony earnings are out" (Nov 5).'
    )
    session.close()


def test_missing_parts_are_not_counted(client):
    session, (nvda,) = _companies("NVDA")
    recent = NOW - timedelta(hours=1)
    _quote(nvda, recent, 10, 4)
    nvda.short_name = " "
    nvda.company_name = " "
    assert _digest([nvda])["items"] == []
    nvda.short_name = "NVIDIA"
    nvda.company_name = "NVIDIA Corporation"
    nvda.current_price = None
    nvda.latest_news_headline = "NVIDIA earnings are out"
    nvda.latest_news_unix = None
    assert _digest([nvda])["items"] == []
    session.close()


def test_updates_digest_shape_excludes_unliked_and_does_not_call_finnhub(client, monkeypatch):
    # GET /updates asks the digest for the real clock. This fixture's news
    # instant is 2026-11-06 02:00 UTC (21:00 ET on Nov 5). Pin both this
    # test's clock and the digest clock to an hour later so that headline
    # stays inside the rolling day, on any date the suite is run.
    frozen = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return frozen.replace(tzinfo=None)
            return frozen.astimezone(tz)

    monkeypatch.setattr(f"{__name__}.datetime", _FrozenDateTime)

    def _frozen_as_utc(now=None):
        if now is None:
            return frozen
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    monkeypatch.setattr("app.services.digest._as_utc", _frozen_as_utc)

    calls = []

    def boom(*_args, **_kwargs):
        calls.append("finnhub")
        raise AssertionError("Finnhub was called from GET /updates")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.finnhub.urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_quote", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_company_news", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_earnings_calendar", boom)

    missing = client.get("/updates", params={"user_id": "nobody"})
    assert missing.status_code == 404

    empty_user = client.post("/onboarding", json={"interests": ["gaming"]})
    user_id = empty_user.json()["user_id"]
    nobody_liked = client.get("/updates", params={"user_id": user_id}).json()
    assert nobody_liked["updates"] == []
    assert nobody_liked["alerts"] == []
    assert nobody_liked["unseen_count"] == 0
    assert nobody_liked["digest"]["items"] == []
    assert nobody_liked["digest"]["empty_line"] is None
    assert nobody_liked["digest"]["header"].startswith("For you, ")
    assert nobody_liked["digest"]["date"] == datetime.now(NEW_YORK).date().isoformat()
    assert "intro" not in nobody_liked["digest"]
    assert "more_count" not in nobody_liked["digest"]
    assert "more_line" not in nobody_liked["digest"]

    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200
    quiet = client.get("/updates", params={"user_id": user_id}).json()
    assert quiet["digest"]["items"] == []
    assert quiet["digest"]["empty_line"] == QUIET
    assert quiet["updates"] == []

    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    nvda = session.get(Company, "NVDA")
    amd = session.get(Company, "AMD")
    published = datetime.now(timezone.utc) - timedelta(hours=1)
    nvda.current_price = 210.5
    nvda.price_change_percent = 2.5
    nvda.latest_quote_at = published.replace(tzinfo=None)
    nvda.latest_news_headline = "NVIDIA earnings are out"
    nvda.latest_news_summary = "A long enough summary of the earnings story."
    nvda.latest_news_unix = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc).timestamp()
    nvda.latest_news_date = "2026-11-06"
    nvda.latest_news_source = "Example Wire"
    amd.current_price = 99
    amd.price_change_percent = 9
    amd.latest_quote_at = published.replace(tzinfo=None)
    session.commit()
    session.close()

    body = client.get("/updates", params={"user_id": user_id}).json()
    assert [item["ticker"] for item in body["digest"]["items"]] == ["NVDA"]
    assert "AMD" not in {item["ticker"] for item in body["digest"]["items"]}
    assert body["digest"]["empty_line"] is None
    news_lines = [
        line for item in body["updates"] if item["ticker"] == "NVDA" for line in item["lines"]
    ]
    assert any("Nov 6" in line for line in news_lines)
    assert all("Nov 6" not in item["line"] or "as of" in item["line"] for item in body["digest"]["items"])
    digest_line = body["digest"]["items"][0]["line"]
    assert "Nov 5" in digest_line
    assert "(Example Wire, Nov 5)." in digest_line
    assert "Nov 6" not in digest_line
    assert "Jan 15" not in digest_line
    assert set(body) >= {"updates", "alerts", "unseen_count", "digest"}
    assert calls == []
