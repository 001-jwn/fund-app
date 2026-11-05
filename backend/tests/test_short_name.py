"""short_name: old databases gain the column, the seed fills it, cards use it."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


OLD_COMPANIES = """
CREATE TABLE companies (
    ticker VARCHAR(32) NOT NULL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
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


def _column_names(db_file) -> list[str]:
    conn = sqlite3.connect(db_file)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(companies)")]
    finally:
        conn.close()


def test_startup_adds_short_name_and_the_loader_fills_it(tmp_path, monkeypatch):
    db_file = tmp_path / "old.db"
    conn = sqlite3.connect(db_file)
    conn.execute(OLD_COMPANIES)
    conn.execute(
        "INSERT INTO companies (ticker, company_name, status, holder_count) "
        "VALUES ('NVDA', 'NVIDIA Corporation', 'active', 7)"
    )
    conn.commit()
    conn.close()
    assert "short_name" not in _column_names(db_file)

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")

    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        from app.db import SessionLocal, init_db
        from app.models import Company

        # A second startup must not try to add the column again.
        init_db()

        session = SessionLocal()
        nvda = session.get(Company, "NVDA")
        amd = session.get(Company, "AMD")
        assert nvda is not None and amd is not None
        # Existing row was updated, not replaced. The table was not rebuilt.
        assert nvda.holder_count == 7
        assert nvda.company_name == "NVIDIA Corporation"
        assert nvda.short_name == "NVIDIA"
        # A company that was not in the old file is inserted with its short name.
        assert amd.short_name == "AMD"
        assert amd.company_name == "Advanced Micro Devices, Inc."
        filled = session.query(Company).filter(Company.short_name.isnot(None)).count()
        assert filled == 31
        session.close()

    names = _column_names(db_file)
    assert names.count("short_name") == 1


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _cards(client, user_id):
    response = client.get("/cards", params={"user_id": user_id, "limit": 50})
    assert response.status_code == 200, response.text
    return response.json()["cards"]


def test_because_liked_uses_short_name_and_falls_back_to_company_name(client):
    user_id = _onboard(client, ["gaming", "travel", "music", "automobile"])
    liked = client.post("/like", json={"user_id": user_id, "ticker": "SONY"})
    assert liked.status_code == 200

    cards = _cards(client, user_id)
    amd = next(card for card in cards if card["ticker"] == "AMD")
    assert amd["company_name"] == "Advanced Micro Devices, Inc."
    assert amd["short_name"] == "AMD"
    assert amd["because_liked"] == "Sony"

    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    sony = session.get(Company, "SONY")
    assert sony is not None
    sony.short_name = "   "
    session.commit()
    session.close()

    blank = next(card for card in _cards(client, user_id) if card["ticker"] == "AMD")
    assert blank["because_liked"] == "Sony Group Corporation"

    session = SessionLocal()
    sony = session.get(Company, "SONY")
    assert sony is not None
    sony.short_name = None
    session.commit()
    session.close()

    missing = next(card for card in _cards(client, user_id) if card["ticker"] == "AMD")
    assert missing["because_liked"] == "Sony Group Corporation"
