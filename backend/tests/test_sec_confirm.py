"""Confirm 8-K categories from fixture text. HTTP is mocked. No live SEC calls."""

from __future__ import annotations

import json
import logging
import urllib.error

from fastapi.testclient import TestClient

from app.services.sec_text import build_summary, decide_filing, ny_dates

FILLER = "The company filed this report with the regulator on the date shown. " * 4
ACCEPTED = "2026-11-06T02:00:00Z"
EXHIBIT_URL = "https://www.sec.gov/Archives/edgar/data/1045810/ex99_1.htm"


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _like(client, user_id, ticker):
    response = client.post("/like", json={"user_id": user_id, "ticker": ticker})
    assert response.status_code == 200, response.text


def _doc(text, exhibit=None, url=EXHIBIT_URL, raw=None):
    return {
        "url": url,
        "role": "exhibit" if exhibit else "main",
        "exhibit": exhibit,
        "text": f"{text}\n{FILLER}",
        "raw": raw or "",
        "too_long": False,
    }


def _decide(items, docs, ticker="NVDA", form="8-K", accession="0001045810-26-000010"):
    return decide_filing(ticker=ticker, form=form, items=items, accession=accession, documents=docs)


def _line(decision, name="NVIDIA"):
    return build_summary(
        category=decision.get("h3_category"),
        form="8-K",
        accepted_at=ACCEPTED,
        name=name,
        fields=decision,
    )


def test_earnings_without_exhibit_or_blocked_exhibit_stays_hidden(client, monkeypatch, tmp_path):
    main = _doc(
        "Results for the quarter ended September 30, 2026 are furnished in Exhibit 99.1.",
        url="https://www.sec.gov/Archives/edgar/data/1045810/body.htm",
    )
    hidden = _decide(["2.02"], [main])
    assert hidden["h3_category"] is None
    assert hidden["verified"] is False
    assert hidden["figure"] is None
    assert hidden["measure"] is None

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    seen = []

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        if "company_tickers" in request.full_url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "CIK" in request.full_url:
            return _Json(_recent("body.htm"))
        if request.full_url.endswith("body.htm"):
            html = (
                "<html><body><p>Results for the quarter ended September 30, 2026 "
                "are furnished in Exhibit 99.1.</p>"
                "<table><tr><td>EX-99.1</td><td><a href='ex99_1.htm'>EX-99.1</a></td></tr></table>"
                f"{FILLER}</body></html>"
            )
            return _Html(html)
        raise urllib.error.HTTPError(request.full_url, 403, "no", hdrs=None, fp=None)

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    assert any(url.endswith("body.htm") for url in seen)
    assert sum("ex99_1" in url for url in seen) == 1
    row = _filing("0001045810-26-000099")
    assert row.h3_category is None
    assert row.figure is None
    assert row.verified is False
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert seen == []


def test_earnings_exhibit_confirms_quarter_and_one_figure():
    exhibit = _doc(
        "The company announced financial results for its fiscal 2026 first quarter ended "
        "December 27, 2025. Diluted earnings per share were $2.10.",
        exhibit="99.1",
    )
    decision = _decide(["2.02"], [_doc("See Exhibit 99.1.", url="https://www.sec.gov/Archives/edgar/data/1/body.htm"), exhibit])
    assert decision["h3_category"] == "earnings"
    assert decision["exhibit_url"] == EXHIBIT_URL
    assert decision["is_quarter"] is True
    assert decision["measure"] == "diluted earnings per share"
    assert decision["figure"] == "$2.10"
    line = _line(decision)
    assert line == (
        "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5. "
        "The company reported diluted earnings per share of $2.10."
    )


def test_earnings_prose_table_disagreement_leaves_figure_empty():
    raw = (
        "<table><tr><td>Net sales</td><td>114,477</td></tr></table>"
    )
    exhibit = _doc(
        "The company announced financial results for its fiscal 2026 first quarter ended "
        "December 27, 2025. The company posted quarterly revenue of $114.5 billion.",
        exhibit="99.1",
        raw=raw,
    )
    decision = _decide(["2.02"], [exhibit])
    assert decision["h3_category"] == "earnings"
    assert decision["is_quarter"] is True
    assert decision["measure"] is None
    assert decision["figure"] is None
    assert "Nov 5" in _line(decision)
    assert "114" not in _line(decision)


