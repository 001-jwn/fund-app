"""SEC 8-K metadata cache. HTTP is mocked. No live SEC or Finnhub calls."""

from __future__ import annotations

import json
import urllib.error

from fastapi.testclient import TestClient

from app.services.sec_filings import SKIP_8K_TICKERS, h3_candidate_for_items, parse_items


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _like(client, user_id, ticker):
    response = client.post("/like", json={"user_id": user_id, "ticker": ticker})
    assert response.status_code == 200, response.text


def _submissions(forms):
    """forms is a list of (form, accession, items, primary)."""
    return {
        "filings": {
            "recent": {
                "accessionNumber": [row[1] for row in forms],
                "form": [row[0] for row in forms],
                "filingDate": ["2026-11-01" for _ in forms],
                "acceptanceDateTime": ["2026-11-01T21:00:00.000Z" for _ in forms],
                "items": [row[2] for row in forms],
                "primaryDocument": [row[3] for row in forms],
            }
        }
    }


def _install_http(monkeypatch, sec, routes, sleeps):
    def urlopen(request, timeout=30):
        sleeps.append(1)
        url = request.full_url
        for fragment, action in routes:
            if fragment in url:
                if isinstance(action, int):
                    raise urllib.error.HTTPError(url, action, "no", hdrs=None, fp=None)
                return _Body(action)
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)


class _Body:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _tickers(*pairs):
    payload = {}
    for index, (ticker, cik) in enumerate(pairs):
        payload[str(index)] = {"cik_str": cik, "ticker": ticker, "title": ticker}
    return payload


def _refresh(monkeypatch, tmp_path, client, routes):
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    sleeps = []
    _install_http(monkeypatch, sec, routes, sleeps)
    sec.refresh_liked_8k_filings()
    return sec, sleeps


def _rows():
    from app.db import SessionLocal
    from app.models import SecFiling

    session = SessionLocal()
    found = session.query(SecFiling).order_by(SecFiling.accession).all()
    snapshot = [
        (
            row.accession,
            row.ticker,
            row.cik,
            row.form,
            row.items,
            row.h3_candidate,
            row.h3_category,
            row.summary_plain,
            row.verified,
            row.amends_accession,
        )
        for row in found
    ]
    session.close()
    return snapshot


def test_parse_items_and_candidate_flag():
    assert parse_items(None) == []
    assert parse_items("") == []
    assert parse_items("  ") == []
    assert parse_items("2.02, 9.01") == ["2.02", "9.01"]
    assert h3_candidate_for_items([]) is False
    assert h3_candidate_for_items(["9.01"]) is False
    for item in ("1.01", "2.01", "2.02", "5.02", "7.01", "8.01"):
        assert h3_candidate_for_items([item]) is True
    assert h3_candidate_for_items(["2.02", "9.01"]) is True


def test_refresh_keeps_only_8k_for_liked_us_tickers(client, monkeypatch, tmp_path):
    user_id = _onboard(client, ["gaming", "music"])
    _like(client, user_id, "NVDA")
    _like(client, user_id, "SONY")
    _like(client, user_id, "SPOT")
    routes = [
        (
            "company_tickers.json",
            _tickers(("NVDA", 1045810), ("SONY", 313838), ("AAPL", 320193), ("SPOT", 1639920)),
        ),
        (
            "CIK0001045810",
            _submissions([
                ("8-K", "0001045810-26-000001", "2.02,9.01", "earn.htm"),
                ("8-K/A", "0001045810-26-000002", "5.02", "lead.htm"),
                ("6-K", "0001045810-26-000003", "2.02", "foreign.htm"),
                ("20-F", "0001045810-26-000004", "", "annual.htm"),
                ("10-Q", "0001045810-26-000005", "2.02", "quarter.htm"),
                ("8-K", "0001045810-26-000006", None, "empty.htm"),
                ("8-K", "0001045810-26-000007", "", "blank.htm"),
                ("8-K", "0001045810-26-000001", "1.01", "dup.htm"),
            ]),
        ),
    ]
    sec, _sleeps = _refresh(monkeypatch, tmp_path, client, routes)
    rows = _rows()
    accessions = [row[0] for row in rows]
    assert accessions == [
        "0001045810-26-000001",
        "0001045810-26-000002",
        "0001045810-26-000006",
        "0001045810-26-000007",
    ]
    by_acc = {row[0]: row for row in rows}
    kept = by_acc["0001045810-26-000001"]
    assert kept[1:] == (
        "NVDA",
        "0001045810",
        "8-K",
        "1.01",
        True,
        None,
        None,
        False,
        None,
    )
    amended = by_acc["0001045810-26-000002"]
    assert amended[3] == "8-K/A"
    assert amended[5] is True
    assert amended[6] is None and amended[7] is None and amended[8] is False and amended[9] is None
    assert by_acc["0001045810-26-000006"][4] is None
    assert by_acc["0001045810-26-000006"][5] is False
    assert by_acc["0001045810-26-000007"][5] is False
    assert all(row[1] not in SKIP_8K_TICKERS for row in rows)

    sec.refresh_liked_8k_filings()
    assert len(_rows()) == 4

    from app.db import SessionLocal
    from app.services.sec_filings import candidate_filings_for_user

    session = SessionLocal()
    found = candidate_filings_for_user(session, user_id)
    session.close()
    assert [row.accession for row in found] == [
        "0001045810-26-000001",
        "0001045810-26-000002",
    ]


