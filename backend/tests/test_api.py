"""Milestone 1 API: onboarding, cards, swipes, matches, offline Finnhub."""

from __future__ import annotations

import json

GAMING = {"NVDA", "AMD", "RBLX", "TTWO", "NTES", "U", "MSFT", "SONY"}
TRAVEL = {"BKNG", "ABNB", "MAR", "HLT", "DAL", "LUV", "EXPE", "UBER"}
MUSIC = {"LYV", "SPOT", "WMG", "AAPL", "AMZN", "SIRI", "SPHR"}


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _cards(client, user_id, limit=50):
    response = client.get("/cards", params={"user_id": user_id, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()["cards"]


def test_health_without_finnhub_key(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "finnhub": "off"}


def test_onboarding_creates_user_and_rejects_bad_input(client):
    user_id = _onboard(client, ["Gaming", "music", "music"])
    assert isinstance(user_id, str) and user_id

    empty = client.post("/onboarding", json={"interests": []})
    assert empty.status_code == 400

    unknown = client.post("/onboarding", json={"interests": ["crypto"]})
    assert unknown.status_code == 400


def test_cards_filter_by_interest_and_hide_holder_count(client):
    user_id = _onboard(client, ["gaming"])
    cards = _cards(client, user_id)
    assert {card["ticker"] for card in cards} == GAMING
    for card in cards:
        assert card["interest"] == "gaming"
        assert card["why_line"].startswith("You picked Gaming")
        assert "Travel" not in card["why_line"]
        assert "Music" not in card["why_line"]
        assert "holder_count" not in card
        assert card["price_available"] is False
        assert card["current_price"] is None
        assert card["news_available"] is False
        assert card["latest_news_headline"] is None

    nvidia = next(card for card in cards if card["ticker"] == "NVDA")
    assert nvidia["why_line"] == (
        "You picked Gaming — NVIDIA makes the graphics chips inside many gaming PCs."
    )
    assert nvidia["last_quarter_date"] == "2026-07-26"
    assert nvidia["company_name"] == "NVIDIA Corporation"
    assert nvidia["short_description"]
    assert nvidia["quarterly_summary"]

    travel_id = _onboard(client, ["travel"])
    travel_cards = _cards(client, travel_id)
    assert {card["ticker"] for card in travel_cards} == TRAVEL
    assert "NVDA" not in {card["ticker"] for card in travel_cards}


def test_cards_exclude_delisted_liked_and_disliked(client):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    session.add(
        Company(
            ticker="GONE",
            company_name="Delisted Example",
            short_description="Should not appear.",
            quarterly_summary="Old quarter.",
            last_quarter_date="2020-01-01",
            status="delisted",
            holder_count=None,
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
    before = {card["ticker"] for card in _cards(client, user_id)}
    assert "GONE" not in before
    assert "NVDA" in before

    liked = client.post("/like", json={"user_id": user_id, "ticker": "nvda"})
    assert liked.status_code == 200
    assert liked.json()["matched"] is True
    assert liked.json()["ticker"] == "NVDA"

    disliked = client.post("/dislike", json={"user_id": user_id, "ticker": "AMD"})
    assert disliked.status_code == 200

    after = {card["ticker"] for card in _cards(client, user_id)}
    assert "NVDA" not in after
    assert "AMD" not in after
    assert "GONE" not in after


def test_why_line_matches_the_interest_the_user_picked(client):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    session.add(
        Company(
            ticker="BOTH",
            company_name="Both Interests Co",
            short_description="Used only in tests.",
            quarterly_summary="A quiet quarter.",
            last_quarter_date="2026-03-31",
            status="active",
            holder_count=12345,
        )
    )
    session.flush()
    session.add(
        CompanyInterest(
            ticker="BOTH",
            interest="gaming",
            why_line="GAMING-WHY-LINE-UNIQUE",
        )
    )
    session.add(
        CompanyInterest(
            ticker="BOTH",
            interest="music",
            why_line="MUSIC-WHY-LINE-UNIQUE",
        )
    )
    session.commit()
    session.close()

    music_id = _onboard(client, ["music"])
    music_card = next(card for card in _cards(client, music_id) if card["ticker"] == "BOTH")
    assert music_card["interest"] == "music"
    assert music_card["why_line"] == "MUSIC-WHY-LINE-UNIQUE"
    assert "GAMING-WHY-LINE-UNIQUE" not in music_card["why_line"]
    assert "holder_count" not in music_card

    gaming_id = _onboard(client, ["gaming"])
    gaming_card = next(card for card in _cards(client, gaming_id) if card["ticker"] == "BOTH")
    assert gaming_card["interest"] == "gaming"
    assert gaming_card["why_line"] == "GAMING-WHY-LINE-UNIQUE"

    both_id = _onboard(client, ["music", "gaming"])
    both_card = next(card for card in _cards(client, both_id) if card["ticker"] == "BOTH")
    assert both_card["why_line"] in {"GAMING-WHY-LINE-UNIQUE", "MUSIC-WHY-LINE-UNIQUE"}
    assert both_card["interest"] == "gaming"
    assert both_card["why_line"] == "GAMING-WHY-LINE-UNIQUE"


def test_like_creates_match_and_dislike_removes_it(client):
    user_id = _onboard(client, ["music"])
    first = client.post("/like", json={"user_id": user_id, "ticker": "SPOT"})
    assert first.status_code == 200
    again = client.post("/like", json={"user_id": user_id, "ticker": "SPOT"})
    assert again.status_code == 200

    listed = client.get("/matches", params={"user_id": user_id})
    assert listed.status_code == 200
    matches = listed.json()["matches"]
    assert [item["ticker"] for item in matches] == ["SPOT"]
    assert matches[0]["why_line"].startswith("You picked Music")
    assert "holder_count" not in matches[0]
    assert matches[0]["interest"] == "music"

    client.post("/like", json={"user_id": user_id, "ticker": "AAPL"})
    listed = client.get("/matches", params={"user_id": user_id})
    tickers = [item["ticker"] for item in listed.json()["matches"]]
    assert tickers[0] == "AAPL"
    assert set(tickers) == {"AAPL", "SPOT"}

    removed = client.post("/dislike", json={"user_id": user_id, "ticker": "SPOT"})
    assert removed.status_code == 200
    assert removed.json()["matched"] is False
    remaining = client.get("/matches", params={"user_id": user_id})
    assert [item["ticker"] for item in remaining.json()["matches"]] == ["AAPL"]

    music_tickers = {card["ticker"] for card in _cards(client, user_id)}
    assert music_tickers == MUSIC - {"AAPL", "SPOT"}


def test_unlike_removes_the_match_and_brings_the_card_back(client):
    user_id = _onboard(client, ["music"])
    other_id = _onboard(client, ["music"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "SPOT"}).status_code == 200
    assert client.post("/like", json={"user_id": other_id, "ticker": "SPOT"}).status_code == 200

    removed = client.post("/unlike", json={"user_id": user_id, "ticker": "spot"})
    assert removed.status_code == 200
    assert removed.json() == {
        "ok": True,
        "user_id": user_id,
        "ticker": "SPOT",
        "matched": False,
    }

    listed = client.get("/matches", params={"user_id": user_id})
    assert listed.json()["matches"] == []
    assert "SPOT" in {card["ticker"] for card in _cards(client, user_id)}

    other_matches = client.get("/matches", params={"user_id": other_id})
    assert [item["ticker"] for item in other_matches.json()["matches"]] == ["SPOT"]

    again = client.post("/unlike", json={"user_id": user_id, "ticker": "SPOT"})
    assert again.status_code == 200
    assert again.json()["ok"] is True
    assert again.json()["matched"] is False
    assert "SPOT" in {card["ticker"] for card in _cards(client, user_id)}

    missing_user = client.post("/unlike", json={"user_id": "nobody", "ticker": "SPOT"})
    assert missing_user.status_code == 404

    missing_company = client.post("/unlike", json={"user_id": user_id, "ticker": "NOPE"})
    assert missing_company.status_code == 404

    # Outside the user's interests, and not currently liked. Still ok, and not a dislike.
    outside = client.post("/unlike", json={"user_id": user_id, "ticker": "BKNG"})
    assert outside.status_code == 200
    assert outside.json()["matched"] is False
    assert "BKNG" not in {card["ticker"] for card in _cards(client, user_id)}

    from app.db import SessionLocal
    from app.models import Dislike

    session = SessionLocal()
    assert session.query(Dislike).filter(Dislike.user_id == user_id).count() == 0
    session.close()


def test_unknown_user_and_ticker(client):
    missing = client.get("/cards", params={"user_id": "nobody"})
    assert missing.status_code == 404
    user_id = _onboard(client, ["automobile"])
    bad = client.post("/like", json={"user_id": user_id, "ticker": "NOPE"})
    assert bad.status_code == 404


def test_running_without_finnhub_key_does_not_call_network(client, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("Finnhub was called even though no API key is set")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    user_id = _onboard(client, ["automobile"])
    cards = _cards(client, user_id)
    assert {card["ticker"] for card in cards} == {"TSLA", "TM", "F", "GM", "RIVN", "RACE", "APTV", "BWA"}
    for card in cards:
        assert card["price_available"] is False
        assert card["current_price"] is None
        assert card["price_change_percent"] is None
        assert card["news_available"] is False
        assert card["latest_news_headline"] is None
        assert card["logo_url"] is None
        assert card["why_line"].startswith("You picked Automobile")


def test_refresh_stores_live_fields_and_keeps_seed_quarter_date(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None

    def fake_quote(_self, symbol):
        assert symbol == "NVDA"
        return {"c": 210.5, "dp": 1.25}

    def fake_news(_self, symbol, _news_from, _news_to):
        return [
            {
                "headline": "NVIDIA ships a new chip",
                "summary": "A short summary of the news.",
                "datetime": 1793577600,  # 2026-11-02 00:00:00 UTC
            }
        ]

    def fake_profile(_self, symbol):
        return {"logo": "https://example.com/nvda.png", "name": "Should Not Replace Seed"}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    live_mod.refresh_passes(["NVDA"])

    user_id = _onboard(client, ["gaming"])
    nvidia = next(card for card in _cards(client, user_id) if card["ticker"] == "NVDA")
    assert nvidia["price_available"] is True
    assert nvidia["current_price"] == 210.5
    assert nvidia["price_change_percent"] == 1.25
    assert nvidia["news_available"] is True
    assert nvidia["latest_news_headline"] == "NVIDIA ships a new chip"
    assert nvidia["latest_news_summary"] == "A short summary of the news."
    assert nvidia["latest_news_date"] == "2026-11-02"
    assert nvidia["news_date_label"] == "News from Nov 2"
    assert nvidia["quarter_label"] == "Last quarter (ended Jul 26, 2026)"
    assert nvidia["logo_url"] == "https://example.com/nvda.png"
    assert nvidia["last_quarter_date"] == "2026-07-26"
    assert "holder_count" not in nvidia

    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    stored = session.get(Company, "NVDA")
    assert stored.holder_count is None
    assert stored.current_price == 210.5
    session.close()

    # A second seed load must not wipe the cached price or rewrite the seed file.
    from app.seed.load_seed import SEED_PATH, load_seed

    before = SEED_PATH.read_bytes()
    assert load_seed() == 31
    assert SEED_PATH.read_bytes() == before
    session = SessionLocal()
    assert session.get(Company, "NVDA").current_price == 210.5
    assert session.get(Company, "NVDA").holder_count is None
    session.close()


def test_refresh_failure_does_not_invent_numbers(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None

    def explode(*_args, **_kwargs):
        raise RuntimeError("finnhub down")

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", explode)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", explode)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", explode)
    live_mod.refresh_passes(["TSLA"])

    user_id = _onboard(client, ["automobile"])
    tesla = next(card for card in _cards(client, user_id) if card["ticker"] == "TSLA")
    assert tesla["price_available"] is False
    assert tesla["current_price"] is None
    assert tesla["news_available"] is False
    assert tesla["news_status"] == "unavailable"
    assert tesla["news_message"] is None


def test_loader_ignores_interest_tags(client, tmp_path):
    payload = {
        "companies": [
            {
                "ticker": "TAGS",
                "company_name": "Tag Test",
                "short_description": "A company used to prove the loader ignores interest_tags.",
                "quarterly_summary": "Nothing happened.",
                "last_quarter_date": "2026-01-31",
                "status": "active",
                "holder_count": 50,
                "current_price": 999,
                "interest_tags": ["music", "travel"],
                "interests": [
                    {"interest": "gaming", "why_line": "ONLY-FROM-INTERESTS-LIST"}
                ],
            }
        ]
    }
    path = tmp_path / "mini.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    from app.seed.load_seed import load_seed

    assert load_seed(path) == 1
    assert load_seed(path) == 1

    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    interests = session.query(CompanyInterest).filter(CompanyInterest.ticker == "TAGS").all()
    assert [(row.interest, row.why_line) for row in interests] == [
        ("gaming", "ONLY-FROM-INTERESTS-LIST")
    ]
    # Live numbers in a seed file are not trusted. Price stays empty.
    assert session.get(Company, "TAGS").current_price is None
    assert session.get(Company, "TAGS").holder_count is None
    session.close()

    user_id = _onboard(client, ["music"])
    assert "TAGS" not in {card["ticker"] for card in _cards(client, user_id)}
    gaming_id = _onboard(client, ["gaming"])
    tagged = next(card for card in _cards(client, gaming_id) if card["ticker"] == "TAGS")
    assert tagged["why_line"] == "ONLY-FROM-INTERESTS-LIST"


def test_seed_file_location_and_contents(client):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest
    from app.seed.load_seed import SEED_PATH, load_seed

    assert SEED_PATH.as_posix().endswith("backend/app/seed/seed_companies.json")
    assert SEED_PATH.is_file()

    before = SEED_PATH.read_bytes()
    load_seed()
    load_seed()
    assert SEED_PATH.read_bytes() == before

    session = SessionLocal()
    tickers = {row.ticker for row in session.query(Company).all()}
    assert len(tickers) == 31
    assert "NTES" in tickers and "SPHR" in tickers
    assert "EA" not in tickers and "EB" not in tickers
    assert session.query(Company).filter(Company.status != "active").count() == 0
    assert session.query(CompanyInterest).count() == 31
    assert session.query(Company).filter(Company.holder_count.isnot(None)).count() == 0
    assert session.query(Company).filter(Company.current_price.isnot(None)).count() == 0
    session.close()


def test_like_and_dislike_reject_ticker_outside_interests(client):
    user_id = _onboard(client, ["gaming"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "BKNG"})
    assert liked.status_code == 400
    assert "interest" in liked.json()["detail"].lower()
    disliked = client.post("/dislike", json={"user_id": user_id, "ticker": "HLT"})
    assert disliked.status_code == 400
    assert "interest" in disliked.json()["detail"].lower()
    matches = client.get("/matches", params={"user_id": user_id})
    assert matches.json()["matches"] == []
    cards = {card["ticker"] for card in _cards(client, user_id)}
    assert "BKNG" not in cards and "NVDA" in cards
    ok = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert ok.status_code == 200
    assert ok.json()["matched"] is True


def test_no_matching_news_uses_the_empty_message(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod
    from app.services.news import NO_RECENT_NEWS_MESSAGE

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    calls = []

    def fake_quote(_self, symbol):
        calls.append(("quote", symbol))
        return {"c": 20.0, "dp": 0.5}

    def fake_news(_self, symbol, _news_from, _news_to):
        calls.append(("news", symbol))
        return [{
            "headline": "Stocks swing on election night",
            "summary": "U.S. markets moved as results came in.",
            "datetime": 10,
        }]

    def fake_profile(_self, symbol):
        calls.append(("profile", symbol))
        return {"logo": "https://example.com/logo.png"}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    live_mod.refresh_passes(["AMD", "NVDA"])

    assert calls == [
        ("quote", "AMD"),
        ("quote", "NVDA"),
        ("news", "AMD"),
        ("news", "NVDA"),
        ("profile", "AMD"),
        ("profile", "NVDA"),
    ]
    user_id = _onboard(client, ["gaming"])
    cards = {card["ticker"]: card for card in _cards(client, user_id)}
    for ticker in ("AMD", "NVDA"):
        card = cards[ticker]
        assert card["news_status"] == "none"
        assert card["news_message"] == NO_RECENT_NEWS_MESSAGE
        assert card["news_available"] is False
        assert card["latest_news_headline"] is None
        assert card["latest_news_summary"] is None
        assert card["price_available"] is True
        assert card["current_price"] == 20.0


def test_matches_empty(client):
    user_id = _onboard(client, ["travel"])
    response = client.get("/matches", params={"user_id": user_id})
    assert response.status_code == 200
    assert response.json() == {"matches": []}