def test_guaranty_credit_and_lease_are_not_deals():
    for sentence in (
        "The Company entered into a guaranty agreement with a lender under a credit agreement.",
        "The Company entered into a credit agreement with a bank.",
        "The Company entered into a lease agreement for an office.",
    ):
        decision = _decide(["1.01", "2.01"], [_doc(sentence)])
        assert decision["h3_category"] is None
        assert decision["verified"] is False


def test_named_deal_stores_exact_fields():
    agreed = _decide(
        ["1.01"],
        [_doc("The Company entered into a definitive agreement to acquire Example Studios, Inc.")],
    )
    assert agreed["h3_category"] == "acquisition_sale"
    assert agreed["side"] == "acquirer"
    assert agreed["stage"] == "agreed"
    assert agreed["counterparty"] == "Example Studios, Inc"
    assert "agreed to acquire Example Studios, Inc" in _line(agreed)

    acquired = _decide(
        ["2.01"],
        [_doc("The Company agreed to be acquired by Northwind Holdings LLC.")],
    )
    assert acquired["side"] == "acquired"
    assert acquired["stage"] == "agreed"
    assert acquired["counterparty"] == "Northwind Holdings LLC"
    assert "agreed to be acquired by Northwind Holdings LLC" in _line(acquired)

    sold = _decide(
        ["1.01"],
        [_doc("The Company completed the sale of Map Business to Atlas Corp.")],
    )
    assert sold["side"] == "seller"
    assert sold["stage"] == "completed"
    assert sold["asset"] == "Map Business"
    assert sold["counterparty"] == "Atlas Corp"
    assert "completed the handover of Map Business to Atlas Corp" in _line(sold)


def test_compensation_and_election_are_not_leadership():
    pay = _decide(
        ["5.02"],
        [_doc("The Company approved an increase in the base salary and bonus of the chief financial officer.")],
    )
    assert pay["h3_category"] is None
    elected = _decide(
        ["5.02"],
        [_doc("At the annual meeting, stockholders elected the directors Jane Doe, John Smith, and Alex Lee.")],
    )
    assert elected["h3_category"] is None
    assert elected["verified"] is False


def test_named_officer_change_step_down_is_not_resigned():
    stepped = _decide(
        ["5.02"],
        [_doc("Jane Doe will step down as chief executive officer effective September 1, 2026.")],
    )
    assert stepped["h3_category"] == "leadership"
    assert stepped["person"] == "Jane Doe"
    assert stepped["role"] == "chief executive officer"
    assert stepped["lead_direction"] == "leaving"
    assert stepped["resigned_or_retired"] is False
    assert stepped["eff_date"] == "Sep 1"
    assert "will leave that role, starting Sep 1." in _line(stepped)
    assert "step down" not in _line(stepped)

    moved = _decide(
        ["5.02"],
        [_doc("John Smith will transition from the role of chief financial officer.")],
    )
    assert moved["person"] == "John Smith"
    assert moved["resigned_or_retired"] is False
    assert moved["eff_date"] is None
    assert "will leave that role." in _line(moved)

    joined = _decide(
        ["5.02"],
        [_doc("The Company appointed Ada Lovelace as chief financial officer.")],
    )
    assert joined["lead_direction"] == "joining"
    assert joined["resigned_or_retired"] is False
    assert joined["eff_date"] is None
    assert _line(joined) == "NVIDIA announced that Ada Lovelace will become its chief financial officer."


def test_negated_leadership_sentence_stays_hidden():
    text = "Jane Doe did not resign as chief executive officer."
    doc = _doc(text)
    assert len(doc["text"].encode("utf-8")) >= 200
    for sentence in (
        text,
        "The board did not announce that Jane Doe resigned as chief executive officer.",
        "Jane Doe will not resign as chief executive officer.",
    ):
        decision = _decide(["5.02"], [_doc(sentence)])
        assert decision["h3_category"] is None
        assert decision["verified"] is False
        assert decision["person"] is None
        assert _line(decision) is None
        assert "did not" not in (decision.get("person") or "")


def test_past_year_leadership_sentence_stays_hidden():
    for text in (
        "In 2019, Jane Doe resigned as chief financial officer.",
        "Jane Doe resigned as chief financial officer, a role held since 2019.",
    ):
        decision = _decide(
            ["5.02"],
            [_doc(text)],
            accession="0001045810-26-000010",
        )
        assert decision["h3_category"] is None
        assert decision["verified"] is False
        assert decision["person"] is None
        assert _line(decision) is None