def test_missing_user_agent_skips_and_unliked_tickers_are_not_fetched(client, monkeypatch, tmp_path):
    from app.services import sec_filings as sec

    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    calls = []
    monkeypatch.setattr(sec.urllib.request, "urlopen", lambda *_a, **_k: calls.append("x"))
    monkeypatch.setenv("SEC_USER_AGENT", "")
    sec._logged_missing_user_agent = False
    sec.refresh_liked_8k_filings()
    assert calls == []

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NTES")
    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    routes = [("company_tickers.json", _tickers(("RACE", 1648416), ("NVDA", 1045810)))]
    _install_http(monkeypatch, sec, routes, [])
    sec.refresh_liked_8k_filings()
    assert _rows() == []
    from app.db import SessionLocal
    from app.services.sec_filings import candidate_filings_for_user

    session = SessionLocal()
    assert candidate_filings_for_user(session, user_id) == []
    session.close()


def test_http_403_stops_the_run_and_sets_backoff(client, monkeypatch, tmp_path):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _like(client, user_id, "AMD")
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    seen = []

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        if "company_tickers" in request.full_url:
            return _Body(_tickers(("NVDA", 1045810), ("AMD", 2488)))
        raise urllib.error.HTTPError(request.full_url, 403, "no", hdrs=None, fp=None)

    monkeypatch.setattr(sec.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    assert len(seen) == 2
    assert _rows() == []

    from app.db import SessionLocal
    from app.models import SecFetchState

    session = SessionLocal()
    state = session.get(SecFetchState, "backoff")
    assert state is not None
    assert state.note == "HTTP 403"
    assert state.backoff_until is not None
    session.close()

    seen.clear()
    sec.refresh_liked_8k_filings()
    assert seen == []


def test_fetch_failure_keeps_prior_rows(client, monkeypatch, tmp_path):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    routes = [
        ("company_tickers.json", _tickers(("NVDA", 1045810), ("AMD", 2488))),
        ("CIK0001045810", _submissions([("8-K", "0001045810-26-000010", "2.02", "earn.htm")])),
    ]
    sec, _sleeps = _refresh(monkeypatch, tmp_path, client, routes)
    before = _rows()
    assert [row[0] for row in before] == ["0001045810-26-000010"]

    def expire(path):
        if not path.is_file():
            return
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        wrapper["fetched_at"] = "2000-01-01T00:00:00"
        path.write_text(json.dumps(wrapper), encoding="utf-8")

    expire(tmp_path / "sec" / "submissions" / "0001045810.json")
    seen = []

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        if "company_tickers" in request.full_url:
            return _Body(_tickers(("NVDA", 1045810)))
        raise urllib.error.URLError("temporary")

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    assert _rows() == before

    expire(tmp_path / "sec" / "company_tickers.json")
    seen.clear()

    def blocked(request, timeout=30):
        seen.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 429, "no", hdrs=None, fp=None)

    monkeypatch.setattr(sec.urllib.request, "urlopen", blocked)
    sec.refresh_liked_8k_filings()
    assert len(seen) == 1
    assert _rows() == before
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert seen == []


def test_updates_does_not_call_sec(client, monkeypatch):
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("network during GET /updates")

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.sec_filings.urllib.request.urlopen", boom)
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    response = client.get("/updates", params={"user_id": user_id})
    assert response.status_code == 200
    assert sorted(response.json()) == ["alerts", "digest", "unseen_count", "updates"]
    assert calls == []


def test_legacy_database_still_opens(tmp_path, monkeypatch):
    db_file = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")
    monkeypatch.setenv("SEC_USER_AGENT", "")

    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        from app.db import ENGINE, SessionLocal, init_db
        from app.models import Company

        with ENGINE.begin() as connection:
            connection.exec_driver_sql("DROP TABLE sec_filings")
            connection.exec_driver_sql("DROP TABLE sec_fetch_state")
        init_db()
        session = SessionLocal()
        stored = session.get(Company, "NVDA")
        assert stored is not None
        assert stored.company_name == "NVIDIA Corporation"
        session.close()
        with ENGINE.begin() as connection:
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert "sec_filings" in tables
        assert "sec_fetch_state" in tables
