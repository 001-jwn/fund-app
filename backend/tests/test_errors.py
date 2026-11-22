"""P4 error shape, cards limit, and cached data when an upstream call is throttled."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

FIXTURE = Path(__file__).parent / "fixtures" / "main_cards_omitted_limit_gaming.json"
VENDOR = re.compile(r"finnhub|\bsec\b|traceback", re.IGNORECASE)

USER_NOT_FOUND = "We couldn't find your saved picks. Please choose your interests again."
COMPANY_NOT_FOUND = "We couldn't find that company."
COMPANY_NOT_ACTIVE = "That company isn't available right now."
OUTSIDE_INTERESTS = "That company doesn't match the interests you picked."
UNKNOWN_INTEREST = (
    "That interest isn't available. Please pick from Gaming, Travel, Music, or Automobile."
)
PICK_ONE = "Pick at least one interest."
NOT_FOUND = "We couldn't find that. Please try again."
BAD_REQUEST = "That didn't work. Please try again."
RATE_LIMITED = "Lots of requests right now. Wait a moment and try again."
DATA_UNAVAILABLE = "This information isn't available yet. Check back a little later."
SERVER_ERROR = "Something went wrong. Try again."


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def assert_api_error(response, status: int, code: str, detail: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert list(body) == ["detail", "code"]
    assert body == {"detail": detail, "code": code}
    assert isinstance(body["detail"], str)
    assert VENDOR.search(body["detail"]) is None
    assert "\n" not in body["detail"]


def test_method_not_allowed_keeps_the_allow_header(client):
    response = client.post("/health")
    assert response.status_code == 405
    assert response.content == b'{"detail":"That didn\'t work. Please try again.","code":"bad_request"}'
    allow = {part.strip() for part in response.headers["allow"].split(",")}
    assert "GET" in allow


def test_unknown_route_is_not_found(client):
    response = client.get("/not-a-route")
    assert_api_error(response, 404, "not_found", NOT_FOUND)


def test_unknown_user_and_company(client):
    user_id = _onboard(client, ["gaming"])
    checks = [
        client.get("/cards", params={"user_id": "nobody"}),
        client.get("/matches", params={"user_id": "nobody"}),
        client.get("/updates", params={"user_id": "nobody"}),
        client.post("/alerts/seen", json={"user_id": "nobody"}),
        client.post("/like", json={"user_id": "nobody", "ticker": "NVDA"}),
        client.post("/dislike", json={"user_id": "nobody", "ticker": "NVDA"}),
        client.post("/unlike", json={"user_id": "nobody", "ticker": "NVDA"}),
    ]
    for response in checks:
        assert_api_error(response, 404, "not_found", USER_NOT_FOUND)

    for path in ("/like", "/dislike", "/unlike"):
        missing = client.post(path, json={"user_id": user_id, "ticker": "NOPE"})
        assert_api_error(missing, 404, "not_found", COMPANY_NOT_FOUND)


def test_not_active_outside_interests_and_unknown_interest(client):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    session.add(
        Company(
            ticker="GONE",
            company_name="Delisted Example",
            short_description="Hidden.",
            status="delisted",
        )
    )
    session.flush()
    session.add(
        CompanyInterest(
            ticker="GONE",
            interest="gaming",
            why_line="You picked Gaming — this company is delisted and must stay hidden.",
        )
    )
    session.commit()
    session.close()

    user_id = _onboard(client, ["gaming"])
    inactive = client.post("/like", json={"user_id": user_id, "ticker": "GONE"})
    assert_api_error(inactive, 400, "bad_request", COMPANY_NOT_ACTIVE)

    outside = client.post("/like", json={"user_id": user_id, "ticker": "BKNG"})
    assert_api_error(outside, 400, "bad_request", OUTSIDE_INTERESTS)

    unknown = client.post("/onboarding", json={"interests": ["Finnhub"]})
    assert_api_error(unknown, 400, "bad_request", UNKNOWN_INTEREST)
    assert "Finnhub" not in unknown.text

    blank = client.post("/onboarding", json={"interests": ["SEC"]})
    assert_api_error(blank, 400, "bad_request", UNKNOWN_INTEREST)
    assert re.search(r"\bSEC\b", blank.text) is None

    empty = client.post("/onboarding", json={"interests": []})
    assert_api_error(empty, 400, "bad_request", PICK_ONE)


def test_invalid_limit_is_422_bad_request(client):
    user_id = _onboard(client, ["gaming"])
    for bad_limit in ("Finnhub", "1.5", "nope", "0", "-1", "-4", "51", "1000", "999999999999"):
        response = client.get("/cards", params={"user_id": user_id, "limit": bad_limit})
        assert_api_error(response, 422, "bad_request", BAD_REQUEST)
        assert "loc" not in response.text
        assert "Finnhub" not in response.text
        assert bad_limit not in response.text


def test_noncanonical_limit_is_422_and_valid_limits_match_main(client):
    import json

    user_id = _onboard(client, ["gaming"])
    omitted = client.get("/cards", params={"user_id": user_id})
    assert omitted.status_code == 200
    assert omitted.content == FIXTURE.read_bytes()
    main_cards = json.loads(FIXTURE.read_text(encoding="utf-8"))["cards"]

    for number in (1, 10, 50):
        response = client.get("/cards", params={"user_id": user_id, "limit": str(number)})
        assert response.status_code == 200
        if number >= len(main_cards):
            assert response.content == omitted.content
        else:
            assert response.json()["cards"] == main_cards[:number]

    for url in (
        f"/cards?user_id={user_id}&limit=10.0",
        f"/cards?user_id={user_id}&limit=%2010",
        f"/cards?user_id={user_id}&limit=5&limit=10",
    ):
        response = client.get(url)
        assert_api_error(response, 422, "bad_request", BAD_REQUEST)
        assert "10.0" not in response.text
        assert "loc" not in response.text


def test_openapi_422_uses_the_api_error_model(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/cards"]["get"]
    for status in ("404", "422", "500"):
        ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/ApiErrorOut"
        assert "HTTPValidationError" not in str(operation["responses"][status])
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    error = schema["components"]["schemas"]["ApiErrorOut"]
    assert error["properties"]["detail"]["type"] == "string"
    assert error["properties"]["code"]["enum"] == [
        "not_found",
        "bad_request",
        "rate_limited",
        "data_unavailable",
        "server_error",
    ]


def test_body_validation_is_422_bad_request(client):
    response = client.post("/onboarding", json={"interests": "Finnhub"})
    assert_api_error(response, 422, "bad_request", BAD_REQUEST)
    assert "Finnhub" not in response.text
    assert "loc" not in response.text

    missing_ticker = client.post("/like", json={"user_id": "somebody"})
    assert_api_error(missing_ticker, 422, "bad_request", BAD_REQUEST)
    assert "ticker" not in missing_ticker.text


def test_unhandled_exception_is_server_error_and_is_logged(client, monkeypatch, caplog):
    user_id = _onboard(client, ["gaming"])

    def explode(*_args, **_kwargs):
        raise RuntimeError("Finnhub HTTP 429 from SEC\nTraceback (most recent call last)")

    monkeypatch.setattr("app.routers.cards.order_feed_cards", explode)
    # Starlette re-raises after sending the 500 body so servers can log it.
    # The response body is what a client receives.
    transport = client._transport
    transport.raise_server_exceptions = False
    try:
        with caplog.at_level(logging.ERROR, logger="fund.errors"):
            response = client.get("/cards", params={"user_id": user_id})
    finally:
        transport.raise_server_exceptions = True
    assert_api_error(response, 500, "server_error", SERVER_ERROR)
    assert "Finnhub" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    logged = [
        record
        for record in caplog.records
        if record.exc_info and "Finnhub" in str(record.exc_info[1])
    ]
    assert logged


def test_reserved_rate_limited_and_data_unavailable_codes(client):
    @client.app.get("/__p4_rate_limited")
    def rate_limited():
        raise HTTPException(status_code=429, detail="Finnhub HTTP 429")

    @client.app.get("/__p4_unavailable")
    def unavailable():
        raise HTTPException(status_code=503, detail="SEC timeout and no cached value")

    limited = client.get("/__p4_rate_limited")
    assert_api_error(limited, 429, "rate_limited", RATE_LIMITED)
    assert "Finnhub" not in limited.text

    missing = client.get("/__p4_unavailable")
    assert_api_error(missing, 503, "data_unavailable", DATA_UNAVAILABLE)
    assert re.search(r"\bSEC\b", missing.text) is None


def test_omitted_limit_matches_main_bytes(client):
    """GET /cards with no limit is the same body main returned at 40891e1."""
    user_id = _onboard(client, ["gaming"])
    omitted = client.get("/cards", params={"user_id": user_id})
    explicit = client.get("/cards", params={"user_id": user_id, "limit": 10})
    assert omitted.status_code == 200
    assert explicit.status_code == 200
    assert omitted.content == FIXTURE.read_bytes()
    assert explicit.content == omitted.content
    assert len(omitted.json()["cards"]) == 8


def test_limit_returns_the_same_card_fields(client):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    for ticker in ("AAA1", "AAA2", "AAA3", "AAA4"):
        session.add(
            Company(
                ticker=ticker,
                company_name=f"Extra {ticker}",
                short_description="Extra card for the limit check.",
                quarterly_summary="A quiet quarter.",
                last_quarter_date="2026-01-31",
                status="active",
            )
        )
        session.flush()
        session.add(
            CompanyInterest(
                ticker=ticker,
                interest="gaming",
                why_line=f"You picked Gaming — extra {ticker}.",
            )
        )
    session.commit()
    session.close()

    user_id = _onboard(client, ["gaming"])
    omitted = client.get("/cards", params={"user_id": user_id})
    ten = client.get("/cards", params={"user_id": user_id, "limit": 10})
    two = client.get("/cards", params={"user_id": user_id, "limit": 2})
    assert omitted.status_code == 200
    assert omitted.content == ten.content
    omitted_cards = omitted.json()["cards"]
    assert len(omitted_cards) == 10
    assert [card["ticker"] for card in omitted_cards[:2]] == ["AAA1", "AAA2"]
    two_cards = two.json()["cards"]
    assert two_cards == omitted_cards[:2]
    assert set(two_cards[0]) == set(omitted_cards[0])


def test_upstream_429_still_serves_cached_values(client, monkeypatch, tmp_path):
    import urllib.error

    from app.db import SessionLocal
    from app.models import Company, SecFiling
    from app.services import live as live_mod
    from app.services import sec_filings as sec

    user_id = _onboard(client, ["gaming"])
    quote_at = datetime(2026, 11, 4, 4, 30, 0)
    session = SessionLocal()
    company = session.get(Company, "NVDA")
    company.current_price = 210.5
    company.price_change_percent = 1.26
    company.latest_quote_at = quote_at
    company.latest_news_headline = "NVIDIA ships a new chip"
    company.latest_news_summary = "A short summary of the news."
    company.latest_news_date = "2026-11-03"
    company.latest_news_source = "Example Wire"
    company.latest_news_url = "https://example.com/nvda-news"
    session.commit()
    session.close()

    before_cards = client.get("/cards", params={"user_id": user_id, "limit": 50})
    assert before_cards.status_code == 200
    before_nvidia = next(card for card in before_cards.json()["cards"] if card["ticker"] == "NVDA")

    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    session = SessionLocal()
    session.add(
        SecFiling(
            accession="0001045810-26-000099",
            ticker="NVDA",
            cik="0001045810",
            form="8-K",
            filed_at="2026-11-05",
            accepted_at="2026-11-05T16:00:00+00:00",
            h3_category="earnings",
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/example.htm",
            summary_plain="NVIDIA reported quarterly results on Nov 5.",
            verified=True,
        )
    )
    session.commit()
    stored_quote_at = session.get(Company, "NVDA").latest_quote_at
    session.close()

    before_updates = client.get("/updates", params={"user_id": user_id})
    assert before_updates.status_code == 200
    before_body = before_updates.json()
    before_lines = next(item["lines"] for item in before_body["updates"] if item["ticker"] == "NVDA")
    assert any("as of Nov 3" in line for line in before_lines)
    assert before_body["filings"]

    calls = []

    def urlopen(request, timeout=30):
        calls.append(request.full_url)
        assert "dummy-key" not in request.full_url
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=None)

    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")
    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path / "finnhub")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    live_mod._client = None
    monkeypatch.setattr("app.services.finnhub.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    live_mod.refresh_passes(["NVDA"])
    sec.refresh_liked_8k_filings()
    assert calls

    after_updates = client.get("/updates", params={"user_id": user_id})
    assert after_updates.status_code == 200
    after_body = after_updates.json()
    after_lines = next(item["lines"] for item in after_body["updates"] if item["ticker"] == "NVDA")
    assert after_lines == before_lines
    assert after_body["filings"] == before_body["filings"]
    assert "Finnhub" not in after_updates.text

    session = SessionLocal()
    assert session.get(Company, "NVDA").latest_quote_at == stored_quote_at
    assert session.get(Company, "NVDA").current_price == 210.5
    session.close()

    assert client.post("/unlike", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    after_cards = client.get("/cards", params={"user_id": user_id, "limit": 50})
    assert after_cards.status_code == 200
    after_nvidia = next(card for card in after_cards.json()["cards"] if card["ticker"] == "NVDA")
    assert after_nvidia == before_nvidia