def test_current_ceo_step_down_still_confirms():
    decision = _decide(
        ["5.02"],
        [_doc("Jane Doe resigned as chief executive officer.")],
        accession="0001045810-26-000010",
    )
    assert decision["h3_category"] == "leadership"
    assert decision["verified"] is True
    assert decision["person"] == "Jane Doe"
    assert decision["role"] == "chief executive officer"
    assert decision["lead_direction"] == "leaving"
    assert decision["resigned_or_retired"] is True
    assert _line(decision) == "NVIDIA announced that Jane Doe, its chief executive officer, will step down."


def test_named_executive_officer_without_a_title_uses_the_fallback():
    for phrase in (
        "a named executive officer",
        "an named executive officer",
        "its named executive officer",
        "the named executive officer",
        "named executive officer",
    ):
        decision = _decide(
            ["5.02"],
            [_doc(f"The Company appointed Pat Lee as {phrase}.")],
        )
        assert decision["h3_category"] == "leadership"
        assert decision["verified"] is True
        assert decision["person"] == "Pat Lee"
        assert decision["role"] is None
        line = _line(decision)
        assert line == "NVIDIA announced a leadership change in an SEC filing on Nov 5."
        assert "named executive" not in line
        assert "Pat Lee" not in line


def test_named_executive_officer_uses_a_real_title():
    for text in (
        "The Company appointed Pat Lee as chief operating officer and a named executive officer.",
        "The Company appointed Pat Lee as a named executive officer and chief operating officer.",
    ):
        decision = _decide(["5.02"], [_doc(text)])
        assert decision["h3_category"] == "leadership"
        assert decision["person"] == "Pat Lee"
        assert decision["role"] == "chief operating officer"
        assert decision["lead_direction"] == "joining"
        assert decision["resigned_or_retired"] is False
        line = _line(decision)
        assert line == "NVIDIA announced that Pat Lee will become its chief operating officer."
        assert "named executive" not in line


def test_guidance_without_outlook_text_is_hidden():
    decision = _decide(
        ["7.01", "8.01"],
        [_doc("The Company declared a quarterly dividend of $0.25 per share.")],
    )
    assert decision["h3_category"] is None
    assert decision["summary_plain"] is None


def test_mixed_guidance_is_unclear():
    decision = _decide(
        ["7.01"],
        [_doc("The Company raised its revenue outlook for the next quarter and lowered its earnings outlook for the full year.")],
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["hide_reason"] == "ambiguous"
    assert decision["text_outcome"] != "confirmed"
    assert _line(decision) is None


def test_two_categories_on_one_accession_stay_hidden():
    text = (
        "The company announced financial results for its fiscal 2026 first quarter ended "
        "December 27, 2025. Diluted earnings per share were $2.10. "
        "The Company also raised its outlook for the next quarter."
    )
    decision = _decide(["2.02", "7.01"], [_doc(text, exhibit="99.1")])
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["summary_plain"] is None


def test_amendment_is_its_own_record_and_is_not_confirmed():
    text = (
        "This amendment amends the report filed under accession 0001140361-26-015711. "
        "Jane Doe will step down as chief executive officer."
    )
    accession = "0001140361-26-035325"
    decision = _decide(["5.02"], [_doc(text)], form="8-K/A", accession=accession)
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["amends_accession"] == "0001140361-26-015711"
    assert decision["amends_accession"] != accession


def test_new_york_date_across_utc_midnight():
    assert ny_dates("2026-11-06T02:00:00Z") == ("2026-11-05", "Nov 5")
    assert ny_dates("2026-11-06T02:00Z") == ("2026-11-05", "Nov 5")
    decision = _decide(
        ["2.02"],
        [_doc(
            "The company announced financial results for the year ended September 30, 2026. "
            "Net income was $4.00 billion.",
            exhibit="99.1",
        )],
    )
    assert decision["is_quarter"] is False
    line = _line(decision)
    assert "latest results" in line
    assert "quarterly" not in line
    assert "Nov 5" in line
    assert "Nov 6" not in line


def test_skip_list_and_block_do_not_invent_a_category(client, monkeypatch, tmp_path):
    text = (
        "The company announced financial results for its fiscal 2026 first quarter ended "
        "December 27, 2025. Diluted earnings per share were $2.10."
    )
    for ticker in ("NTES", "SONY", "SPOT", "TM", "RACE"):
        decision = _decide(["2.02"], [_doc(text)], ticker=ticker)
        assert decision["h3_category"] is None
        assert decision["verified"] is False

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "AMD")
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    seen = []

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        if "company_tickers" in request.full_url:
            return _Json({"0": {"cik_str": 2488, "ticker": "AMD", "title": "AMD"}})
        raise urllib.error.HTTPError(request.full_url, 429, "no", hdrs=None, fp=None)

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    assert _all_filings() == []
    from app.db import SessionLocal
    from app.models import SecFetchState

    session = SessionLocal()
    state = session.get(SecFetchState, "backoff")
    session.close()
    assert state is not None and state.note == "HTTP 429"
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert seen == []


