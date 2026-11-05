"""GET /updates reads the cache only. Numbers below are fixtures, not market data."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

from fastapi.testclient import TestClient

# 2026-11-04 04:30 UTC is 23:30 the previous evening in New York (EST, UTC-5).
QUOTE_BEFORE_MIDNIGHT = datetime(2026, 11, 4, 4, 30)
# 2026-11-04 05:30 UTC is 00:30 the same calendar day in New York.
QUOTE_AFTER_MIDNIGHT = datetime(2026, 11, 4, 5, 30)

OLD_COMPANIES = """
CREATE TABLE companies (
    ticker VARCHAR(32) NOT NULL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    short_name TEXT,
    short_description TEXT,
    current_price FLOAT,
    price_change_percent FLOAT,
    holder_count INTEGER,
    latest_news_headline TEXT,
    latest_news_summary TEXT,
    latest_news_date VARCHAR(32),
    quarterly_summary TEXT,
    last_quarter_date VARCHAR(32),
    logo_url TEXT,
    status VARCHAR(16),
    data_updated_at DATETIME
)
"""


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _updates(client, user_id):
    response = client.get("/updates", params={"user_id": user_id})
    assert response.status_code == 200, response.text
    return response.json()["updates"]


def _matches(client, user_id):
    response = client.get("/matches", params={"user_id": user_id})
    assert response.status_code == 200, response.text
    return [item["ticker"] for item in response.json()["matches"]]


def _set_company(ticker, **fields):
    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    company = session.get(Company, ticker)
    assert company is not None
    for key, value in fields.items():
        setattr(company, key, value)
    session.commit()
    session.close()


def _column_names(db_file):
    conn = sqlite3.connect(db_file)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(companies)")]
    finally:
        conn.close()


def test_unknown_user_and_no_likes(client):
    missing = client.get("/updates", params={"user_id": "nobody"})
    assert missing.status_code == 404

    user_id = _onboard(client, ["gaming"])
    assert _updates(client, user_id) == []


def test_updates_follow_matches_and_skip_tickers_with_no_cache(client):
    _set_company(
        "AMD",
        current_price=50.0,
        price_change_percent=1.26,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
    )
    _set_company(
        "SONY",
        current_price=100.0,
        price_change_percent=-2.04,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
    )
    # AAPL is not liked. A cached quote must not put it in Updates.
    _set_company(
        "AAPL",
        current_price=180.0,
        price_change_percent=1.0,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
    )

    user_id = _onboard(client, ["gaming", "music"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "SONY"}).status_code == 200
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    assert client.post("/like", json={"user_id": user_id, "ticker": "AMD"}).status_code == 200

    # NVDA is liked and has no cached quote or news, so it is left out.
    # Newest like first, matching /matches: AMD, NVDA, SONY → AMD, SONY.
    assert _matches(client, user_id) == ["AMD", "NVDA", "SONY"]
    updates = _updates(client, user_id)
    assert [item["ticker"] for item in updates] == ["AMD", "SONY"]
    assert "AAPL" not in {item["ticker"] for item in updates}
    assert updates[0]["lines"] == ["AMD is up 1.3% (as of Nov 3), at US$50.00."]
    assert updates[0]["news_url"] is None
    assert updates[1]["lines"] == ["Sony is down 2.0% (as of Nov 3), at US$100.00."]


def test_price_direction_uses_rounded_percent_and_new_york_date(client):
    user_id = _onboard(client, ["gaming"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200

    _set_company(
        "NVDA",
        current_price=210.5,
        price_change_percent=1.26,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
    )
    up = _updates(client, user_id)
    assert up == [{
        "ticker": "NVDA",
        "lines": ["NVIDIA is up 1.3% (as of Nov 3), at US$210.50."],
        "news_url": None,
    }]

    _set_company("NVDA", price_change_percent=-2.04, current_price=100)
    down = _updates(client, user_id)
    assert down[0]["lines"] == ["NVIDIA is down 2.0% (as of Nov 3), at US$100.00."]

    _set_company("NVDA", price_change_percent=0.04)
    flat_up = _updates(client, user_id)
    assert flat_up[0]["lines"] == ["NVIDIA is about flat (as of Nov 3), at US$100.00."]

    _set_company("NVDA", price_change_percent=-0.04)
    flat_down = _updates(client, user_id)
    assert flat_down[0]["lines"] == ["NVIDIA is about flat (as of Nov 3), at US$100.00."]

    _set_company("NVDA", latest_quote_at=QUOTE_AFTER_MIDNIGHT, price_change_percent=1.26, current_price=210.5)
    later = _updates(client, user_id)
    assert later[0]["lines"] == ["NVIDIA is up 1.3% (as of Nov 4), at US$210.50."]
    assert "today" not in later[0]["lines"][0].lower()
    assert "1969" not in later[0]["lines"][0]


def test_incomplete_quote_or_news_is_omitted(client):
    from app.services.news import NO_RECENT_NEWS_MESSAGE, NO_RECENT_NEWS_SENTINEL

    user_id = _onboard(client, ["gaming"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    _set_company(
        "NVDA",
        short_name="   ",
        current_price=210.5,
        price_change_percent=1.26,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
        latest_news_headline="NVIDIA ships a new chip",
        latest_news_date="2026-11-03",
        latest_news_source="Example Wire",
        latest_news_url="https://example.com/nvda-news",
    )
    both = _updates(client, user_id)[0]
    assert both["lines"] == [
        "NVIDIA Corporation is up 1.3% (as of Nov 3), at US$210.50.",
        'In the news for NVIDIA Corporation: "NVIDIA ships a new chip" (Example Wire, Nov 3).',
    ]
    assert both["news_url"] == "https://example.com/nvda-news"

    _set_company("NVDA", short_name="NVIDIA", latest_news_source="  ")
    no_source = _updates(client, user_id)[0]
    assert no_source["lines"][1] == (
        'In the news for NVIDIA: "NVIDIA ships a new chip" (Nov 3).'
    )
    assert no_source["news_url"] == "https://example.com/nvda-news"

    _set_company("NVDA", latest_news_source="Example Wire", latest_news_url="  ")
    no_url = _updates(client, user_id)[0]
    assert "Example Wire" in no_url["lines"][1]
    assert no_url["news_url"] is None

    _set_company("NVDA", latest_news_date=None, latest_news_url="https://example.com/nvda-news")
    no_date = _updates(client, user_id)[0]
    assert len(no_date["lines"]) == 1
    assert no_date["lines"][0].startswith("NVIDIA is up")
    assert no_date["news_url"] is None

    _set_company(
        "NVDA",
        latest_news_headline=NO_RECENT_NEWS_SENTINEL,
        latest_news_date="2026-11-03",
        latest_news_source="Example Wire",
        latest_news_url="https://example.com/nvda-news",
    )
    sentinel = _updates(client, user_id)[0]
    assert sentinel["lines"] == ["NVIDIA is up 1.3% (as of Nov 3), at US$210.50."]
    assert sentinel["news_url"] is None
    assert NO_RECENT_NEWS_MESSAGE not in sentinel["lines"][0]

    _set_company("NVDA", latest_news_headline=NO_RECENT_NEWS_MESSAGE)
    message = _updates(client, user_id)[0]
    assert message["news_url"] is None
    assert len(message["lines"]) == 1

    _set_company("NVDA", current_price=0, latest_quote_at=datetime(1969, 12, 31, 19, 0))
    zero_price = _updates(client, user_id)
    assert zero_price == []

    _set_company(
        "NVDA",
        current_price=210.5,
        price_change_percent=None,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
        latest_news_headline="NVIDIA ships a new chip",
        latest_news_date="2026-11-03",
        latest_news_source="Example Wire",
        latest_news_url="https://example.com/nvda-news",
    )
    missing_pct = _updates(client, user_id)[0]
    assert missing_pct["lines"] == [
        'In the news for NVIDIA: "NVIDIA ships a new chip" (Example Wire, Nov 3).'
    ]
    assert "US$" not in missing_pct["lines"][0]

    _set_company("NVDA", price_change_percent=1.26, latest_quote_at=None)
    missing_time = _updates(client, user_id)[0]
    assert missing_time["lines"] == [
        'In the news for NVIDIA: "NVIDIA ships a new chip" (Example Wire, Nov 3).'
    ]

    _set_company("NVDA", current_price=None, latest_quote_at=QUOTE_BEFORE_MIDNIGHT)
    missing_price = _updates(client, user_id)[0]
    assert "US$" not in missing_price["lines"][0]

    _set_company(
        "NVDA",
        current_price=None,
        price_change_percent=None,
        latest_quote_at=None,
        latest_news_headline=None,
        latest_news_date=None,
        latest_news_source=None,
        latest_news_url=None,
    )
    assert _updates(client, user_id) == []


def test_updates_does_not_call_finnhub_when_the_cache_is_old(client, monkeypatch):
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("Finnhub was called from /updates")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.finnhub.urllib.request.urlopen", boom)

    user_id = _onboard(client, ["gaming"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    _set_company(
        "NVDA",
        current_price=210.5,
        price_change_percent=1.26,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
        data_updated_at=datetime(2020, 1, 1, 0, 0),
    )
    updates = _updates(client, user_id)
    assert updates[0]["lines"] == ["NVIDIA is up 1.3% (as of Nov 3), at US$210.50."]
    assert calls == []


def test_refresh_persists_quote_time_source_and_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    quote_stamp = int(QUOTE_BEFORE_MIDNIGHT.replace(tzinfo=timezone.utc).timestamp())

    def fake_quote(_self, symbol):
        assert symbol == "NVDA"
        return {"c": 210.5, "dp": 1.26, "t": quote_stamp}

    def fake_news(_self, symbol, _news_from, _news_to):
        return [
            {
                "headline": "NVIDIA ships a new chip",
                "summary": "A short summary of the news.",
                "datetime": 1793577600,
                "source": "Example Wire",
                "url": "https://example.com/nvda-news",
            }
        ]

    def fake_profile(_self, symbol):
        return {"logo": "https://example.com/nvda.png"}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    live_mod.refresh_passes(["NVDA"])

    from app.db import SessionLocal
    from app.models import Company
    from app.seed.load_seed import load_seed

    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    assert stored is not None
    assert stored.current_price == 210.5
    assert stored.price_change_percent == 1.26
    assert stored.latest_quote_at == QUOTE_BEFORE_MIDNIGHT
    assert stored.latest_news_headline == "NVIDIA ships a new chip"
    assert stored.latest_news_date == "2026-11-02"
    assert stored.latest_news_source == "Example Wire"
    assert stored.latest_news_url == "https://example.com/nvda-news"
    assert stored.holder_count is None
    session.close()

    # A later seed load must not wipe the cached quote time or the news link.
    assert load_seed() == 31
    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    assert stored.latest_quote_at == QUOTE_BEFORE_MIDNIGHT
    assert stored.latest_news_source == "Example Wire"
    assert stored.latest_news_url == "https://example.com/nvda-news"
    assert stored.current_price == 210.5
    session.close()

    def unavailable_quote(_self, symbol):
        return {"c": 15.0, "dp": 1.0, "t": 0}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", unavailable_quote)
    live_mod._client = None
    live_mod.refresh_passes(["NVDA"])
    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    # t == 0 is not a quote. Price, change, and timestamp stay together.
    assert stored.current_price == 210.5
    assert stored.price_change_percent == 1.26
    assert stored.latest_quote_at == QUOTE_BEFORE_MIDNIGHT
    session.close()

    def zero_price(_self, symbol):
        return {"c": 0, "dp": 1.0, "t": quote_stamp}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", zero_price)
    live_mod._client = None
    live_mod.refresh_passes(["NVDA"])
    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    # c == 0 is not a price, so the previous row is left alone.
    assert stored.current_price == 210.5
    assert stored.price_change_percent == 1.26
    assert stored.latest_quote_at == QUOTE_BEFORE_MIDNIGHT
    session.close()

    def no_story(_self, symbol, _news_from, _news_to):
        return [{"headline": "Markets move", "summary": "A general market roundup today.", "datetime": 10}]

    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", no_story)
    live_mod._client = None
    live_mod.refresh_passes(["NVDA"])
    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    assert stored.latest_news_headline == "__no_recent_company_news__"
    assert stored.latest_news_source is None
    assert stored.latest_news_url is None
    session.close()


def test_startup_adds_update_columns_to_an_old_database(tmp_path, monkeypatch):
    db_file = tmp_path / "old.db"
    conn = sqlite3.connect(db_file)
    conn.execute(OLD_COMPANIES)
    conn.execute(
        "INSERT INTO companies (ticker, company_name, short_name, status, holder_count) "
        "VALUES ('NVDA', 'NVIDIA Corporation', 'NVIDIA', 'active', 7)"
    )
    conn.commit()
    conn.close()
    before = _column_names(db_file)
    assert "latest_quote_at" not in before
    assert "latest_news_source" not in before
    assert "latest_news_url" not in before

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")

    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        from app.db import SessionLocal, init_db
        from app.models import Company

        init_db()
        session = SessionLocal()
        nvda = session.get(Company, "NVDA")
        assert nvda is not None
        assert nvda.holder_count == 7
        assert nvda.short_name == "NVIDIA"
        assert nvda.company_name == "NVIDIA Corporation"
        assert nvda.latest_quote_at is None
        assert nvda.latest_news_source is None
        assert nvda.latest_news_url is None
        session.close()

    names = _column_names(db_file)
    assert names.count("latest_quote_at") == 1
    assert names.count("latest_news_source") == 1
    assert names.count("latest_news_url") == 1
    assert names.count("short_name") == 1


def _refresh_quote(monkeypatch, live_mod, ticker, quote):
    def fake_quote(_self, symbol):
        assert symbol == ticker
        return quote

    def fake_news(_self, symbol, _news_from, _news_to):
        return []

    def fake_profile(_self, symbol):
        return {}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    live_mod._client = None
    live_mod.refresh_passes([ticker])


def _stored(ticker):
    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    company = session.get(Company, ticker)
    assert company is not None
    snapshot = (
        company.current_price,
        company.price_change_percent,
        company.latest_quote_at,
        company.latest_news_headline,
        company.latest_news_date,
    )
    session.close()
    return snapshot


def test_invalid_quote_timestamp_preserves_price_change_and_time(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    # QA repro: a real quote, then a later quote whose timestamp is 0.
    valid_t = 1762230600
    valid_at = datetime.fromtimestamp(valid_t, tz=timezone.utc).replace(tzinfo=None)
    _refresh_quote(monkeypatch, live_mod, "NVDA", {"c": 210.5, "dp": 1.26, "t": valid_t})
    assert _stored("NVDA")[:3] == (210.5, 1.26, valid_at)

    bad_timestamps = [
        {"c": 15.0, "dp": 1.0},
        {"c": 15.0, "dp": 1.0, "t": None},
        {"c": 15.0, "dp": 1.0, "t": 0},
        {"c": 15.0, "dp": 1.0, "t": -5},
        {"c": 15.0, "dp": 1.0, "t": "1762230600"},
        {"c": 15.0, "dp": 1.0, "t": True},
        {"c": 15.0, "dp": 1.0, "t": float("nan")},
        {"c": 15.0, "dp": 1.0, "t": float("inf")},
    ]
    for quote in bad_timestamps:
        _refresh_quote(monkeypatch, live_mod, "NVDA", quote)
        assert _stored("NVDA")[:3] == (210.5, 1.26, valid_at)

    # The same bad payloads must not create a quote on an empty row.
    assert _stored("SONY")[0] is None
    assert _stored("SONY")[2] is None
    for quote in bad_timestamps:
        _refresh_quote(monkeypatch, live_mod, "SONY", quote)
        assert _stored("SONY")[0] is None
        assert _stored("SONY")[1] is None
        assert _stored("SONY")[2] is None

    user_id = _onboard(client, ["gaming"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    assert client.post("/like", json={"user_id": user_id, "ticker": "SONY"}).status_code == 200
    matches = client.get("/matches", params={"user_id": user_id})
    nvidia = next(item for item in matches.json()["matches"] if item["ticker"] == "NVDA")
    assert nvidia["current_price"] == 210.5
    assert nvidia["price_change_percent"] == 1.26
    updates = _updates(client, user_id)
    assert [item["ticker"] for item in updates] == ["NVDA"]
    assert updates[0]["lines"][0].startswith("NVIDIA is up 1.3%")
    assert "US$15.00" not in updates[0]["lines"][0]


def test_zero_news_timestamp_does_not_invent_jan_1(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    _refresh_quote(
        monkeypatch,
        live_mod,
        "NVDA",
        {"c": 210.5, "dp": 1.26, "t": int(QUOTE_BEFORE_MIDNIGHT.replace(tzinfo=timezone.utc).timestamp())},
    )

    def fake_quote(_self, symbol):
        return {"c": 210.5, "dp": 1.26, "t": int(QUOTE_BEFORE_MIDNIGHT.replace(tzinfo=timezone.utc).timestamp())}

    def fake_news(_self, symbol, _news_from, _news_to):
        return [{
            "headline": "NVIDIA ships a new chip",
            "summary": "A short summary of the news.",
            "datetime": 0,
            "source": "Example Wire",
            "url": "https://example.com/nvda-news",
        }]

    def fake_profile(_self, symbol):
        return {}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    live_mod._client = None
    live_mod.refresh_passes(["NVDA"])

    price, pct, quote_at, headline, news_date = _stored("NVDA")
    assert price == 210.5
    assert headline == "__no_recent_company_news__"
    assert news_date is None
    assert news_date != "1970-01-01"

    user_id = _onboard(client, ["gaming"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    updates = _updates(client, user_id)
    assert updates[0]["lines"] == ["NVIDIA is up 1.3% (as of Nov 3), at US$210.50."]
    assert updates[0]["news_url"] is None
    assert "Jan 1" not in updates[0]["lines"][0]


def test_nonfinite_quotes_are_skipped_without_failing_other_tickers(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    valid_t = int(QUOTE_BEFORE_MIDNIGHT.replace(tzinfo=timezone.utc).timestamp())
    _refresh_quote(monkeypatch, live_mod, "NVDA", {"c": 210.5, "dp": 1.26, "t": valid_t})

    for quote in (
        {"c": math.inf, "dp": 1.26, "t": valid_t},
        {"c": -math.inf, "dp": 1.26, "t": valid_t},
        {"c": math.nan, "dp": 1.26, "t": valid_t},
        {"c": 15.0, "dp": math.inf, "t": valid_t},
        {"c": 15.0, "dp": -math.inf, "t": valid_t},
        {"c": 15.0, "dp": math.nan, "t": valid_t},
    ):
        _refresh_quote(monkeypatch, live_mod, "NVDA", quote)
        assert _stored("NVDA")[:3] == (210.5, 1.26, QUOTE_BEFORE_MIDNIGHT)

    assert _stored("AMD")[0] is None
    _refresh_quote(monkeypatch, live_mod, "AMD", {"c": math.inf, "dp": math.nan, "t": valid_t})
    assert _stored("AMD")[0] is None
    assert _stored("AMD")[2] is None

    _set_company(
        "AMD",
        current_price=math.inf,
        price_change_percent=1.26,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
        latest_news_headline="AMD ships a new chip",
        latest_news_date="2026-11-03",
        latest_news_source="Example Wire",
        latest_news_url="https://example.com/amd-news",
    )
    _set_company(
        "SONY",
        current_price=100.0,
        price_change_percent=math.nan,
        latest_quote_at=QUOTE_BEFORE_MIDNIGHT,
        latest_news_headline="Sony ships a new headset",
        latest_news_date="2026-11-03",
        latest_news_source=None,
        latest_news_url=None,
    )
    user_id = _onboard(client, ["gaming"])
    for ticker in ("NVDA", "AMD", "SONY", "RBLX"):
        assert client.post("/like", json={"user_id": user_id, "ticker": ticker}).status_code == 200

    # A garbage timestamp is written after the like, so loading that one row
    # must not hide the other liked stocks.
    from app.db import ENGINE

    assert ENGINE is not None
    with ENGINE.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE companies SET latest_quote_at = 'not-a-date', current_price = 10, "
            "price_change_percent = 1 WHERE ticker = 'RBLX'"
        )

    updates = _updates(client, user_id)
    by_ticker = {item["ticker"]: item for item in updates}
    assert "US$inf" not in str(updates)
    assert "nan" not in str(updates).lower()
    assert by_ticker["NVDA"]["lines"] == ["NVIDIA is up 1.3% (as of Nov 3), at US$210.50."]
    assert by_ticker["AMD"]["lines"] == [
        'In the news for AMD: "AMD ships a new chip" (Example Wire, Nov 3).'
    ]
    assert "US$" not in by_ticker["AMD"]["lines"][0]
    assert by_ticker["SONY"]["lines"] == [
        'In the news for Sony: "Sony ships a new headset" (Nov 3).'
    ]
    assert "RBLX" not in by_ticker
