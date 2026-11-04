"""Feed order: shared interest tags, then ticker. because_liked skips the shown interest."""

from __future__ import annotations

from datetime import datetime

GAMING = {"NVDA", "AMD", "RBLX", "TTWO", "NTES", "U", "MSFT", "SONY"}
TRAVEL = {"BKNG", "ABNB", "MAR", "HLT", "DAL", "LUV", "EXPE", "UBER"}
MUSIC = {"LYV", "SPOT", "WMG", "AAPL", "AMZN", "SIRI", "SPHR"}
AUTO = {"TSLA", "TM", "F", "GM", "RIVN", "RACE", "APTV", "BWA"}

SONY_WHY = "You picked Gaming — Sony makes PlayStation consoles and many of the games people play on them."


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _cards(client, user_id, limit=50):
    response = client.get("/cards", params={"user_id": user_id, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()["cards"]


def _add_company(ticker, name, interests):
    from app.db import SessionLocal
    from app.models import Company, CompanyInterest

    session = SessionLocal()
    session.add(
        Company(
            ticker=ticker,
            company_name=name,
            short_description="Used only in tests.",
            quarterly_summary="A quiet quarter.",
            last_quarter_date="2026-03-31",
            status="active",
        )
    )
    session.flush()
    for interest in interests:
        session.add(
            CompanyInterest(
                ticker=ticker,
                interest=interest,
                why_line=f"WHY-{ticker}-{interest}",
            )
        )
    session.commit()
    session.close()


def _add_interest(ticker, interest):
    from app.db import SessionLocal
    from app.models import CompanyInterest

    session = SessionLocal()
    session.add(
        CompanyInterest(
            ticker=ticker,
            interest=interest,
            why_line=f"WHY-{ticker}-{interest}",
        )
    )
    session.commit()
    session.close()


def _stamp_like(user_id, ticker, when):
    from app.db import SessionLocal
    from app.models import Like

    session = SessionLocal()
    row = session.get(Like, (user_id, ticker))
    assert row is not None
    row.created_at = when
    session.commit()
    session.close()


def test_no_likes_keeps_alphabetical_order(client):
    user_id = _onboard(client, ["gaming", "travel"])
    first = _cards(client, user_id)
    second = _cards(client, user_id)
    tickers = [card["ticker"] for card in first]
    assert tickers == sorted(GAMING | TRAVEL)
    assert tickers == [card["ticker"] for card in second]
    assert first == second
    for card in first:
        assert card["because_liked"] is None


def test_liked_and_disliked_never_return_and_shared_tags_rank_higher(client):
    user_id = _onboard(client, ["gaming", "travel"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200
    disliked = client.post("/dislike", json={"user_id": user_id, "ticker": "AMD"})
    assert disliked.status_code == 200

    cards = _cards(client, user_id)
    tickers = [card["ticker"] for card in cards]
    assert tickers == sorted(GAMING - {"NVDA", "AMD"}) + sorted(TRAVEL)
    assert "NVDA" not in tickers
    assert "AMD" not in tickers
    # Two interests, so the shared Gaming tag is enough to name NVIDIA.
    for card in cards:
        if card["ticker"] in GAMING:
            assert card["because_liked"] == "NVIDIA Corporation"
        else:
            assert card["because_liked"] is None
    assert _cards(client, user_id) == cards


def test_gaming_only_card_skips_because_liked_when_only_shared_tag_is_gaming(client):
    user_id = _onboard(client, ["Gaming"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200

    cards = _cards(client, user_id)
    amd = next(card for card in cards if card["ticker"] == "AMD")
    assert amd["interest"] == "gaming"
    assert amd["why_line"].startswith("You picked Gaming")
    assert amd["because_liked"] is None
    assert [card["ticker"] for card in cards] == sorted(GAMING - {"NVDA"})
    assert "NVDA" not in {card["ticker"] for card in cards}


def test_extra_shared_tag_sets_because_liked_and_ranks_first(client):
    # Music is not an interest this user picked. It still counts toward the score.
    _add_interest("NVDA", "music")
    _add_interest("SONY", "music")

    user_id = _onboard(client, ["gaming"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200

    cards = _cards(client, user_id)
    tickers = [card["ticker"] for card in cards]
    assert tickers[0] == "SONY"
    assert tickers == ["SONY", *sorted(GAMING - {"NVDA", "SONY"})]
    assert "NVDA" not in tickers

    sony = cards[0]
    assert sony["interest"] == "gaming"
    assert sony["why_line"] == SONY_WHY
    assert sony["because_liked"] == "NVIDIA Corporation"

    amd = next(card for card in cards if card["ticker"] == "AMD")
    assert amd["interest"] == "gaming"
    assert amd["because_liked"] is None

    top = _cards(client, user_id, limit=1)
    assert [card["ticker"] for card in top] == ["SONY"]
    assert top[0]["because_liked"] == "NVIDIA Corporation"

    hidden = client.post("/dislike", json={"user_id": user_id, "ticker": "SONY"})
    assert hidden.status_code == 200
    after = [card["ticker"] for card in _cards(client, user_id)]
    assert "SONY" not in after
    assert "NVDA" not in after
    assert after == sorted(GAMING - {"NVDA", "SONY"})


def test_because_liked_tie_breaks_are_deterministic(client):
    _add_company("CARD", "Card Co", ["gaming", "music", "travel", "automobile"])
    _add_company("BIGL", "Big Overlap Co", ["music", "travel", "automobile"])
    _add_company("AAAA", "Alpha Tie Co", ["travel"])
    _add_company("ZZZZ", "Zulu Tie Co", ["travel"])

    user_id = _onboard(client, ["gaming", "music", "travel", "automobile"])
    assert client.post("/like", json={"user_id": user_id, "ticker": "BIGL"}).status_code == 200
    assert client.post("/like", json={"user_id": user_id, "ticker": "ZZZZ"}).status_code == 200
    _stamp_like(user_id, "BIGL", datetime(2026, 1, 1, 0, 0, 0))
    _stamp_like(user_id, "ZZZZ", datetime(2026, 6, 1, 0, 0, 0))

    cards = _cards(client, user_id)
    assert cards == _cards(client, user_id)
    tickers = [card["ticker"] for card in cards]
    assert "BIGL" not in tickers
    assert "ZZZZ" not in tickers
    # CARD shares 3 tags with BIGL and 1 with ZZZZ (4). Travel shares both likes (2).
    # Music and automobile share only BIGL (1). Gaming shares none (0).
    assert tickers == (
        ["CARD"]
        + sorted(TRAVEL | {"AAAA"})
        + sorted(MUSIC | AUTO)
        + sorted(GAMING)
    )
    card = cards[0]
    assert card["ticker"] == "CARD"
    assert card["interest"] == "gaming"
    assert card["why_line"] == "WHY-CARD-gaming"
    # Four interests, so every shared tag counts. ZZZZ was liked later, but BIGL shares more tags.
    assert card["because_liked"] == "Big Overlap Co"
    booking = next(item for item in cards if item["ticker"] == "BKNG")
    assert booking["interest"] == "travel"
    # Booking shares Travel with both likes. ZZZZ was liked later, so it wins the tie.
    assert booking["because_liked"] == "Zulu Tie Co"
    spotify = next(item for item in cards if item["ticker"] == "SPOT")
    assert spotify["because_liked"] == "Big Overlap Co"

    # Same other-tag count: the later like wins, even when its ticker comes later.
    assert client.post("/dislike", json={"user_id": user_id, "ticker": "BIGL"}).status_code == 200
    assert client.post("/like", json={"user_id": user_id, "ticker": "AAAA"}).status_code == 200
    _stamp_like(user_id, "AAAA", datetime(2026, 1, 1, 0, 0, 0))
    _stamp_like(user_id, "ZZZZ", datetime(2026, 6, 1, 0, 0, 0))
    later = next(item for item in _cards(client, user_id) if item["ticker"] == "CARD")
    assert later["because_liked"] == "Zulu Tie Co"
    assert "AAAA" not in {item["ticker"] for item in _cards(client, user_id)}
    assert "ZZZZ" not in {item["ticker"] for item in _cards(client, user_id)}

    # Same count and the same Like.created_at: ticker A to Z.
    same = datetime(2026, 3, 1, 12, 0, 0)
    _stamp_like(user_id, "AAAA", same)
    _stamp_like(user_id, "ZZZZ", same)
    tied = _cards(client, user_id)
    assert tied == _cards(client, user_id)
    card = next(item for item in tied if item["ticker"] == "CARD")
    assert card["because_liked"] == "Alpha Tie Co"


def test_all_four_interests_names_sony_on_the_amd_card(client):
    user_id = _onboard(client, ["gaming", "travel", "music", "automobile"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "SONY"})
    assert liked.status_code == 200

    cards = _cards(client, user_id)
    amd = next(card for card in cards if card["ticker"] == "AMD")
    assert amd["interest"] == "gaming"
    assert amd["why_line"].startswith("You picked Gaming")
    assert amd["because_liked"] == "Sony Group Corporation"
    assert "SONY" not in {card["ticker"] for card in cards}
    travel = next(card for card in cards if card["ticker"] == "BKNG")
    assert travel["because_liked"] is None