def test_empty_fields_use_fallback_and_lines_have_no_advice_words():
    decision = _decide(
        ["1.01"],
        [_doc("The Company entered into a definitive agreement to acquire Example Studios, Inc.")],
    )
    decision["stage"] = None
    line = _line(decision)
    assert line == "NVIDIA reported a major deal in an SEC filing on Nov 5. The filing has the details."
    banned = ("buy", "sell", "hold", "soared", "crashed", "plunged", "skyrocketed", "tanked", "blockbuster", "shock")
    for word in banned:
        assert word not in line.lower()
    assert "time to" not in line.lower()
    assert "big move" not in line.lower()


def test_three_people_use_the_fallback_leadership_line():
    text = (
        "The Company appointed Jane Doe as chief executive officer effective September 1, 2026. "
        "The Company appointed John Smith as chief financial officer. "
        "Mary Jones will step down as board chair."
    )
    decision = _decide(["5.02"], [_doc(text)])
    assert decision["h3_category"] == "leadership"
    assert decision["person"] is None
    line = _line(decision)
    assert line == "NVIDIA announced a leadership change in an SEC filing on Nov 5."
    assert "Jane Doe" not in line


def test_deal_described_only_under_8_01_is_hidden():
    decision = _decide(
        ["8.01"],
        [_doc("The Company entered into a definitive agreement to acquire Example Studios, Inc.")],
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False


def test_size_cutoff_and_three_document_limit(client, monkeypatch, tmp_path, caplog):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    seen = []
    huge_reads = {"n": 0}

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        url = request.full_url
        if "company_tickers" in url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "CIK" in url:
            return _Json(_two_filings())
        if url.endswith("many.htm"):
            rows = "".join(
                f"<tr><td>{label}</td><td><a href='{name}'>{label}</a></td></tr>"
                for name, label in (
                    ("ex10_1.htm", "EX-10.1"),
                    ("ex99_2.htm", "EX-99.2"),
                    ("ex21_1.htm", "EX-21.1"),
                    ("ex99_1.htm", "EX-99.1"),
                )
            )
            return _Html(f"<html><body><table>{rows}</table>{FILLER}</body></html>")
        if url.endswith("huge.htm"):
            return _Huge(huge_reads)
        if url.endswith("ex99_1.htm"):
            return _Html("<html><body><p>Exhibit text.</p></body></html>")
        if "ex99_2" in url or "ex10_1" in url or "ex21_1" in url:
            return _Html("<html><body><p>Other exhibit.</p></body></html>")
        raise AssertionError(url)

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    with caplog.at_level(logging.INFO, logger="fund.sec"):
        sec.refresh_liked_8k_filings()
    many_docs = [
        url
        for url in seen
        if url.endswith("many.htm") or "ex99_" in url or "ex10_" in url or "ex21_" in url
    ]
    assert [url.rsplit("/", 1)[-1] for url in many_docs] == ["many.htm", "ex99_1.htm", "ex10_1.htm"]
    assert huge_reads["n"] < 40
    assert "UNIQUE_FILING_TEXT" not in caplog.text
    assert "SEC document bytes=" in caplog.text
    huge = _filing("0001045810-26-000050")
    assert huge.h3_category is None
    assert huge.verified is False
    assert huge.text_outcome == "unconfirmable"
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert not any(url.endswith("huge.htm") for url in seen)


def test_updates_filings_are_liked_confirmed_and_offline(client, monkeypatch):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    other = _onboard(client, ["gaming"])
    _like(client, other, "AMD")
    _insert_filing(
        accession="0001045810-26-000010",
        ticker="NVDA",
        accepted_at="2026-11-06T02:00:00Z",
        line="NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.",
        verified=True,
        category="earnings",
    )
    _insert_filing(
        accession="0001045810-26-000011",
        ticker="NVDA",
        accepted_at="2026-11-01T15:00:00Z",
        line="Hidden because it is not confirmed.",
        verified=False,
        category=None,
    )
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("network")
        raise AssertionError("network during GET /updates")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.sec_filings.urllib.request.urlopen", boom)
    body = client.get("/updates", params={"user_id": user_id}).json()
    assert calls == []
    assert sorted(body) == ["alerts", "digest", "filings", "unseen_count", "updates"]
    assert len(body["filings"]) == 1
    assert body["filings"][0] == {
        "ticker": "NVDA",
        "short_name": "NVIDIA",
        "accession": "0001045810-26-000010",
        "date_ny": "2026-11-05",
        "line": "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.",
        "filing_url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/0001045810-26-000010-index.html",
    }
    other_body = client.get("/updates", params={"user_id": other}).json()
    assert other_body["filings"] == []


def test_updates_omit_filings_whose_url_is_not_on_sec(client, monkeypatch):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    good = (
        "https://www.sec.gov/Archives/edgar/data/1045810/"
        "000104581026000010/0001045810-26-000010-index.html"
    )
    _insert_filing(
        "0001045810-26-000010",
        "NVDA",
        "2026-11-06T02:00:00Z",
        "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.",
        True,
        "earnings",
        filing_url=good,
    )
    _insert_filing(
        "0001045810-26-000012",
        "NVDA",
        "2026-11-07T15:00:00Z",
        "NVIDIA shared its latest results in an SEC filing on Nov 7.",
        True,
        "earnings",
        filing_url="https://example.com/not-the-sec",
    )
    _insert_filing(
        "0001045810-26-000013",
        "NVDA",
        "2026-11-08T15:00:00Z",
        "NVIDIA shared its latest results in an SEC filing on Nov 8.",
        True,
        "earnings",
        filing_url="http://www.sec.gov/Archives/edgar/data/1045810/not-https.htm",
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("network during GET /updates")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.sec_filings.urllib.request.urlopen", boom)
    body = client.get("/updates", params={"user_id": user_id}).json()
    assert sorted(body) == ["alerts", "digest", "filings", "unseen_count", "updates"]
    assert [item["accession"] for item in body["filings"]] == ["0001045810-26-000010"]
    assert body["filings"][0] == {
        "ticker": "NVDA",
        "short_name": "NVIDIA",
        "accession": "0001045810-26-000010",
        "date_ny": "2026-11-05",
        "line": "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.",
        "filing_url": good,
    }


def test_duplicate_lines_keep_both_records_and_show_the_later_one(client):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    line = "NVIDIA shared its latest results in an SEC filing on Nov 1."
    _insert_filing("0001045810-26-000021", "NVDA", "2026-11-01T15:00:00Z", line, True, "earnings")
    _insert_filing("0001045810-26-000022", "NVDA", "2026-11-03T15:00:00Z", line, True, "earnings")
    _insert_filing(
        "0001045810-26-000023",
        "NVDA",
        "2026-10-20T15:00:00Z",
        line,
        True,
        "earnings",
    )
    body = client.get("/updates", params={"user_id": user_id}).json()
    shown = [item["accession"] for item in body["filings"]]
    assert shown[0] == "0001045810-26-000022"
    assert "0001045810-26-000021" not in shown
    assert "0001045810-26-000023" in shown
    assert len(_all_filings()) == 3


def test_legacy_databases_from_main_and_k2_still_open(tmp_path, monkeypatch):
    import app.db as dbmod
    from app.main import create_app
    from app.models import Company, SecFiling

    current = tmp_path / "from-k2.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + current.resolve().as_posix())
    monkeypatch.setenv("FINNHUB_API_KEY", "")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "0")
    monkeypatch.setenv("SEC_USER_AGENT", "")
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
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
                    amends_accession VARCHAR(32)
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO sec_filings (accession, ticker, cik, form, h3_candidate, verified) "
                "VALUES ('0001045810-26-000001', 'NVDA', '0001045810', '8-K', 0, 0)"
            )
        dbmod.init_db()
        session = dbmod.SessionLocal()
        assert session.get(Company, "NVDA").company_name == "NVIDIA Corporation"
        stored = session.get(SecFiling, "0001045810-26-000001")
        assert stored is not None
        assert stored.measure is None
        assert stored.text_outcome is None
        session.close()

    older = tmp_path / "from-bcb25e4.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + older.resolve().as_posix())
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        with dbmod.ENGINE.begin() as connection:
            connection.exec_driver_sql("DROP TABLE sec_filings")
            connection.exec_driver_sql("DROP TABLE sec_fetch_state")
        dbmod.init_db()
        session = dbmod.SessionLocal()
        assert session.get(Company, "NVDA").company_name == "NVIDIA Corporation"
        session.close()
        assert client.get("/health").status_code == 200


