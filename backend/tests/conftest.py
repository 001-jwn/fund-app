"""Each test gets its own SQLite file and no Finnhub key."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
