"""hide_reason is stored for unconfirmable rows and never leaves the API."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.services.sec_text import build_summary, decide_filing

PAD = "The company filed this report with the regulator on the date shown. " * 4
EXHIBIT = "https://www.sec.gov/Archives/edgar/data/1045810/ex99.htm"


def _doc(text: str, *, exhibit: str | None = None, too_long: bool = False) -> dict:
    return {
        "url": EXHIBIT if exhibit else "https://www.sec.gov/Archives/edgar/data/1045810/body.htm",
        "role": "exhibit" if exhibit else "main",
        "exhibit": exhibit,
        "text": text if too_long else f"{text}\n{PAD}",
        "raw": "",
        "too_long": too_long,
    }


def _decide(ticker, form, items, text, accession="0001045810-26-000010", exhibit=None, too_long=False):
    return decide_filing(
        ticker=ticker,
        form=form,
        items=items,
        accession=accession,
        documents=[_doc(text, exhibit=exhibit, too_long=too_long)],
    )


def test_each_hide_reason_value(client):
    skipped = _decide("NTES", "8-K", ["2.02"], "Results for the quarter ended September 30, 2026.")
    assert skipped["hide_reason"] == "skipped_fpi"
    assert skipped["text_outcome"] == "unconfirmable"

    other = _decide("NVDA", "10-K", ["2.02"], "Results for the quarter ended September 30, 2026.")
    assert other["hide_reason"] == "not_8k"

    amended = _decide(
        "AAPL",
        "8-K/A",
        ["5.02"],
        "This amendment amends the report. Jane Doe resigned as chief financial officer.",
        accession="0001140361-26-035325",
    )
    assert amended["hide_reason"] == "amendment"
    assert amended["h3_category"] is None

    long = _decide("NVDA", "8-K", ["2.02"], "too long", too_long=True)
    assert long["hide_reason"] == "too_long"

    empty = decide_filing(
        ticker="NVDA",
        form="8-K",
        items=["2.02"],
        accession="0001045810-26-000010",
        documents=[{"url": EXHIBIT, "role": "main", "exhibit": None, "text": "short", "raw": "", "too_long": False}],
    )
    assert empty["hide_reason"] == "no_text"

    two = _decide(
        "NVDA",
        "8-K",
        ["2.02"],
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10. The Company also raised its outlook for the next quarter.",
        exhibit="99.1",
    )
    assert two["hide_reason"] == "two_categories"

    restated = _decide(
        "MSFT",
        "8-K",
        ["8.01"],
        "The Company reaffirms its outlook for the next quarter.",
    )
    assert restated["hide_reason"] == "restated_outlook"
    assert restated["h3_category"] is None

    mixed = _decide(
        "NVDA",
        "8-K",
        ["7.01"],
        "The Company raised its revenue outlook and lowered its margin outlook for the next quarter.",
    )
    assert mixed["hide_reason"] == "unclear_direction"

    none = _decide("NVDA", "8-K", ["7.01"], "The Company declared a quarterly dividend of $0.25 per share.")
    assert none["hide_reason"] == "no_category"

    from app.db import SessionLocal
    from app.models import SecFiling
    from app.services.sec_filings import _apply_decision, _mark_document_unreadable

    session = SessionLocal()
    session.add(
        SecFiling(
            accession="0001045810-26-000088",
            ticker="NVDA",
            cik="0001045810",
            form="8-K",
            h3_candidate=True,
            verified=False,
            text_outcome=None,
        )
    )
    session.commit()
    session.close()
    _mark_document_unreadable("0001045810-26-000088")
    session = SessionLocal()
    unreadable = session.get(SecFiling, "0001045810-26-000088")
    assert unreadable.hide_reason == "no_text"
    assert unreadable.text_outcome == "unconfirmable"
    session.close()

    rejected = _decide(
        "NVDA",
        "8-K",
        ["5.02"],
        "On May 1, 2026, the Board appointed Jane Doe as chief financial officer.",
    )
    assert rejected["text_outcome"] == "confirmed"
    row = SecFiling(
        accession="0001045810-26-000089",
        ticker="NVDA",
        cik="0001045810",
        form="8-K",
        accepted_at="2026-11-05T16:00:00Z",
        h3_candidate=True,
    )
    _apply_decision(row, rejected, "NVIDIA")
    assert row.hide_reason == "leadership_rejected"
    assert row.summary_plain is None
    assert row.verified is False
    assert "will become" not in (row.summary_plain or "")

    shown = _decide(
        "NVDA",
        "8-K",
        ["2.02"],
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10.",
        exhibit="99.1",
    )
    quiet = SecFiling(
        accession="0001045810-26-000090",
        ticker="NVDA",
        cik="0001045810",
        form="8-K",
        accepted_at="2026-11-06T02:00:00Z",
        h3_candidate=True,
    )
    _apply_decision(quiet, shown, "NVIDIA")
    assert quiet.hide_reason is None
    assert quiet.text_outcome == "confirmed"
    assert quiet.summary_plain
    advice = SecFiling(
        accession="0001045810-26-000091",
        ticker="NVDA",
        cik="0001045810",
        form="8-K",
        accepted_at="2026-11-06T02:00:00Z",
        h3_candidate=True,
    )
    _apply_decision(advice, shown, "Buy")
    assert advice.hide_reason == "no_line"
    assert advice.summary_plain is None
    assert advice.text_outcome == "unconfirmable"


def test_restated_outlook_matches_reiterate_and_keeps_earnings():
    reaffirm = _decide("MSFT", "8-K", ["8.01"], "The Company reaffirms its outlook for the next quarter.")
    reiterate = _decide("MSFT", "8-K", ["8.01"], "The Company reiterates its outlook for the next quarter.")
    affirm = _decide("MSFT", "8-K", ["7.01"], "The Company affirms its guidance for the full year.")
    confirm = _decide("MSFT", "8-K", ["8.01"], "The Company confirms its outlook for the next quarter.")
    for decision in (reaffirm, reiterate, affirm, confirm):
        assert decision["hide_reason"] == "restated_outlook"
        assert decision["h3_category"] is None
        assert build_summary(
            category=decision.get("h3_category"),
            form="8-K",
            accepted_at="2026-11-06T02:00:00Z",
            name="Microsoft",
            fields=decision,
        ) is None

    earnings = _decide(
        "TTWO",
        "8-K",
        ["2.02"],
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10. The Company reaffirms its outlook for the next quarter.",
        exhibit="99.1",
    )
    assert earnings["h3_category"] == "earnings"
    assert earnings["hide_reason"] is None
    line = build_summary(
        category=earnings.get("h3_category"),
        form="8-K",
        accepted_at="2026-11-09T16:00:00Z",
        name="Take-Two",
        fields=earnings,
    )
    assert line.startswith("Take-Two shared its quarterly results in an SEC filing on Nov 9.")
    assert "outlook" not in line
    assert "confirmed its earlier outlook" not in line

    raised = _decide(
        "NVDA",
        "8-K",
        ["2.02"],
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10. The Company raised its outlook for the next quarter.",
        exhibit="99.1",
    )
    assert raised["hide_reason"] == "two_categories"

    both = _decide(
        "MSFT",
        "8-K",
        ["8.01"],
        "The Company raises its revenue outlook and reaffirms its EPS outlook for the next quarter.",
    )
    assert both["hide_reason"] == "restated_outlook"
    assert both["h3_category"] is None

    call = _decide(
        "NVDA",
        "8-K",
        ["7.01"],
        "The Company confirmed the date of its conference call.",
    )
    assert call["hide_reason"] == "no_category"
    assert call["hide_reason"] != "restated_outlook"


def test_original_restated_phrases_match_anywhere_in_the_sentence():
    earnings = (
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10. "
    )
    targets = _decide(
        "TTWO",
        "8-K",
        ["2.02"],
        earnings + "The Company reiterated its full-year targets.",
        exhibit="99.1",
    )
    assert targets["h3_category"] == "earnings"
    assert targets["hide_reason"] is None
    targets_line = build_summary(
        category=targets.get("h3_category"),
        form="8-K",
        accepted_at="2026-11-09T21:00:00Z",
        name="Take-Two",
        fields=targets,
    )
    assert targets_line.startswith("Take-Two shared its quarterly results in an SEC filing on Nov 9.")

    provided = _decide(
        "MSFT",
        "8-K",
        ["2.02"],
        earnings + "As provided on July 29, 2026, the Company expects fiscal 2027 revenue of $90 billion.",
        exhibit="99.1",
    )
    assert provided["h3_category"] == "earnings"
    assert provided["hide_reason"] is None
    provided_line = build_summary(
        category=provided.get("h3_category"),
        form="8-K",
        accepted_at="2026-11-09T21:00:00Z",
        name="Microsoft",
        fields=provided,
    )
    assert provided_line.startswith("Microsoft shared its quarterly results")
    assert "outlook" not in (provided_line or "").lower()

    hidden = _decide(
        "MSFT",
        "8-K",
        ["7.01"],
        "The Company reiterated its fiscal 2027 targets. The Company raised its outlook for the next quarter.",
    )
    assert hidden["h3_category"] is None
    assert hidden["hide_reason"] == "restated_outlook"
    hidden_line = build_summary(
        category=hidden.get("h3_category"),
        form="8-K",
        accepted_at="2026-11-09T21:00:00Z",
        name="Microsoft",
        fields=hidden,
    )
    assert hidden_line is None
    assert "raised its outlook" not in (hidden_line or "")


def test_expired_cache_is_redecided_without_a_network_call(client, monkeypatch, tmp_path):
    from sqlalchemy.orm import Session

    from app.db import SessionLocal
    from app.models import SecFiling
    from app.services import sec_filings as sec

    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    accession = "0001045810-26-000311"
    text = "The Company declared a quarterly dividend of $0.25 per share. " * 4
    cache = tmp_path / "sec" / "documents" / f"{accession}.json"
    cache.parent.mkdir(parents=True)
    stale = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)).isoformat()
    cache.write_text(
        json.dumps(
            {
                "fetched_at": stale,
                "data": [{
                    "url": EXHIBIT,
                    "role": "main",
                    "exhibit": None,
                    "text": text,
                    "raw": "",
                    "too_long": False,
                }],
            }
        ),
        encoding="utf-8",
    )
    kept = "NVIDIA shared its quarterly results in an SEC filing on Nov 5."
    session = SessionLocal()
    session.add(
        SecFiling(
            accession=accession,
            ticker="NVDA",
            cik="0001045810",
            form="8-K",
            accepted_at="2026-11-06T02:00:00Z",
            items="8.01",
            h3_candidate=True,
            h3_category="earnings",
            verified=True,
            text_outcome="confirmed",
            summary_plain=kept,
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/index.html",
        )
    )
    missing = "0001045810-26-000312"
    session.add(
        SecFiling(
            accession=missing,
            ticker="NVDA",
            cik="0001045810",
            form="8-K",
            accepted_at="2026-11-06T02:00:00Z",
            items="2.02",
            h3_candidate=True,
            h3_category="earnings",
            verified=True,
            text_outcome="confirmed",
            summary_plain=kept,
            hide_reason=None,
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/index.html",
        )
    )
    session.commit()
    session.close()

    commits = {"n": 0}
    real_commit = Session.commit

    def counted_commit(self, *args, **kwargs):
        commits["n"] += 1
        return real_commit(self, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", counted_commit)
    sec._redecide_from_cache()
    session = SessionLocal()
    changed = session.get(SecFiling, accession)
    assert changed.text_outcome == "unconfirmable"
    assert changed.hide_reason == "no_category"
    assert changed.summary_plain is None
    untouched = session.get(SecFiling, missing)
    assert untouched.text_outcome == "confirmed"
    assert untouched.summary_plain == kept
    assert untouched.h3_category == "earnings"
    assert untouched.hide_reason is None
    session.close()
    assert commits["n"] == 1

    commits["n"] = 0
    sec._redecide_from_cache()
    assert commits["n"] == 0
    session = SessionLocal()
    again = session.get(SecFiling, accession)
    assert again.hide_reason == "no_category"
    still = session.get(SecFiling, missing)
    assert still.summary_plain == kept
    session.close()


def test_api_responses_omit_hide_reason(client):
    user = client.post("/onboarding", json={"interests": ["gaming"]})
    assert user.status_code == 200
    user_id = user.json()["user_id"]
    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200

    from app.db import SessionLocal
    from app.models import SecFiling

    session = SessionLocal()
    session.add(
        SecFiling(
            accession="0001045810-26-000099",
            ticker="NVDA",
            cik="0001045810",
            form="8-K",
            accepted_at="2026-11-06T02:00:00Z",
            items="8.01",
            h3_candidate=True,
            verified=False,
            text_outcome="unconfirmable",
            hide_reason="no_category",
            filing_url="https://www.sec.gov/Archives/edgar/data/1045810/index.html",
            summary_plain=None,
        )
    )
    session.commit()
    session.close()

    for path in ("/cards", "/matches", "/updates"):
        response = client.get(path, params={"user_id": user_id})
        assert response.status_code == 200
        assert "hide_reason" not in response.text


def test_rules_version_redecides_an_old_row_once_from_cache(client, monkeypatch, tmp_path):
    import app.db as dbmod
    from app.models import SecFetchState, SecFiling
    from app.services import sec_filings as sec

    user = client.post("/onboarding", json={"interests": ["gaming"]})
    user_id = user.json()["user_id"]
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200

    with dbmod.ENGINE.begin() as connection:
        connection.exec_driver_sql("DROP TABLE sec_filings")
        connection.exec_driver_sql(
            """
            CREATE TABLE sec_filings (
                accession VARCHAR(32) PRIMARY KEY,
                ticker VARCHAR(32) NOT NULL,
                cik VARCHAR(10) NOT NULL,
                form VARCHAR(16) NOT NULL,
                filed_at VARCHAR(32),
                accepted_at VARCHAR(40),
                items TEXT,
                h3_candidate BOOLEAN,
                h3_category VARCHAR(32),
                filing_url TEXT,
                report_url TEXT,
                summary_plain TEXT,
                verified BOOLEAN,
                amends_accession VARCHAR(32),
                text_outcome VARCHAR(24)
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO sec_filings "
            "(accession, ticker, cik, form, accepted_at, items, h3_candidate, verified, text_outcome) "
            "VALUES ('0001045810-26-000077', 'NVDA', '0001045810', '8-K', "
            "'2026-11-06T02:00:00Z', '8.01', 1, 0, 'unconfirmable')"
        )
    dbmod.init_db()
    session = dbmod.SessionLocal()
    stored = session.get(SecFiling, "0001045810-26-000077")
    assert stored.hide_reason is None
    assert stored.text_outcome == "unconfirmable"
    session.close()

    cache = tmp_path / "sec" / "documents" / "0001045810-26-000077.json"
    cache.parent.mkdir(parents=True)
    text = "The company discussed ordinary operations in this current report. " * 5
    cache.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "data": [
                    {
                        "url": "https://www.sec.gov/Archives/edgar/data/1045810/body.htm",
                        "role": "main",
                        "exhibit": None,
                        "text": text,
                        "raw": "",
                        "too_long": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    fetched = []

    class _Json:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _n=None):
            return json.dumps(self.payload).encode("utf-8")

    def urlopen(request, timeout=30):
        fetched.append(request.full_url)
        if "company_tickers" in request.full_url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "submissions" in request.full_url:
            return _Json({"filings": {"recent": {"accessionNumber": []}}})
        raise AssertionError(request.full_url)

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    session = dbmod.SessionLocal()
    row = session.get(SecFiling, "0001045810-26-000077")
    assert row.text_outcome == "unconfirmable"
    assert row.hide_reason == "no_category"
    version = session.get(SecFetchState, sec.RULES_VERSION_KEY)
    assert version.note == sec.RULES_VERSION
    row.hide_reason = "sentinel"
    session.commit()
    session.close()
    fetched.clear()
    sec.refresh_liked_8k_filings()
    session = dbmod.SessionLocal()
    row = session.get(SecFiling, "0001045810-26-000077")
    assert row.text_outcome == "unconfirmable"
    assert row.hide_reason == "sentinel"
    session.close()
    assert all("Archives/edgar/data" not in url for url in fetched)