def test_network_does_not_hold_a_database_session(client, monkeypatch, tmp_path):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    from app.services import sec_filings as sec

    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    active = {"n": 0}
    original = sec.dbmod.SessionLocal

    def factory():
        session = original()
        active["n"] += 1
        close = session.close

        def wrapped():
            active["n"] -= 1
            return close()

        session.close = wrapped
        return session

    monkeypatch.setattr(sec.dbmod, "SessionLocal", factory)
    sec._last_request_at = sec.time.monotonic()

    def sleep(_seconds):
        assert active["n"] == 0

    monkeypatch.setattr(sec.time, "sleep", sleep)

    def urlopen(request, timeout=30):
        assert active["n"] == 0
        if "company_tickers" in request.full_url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "CIK" in request.full_url:
            return _Json(_recent("body.htm"))
        raise urllib.error.URLError("stop after metadata")

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    sec.refresh_liked_8k_filings()
    assert active["n"] == 0


class _Json:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n=None):
        return json.dumps(self.payload).encode("utf-8")


class _Html:
    def __init__(self, text):
        self.payload = text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n=None):
        payload, self.payload = self.payload, b""
        return payload


class _Huge:
    def __init__(self, counter):
        self.counter = counter
        self.sent = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, n=65536):
        self.counter["n"] += 1
        if self.counter["n"] > 80:
            return b""
        self.sent += n
        if self.sent > 2_000_000:
            marker = b"UNIQUE_FILING_TEXT"
            return marker + (b"x" * max(n - len(marker), 0))
        return b"a" * n


