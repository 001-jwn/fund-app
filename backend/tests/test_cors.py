"""CORS: open by default, and limited when CORS_ORIGINS is set."""

from __future__ import annotations

from fastapi.testclient import TestClient

ORIGIN = "http://192.168.1.42:8081"
OTHER = "http://localhost:5173"
BLOCKED = "http://evil.example"


def _client(monkeypatch, tmp_path, origins: str | None) -> TestClient:
    db_file = tmp_path / "cors.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")
    if origins is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", origins)

    from app.main import create_app

    return TestClient(create_app())


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def _assert_any_origin(client: TestClient) -> None:
    preflight = _preflight(client, ORIGIN)
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"
    assert preflight.headers.get("access-control-allow-credentials") != "true"

    response = client.get("/health", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers.get("access-control-allow-credentials") != "true"


def test_cors_preflight_and_response_allow_any_origin_by_default(monkeypatch, tmp_path):
    # Unset, and a blank value (as in .env.example), both allow any origin.
    for origins in (None, ""):
        with _client(monkeypatch, tmp_path, origins) as client:
            _assert_any_origin(client)


def test_cors_honors_cors_origins_when_set(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, f"{ORIGIN}, {OTHER}") as client:
        preflight = _preflight(client, ORIGIN)
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == ORIGIN

        other = client.get("/health", headers={"Origin": OTHER})
        assert other.status_code == 200
        assert other.headers["access-control-allow-origin"] == OTHER

        blocked = client.get("/health", headers={"Origin": BLOCKED})
        assert blocked.status_code == 200
        assert "access-control-allow-origin" not in blocked.headers

        blocked_preflight = _preflight(client, BLOCKED)
        assert blocked_preflight.status_code == 400
        assert blocked_preflight.headers.get("access-control-allow-origin") != BLOCKED