def _recent(primary):
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-26-000099"],
                "form": ["8-K"],
                "filingDate": ["2026-11-05"],
                "acceptanceDateTime": ["2026-11-06T02:00:00.000Z"],
                "items": ["2.02"],
                "primaryDocument": [primary],
            }
        }
    }


def _two_filings():
    return {
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-26-000040", "0001045810-26-000050"],
                "form": ["8-K", "8-K"],
                "filingDate": ["2026-11-05", "2026-11-05"],
                "acceptanceDateTime": ["2026-11-06T02:00:00.000Z", "2026-11-06T02:00:00.000Z"],
                "items": ["2.02", "2.02"],
                "primaryDocument": ["many.htm", "huge.htm"],
            }
        }
    }


def _filing(accession):
    from app.db import SessionLocal
    from app.models import SecFiling

    session = SessionLocal()
    row = session.get(SecFiling, accession)
    session.expunge(row)
    session.close()
    return row


def _all_filings():
    from app.db import SessionLocal
    from app.models import SecFiling

    session = SessionLocal()
    rows = session.query(SecFiling).all()
    session.close()
    return rows


def _insert_filing(accession, ticker, accepted_at, line, verified, category, filing_url=None):
    from app.db import SessionLocal
    from app.models import SecFiling

    if filing_url is None:
        filing_url = (
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            f"{accession.replace('-', '')}/{accession}-index.html"
        )
    session = SessionLocal()
    session.add(
        SecFiling(
            accession=accession,
            ticker=ticker,
            cik="0001045810",
            form="8-K",
            accepted_at=accepted_at,
            items="2.02",
            h3_candidate=True,
            h3_category=category,
            filing_url=filing_url,
            summary_plain=line,
            verified=verified,
            text_outcome="confirmed" if verified else "unconfirmable",
        )
    )
    session.commit()
    session.close()
