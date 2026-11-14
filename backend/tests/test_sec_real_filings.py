"""Real 8-K fixtures. HTTP is mocked. No live SEC calls."""

from __future__ import annotations

import json
import logging
import urllib.error
from datetime import date, timedelta
from pathlib import Path

from app.services.sec_filings import (
    CANDIDATE_LIMIT_PER_TICKER,
    CANDIDATE_LOOKBACK_DAYS,
    _candidate_accessions,
    _exhibit_number,
    _fetch_documents,
    _find_exhibits,
)
from app.services.sec_text import build_summary, decide_filing, plain_text

FIXTURES = Path(__file__).parent / "fixtures" / "sec"
AAPL_EXHIBIT = (
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/"
    "a8-kex991q4202609262026.htm"
)
MSFT_EXHIBIT = (
    "https://www.sec.gov/Archives/edgar/data/789019/000119312526436122/msft-ex99_1.htm"
)
NVDA_EXHIBIT = (
    "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000073/q2fy27pr.htm"
)
UBER_EXHIBIT = (
    "https://www.sec.gov/Archives/edgar/data/1543151/000154315126000011/"
    "uberq425earningspressrelea.htm"
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _doc(text: str, *, url: str, exhibit: str | None = None, raw: str = "") -> dict:
    return {
        "url": url,
        "role": "exhibit" if exhibit else "main",
        "exhibit": exhibit,
        "text": text,
        "raw": raw,
        "too_long": False,
    }


def _line(decision, *, name: str, accepted_at: str, form: str = "8-K") -> str | None:
    return build_summary(
        category=decision.get("h3_category"),
        form=form,
        accepted_at=accepted_at,
        name=name,
        fields=decision,
    )


class _Html:
    def __init__(self, text: str):
        self.payload = text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n=None):
        payload, self.payload = self.payload, b""
        return payload


class _Json:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _n=None):
        return json.dumps(self.payload).encode("utf-8")


def _fetch(monkeypatch, sec, routes: dict[str, str], report_url: str, filing_url: str) -> list[dict]:
    def urlopen(request, timeout=30):
        for fragment, body in routes.items():
            if fragment in request.full_url:
                return _Html(body)
        raise AssertionError(request.full_url)

    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    return _fetch_documents(
        {"report_url": report_url, "filing_url": filing_url, "accession": "test"},
        "fun(d) contact@example.com",
    )


def test_plain_text_unescapes_entities_and_nbsp_before_matching():
    raw = (
        "<p>Exhibit&#160;99.1 was filed on September&#160;1. "
        "O&#8217;Brien and Jos&eacute; said &#8220;hello&#8221; &amp; more.&nbsp;</p>"
    )
    text = plain_text(raw)
    assert "Exhibit 99.1" in text
    assert "September 1" in text
    assert "O\u2019Brien" in text
    assert "José" in text
    assert "\u201chello\u201d" in text
    assert "&" in text
    assert "&#" not in text
    assert "&nbsp;" not in text
    assert "\xa0" not in text


def test_filename_fallback_and_index_type_column():
    assert _exhibit_number("Press release", "a8-kex991q4202609262026.htm") == "99.1"
    assert _exhibit_number("Press release", "msft-ex99_1.htm") == "99.1"
    assert _exhibit_number("Press Release, dated", "q2fy27pr.htm") is None
    assert _exhibit_number("Press release dated February 4, 2026", "uberq425earningspressrelea.htm") is None

    aapl_base = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/aapl-20261102.htm"
    aapl = _find_exhibits(_read("aapl-0000320193-26-000024-body.html"), aapl_base)
    assert ("99.1", AAPL_EXHIBIT) in aapl

    msft_base = "https://www.sec.gov/Archives/edgar/data/789019/000119312526436122/msft-20261028.htm"
    msft = _find_exhibits(_read("msft-0001193125-26-436122-body.html"), msft_base)
    assert ("99.1", MSFT_EXHIBIT) in msft

    nvda_index = (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000073/"
        "0001045810-26-000073-index.html"
    )
    nvda_body = _find_exhibits(
        _read("nvda-0001045810-26-000073-body.html"),
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000073/nvda-20260826.htm",
    )
    assert all(number != "99.1" for number, _url in nvda_body)
    nvda = _find_exhibits(_read("nvda-0001045810-26-000073-index.html"), nvda_index)
    assert ("99.1", NVDA_EXHIBIT) in nvda


def test_aapl_000024_earnings_line_includes_diluted_eps(monkeypatch):
    from app.services import sec_filings as sec

    report = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/aapl-20261102.htm"
    index = (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/"
        "0000320193-26-000024-index.html"
    )
    docs = _fetch(
        monkeypatch,
        sec,
        {
            "aapl-20261102.htm": _read("aapl-0000320193-26-000024-body.html"),
            "a8-kex991q4202609262026.htm": _read("aapl-0000320193-26-000024-ex991.html"),
        },
        report,
        index,
    )
    assert any(doc.get("exhibit") == "99.1" and doc.get("url") == AAPL_EXHIBIT for doc in docs)
    decision = decide_filing(
        ticker="AAPL",
        form="8-K",
        items=["2.02", "9.01"],
        accession="0000320193-26-000024",
        documents=docs,
    )
    assert decision["h3_category"] == "earnings"
    assert decision["verified"] is True
    assert decision["hide_reason"] is None
    assert decision["is_quarter"] is True
    assert decision["measure"] == "diluted earnings per share"
    assert decision["figure"] == "$2.10"
    assert _line(decision, name="Apple", accepted_at="2026-11-02T21:30:23.000Z") == (
        "Apple shared its quarterly results in an SEC filing on Nov 2. "
        "The company reported diluted earnings per share of $2.10."
    )


def test_aapl_015711_three_people_use_the_leadership_fallback():
    text = plain_text(_read("aapl-0001140361-26-015711.txt"))
    assert len(text.encode("utf-8")) >= 200
    decision = decide_filing(
        ticker="AAPL",
        form="8-K",
        items=["5.02"],
        accession="0001140361-26-015711",
        documents=[_doc(text, url="https://www.sec.gov/Archives/edgar/data/320193/000114036126015711/ef20071035_8k.htm")],
    )
    assert decision["h3_category"] == "leadership"
    assert decision["verified"] is True
    assert decision["person"] is None
    assert decision["hide_reason"] is None
    line = _line(decision, name="Apple", accepted_at="2026-04-20T21:29:51Z")
    assert line == "Apple announced a leadership change in an SEC filing on Apr 20."
    assert "Tim Cook" not in line
    assert "John Ternus" not in line


def test_real_leadership_wording_for_transition_appointment_step_down_and_assume():
    cases = (
        (
            "Tim Cook will transition from his role as chief executive officer effective September 1, 2026.",
            "Tim Cook",
            "chief executive officer",
            "leaving",
            False,
            "Sep 1",
        ),
        (
            "The Board appointed John Ternus, Senior Vice President of Hardware Engineering, as chief executive officer.",
            "John Ternus",
            "chief executive officer",
            "joining",
            False,
            None,
        ),
        (
            "Jane Doe will step down from her role as chief financial officer.",
            "Jane Doe",
            "chief financial officer",
            "leaving",
            False,
            None,
        ),
        (
            "Balaji Krishnamurthy, currently Vice President, Strategic Finance, will assume the role of chief financial officer.",
            "Balaji Krishnamurthy",
            "chief financial officer",
            "joining",
            False,
            None,
        ),
    )
    for sentence, person, role, direction, resigned, eff in cases:
        decision = decide_filing(
            ticker="AAPL",
            form="8-K",
            items=["5.02"],
            accession="0001140361-26-015711",
            documents=[_doc(sentence + (" The board recorded the change in this report." * 3), url="https://www.sec.gov/x.htm")],
        )
        assert decision["h3_category"] == "leadership", sentence
        assert decision["person"] == person
        assert decision["role"] == role
        assert decision["lead_direction"] == direction
        assert decision["resigned_or_retired"] is resigned
        assert decision["eff_date"] == eff

    hidden = decide_filing(
        ticker="AAPL",
        form="8-K",
        items=["5.02"],
        accession="0001140361-26-015711",
        documents=[_doc(
            "Jane Doe will not transition from her role as chief executive officer. "
            + ("The board recorded the discussion in this report. " * 3),
            url="https://www.sec.gov/x.htm",
        )],
    )
    assert hidden["h3_category"] is None
    assert hidden["person"] is None


def test_nvda_000073_hides_for_two_categories_after_exhibit_is_found(monkeypatch):
    from app.services import sec_filings as sec

    report = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000073/nvda-20260826.htm"
    index = (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000073/"
        "0001045810-26-000073-index.html"
    )
    docs = _fetch(
        monkeypatch,
        sec,
        {
            "nvda-20260826.htm": _read("nvda-0001045810-26-000073-body.html"),
            "0001045810-26-000073-index.html": _read("nvda-0001045810-26-000073-index.html"),
            "q2fy27pr.htm": _read("nvda-0001045810-26-000073-ex991.html"),
        },
        report,
        index,
    )
    exhibit = next(doc for doc in docs if doc.get("exhibit") == "99.1")
    assert exhibit["url"] == NVDA_EXHIBIT
    assert "108.0 billion" in exhibit["text"]
    decision = decide_filing(
        ticker="NVDA",
        form="8-K",
        items=["2.02"],
        accession="0001045810-26-000073",
        documents=docs,
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["hide_reason"] == "two_categories"
    assert _line(decision, name="NVIDIA", accepted_at="2026-08-26T20:21:19Z") is None


def test_uber_000011_hides_for_two_categories_after_exhibit_is_found(monkeypatch):
    from app.services import sec_filings as sec

    report = "https://www.sec.gov/Archives/edgar/data/1543151/000154315126000011/uber-20260130.htm"
    index = (
        "https://www.sec.gov/Archives/edgar/data/1543151/000154315126000011/"
        "0001543151-26-000011-index.html"
    )
    docs = _fetch(
        monkeypatch,
        sec,
        {
            "uber-20260130.htm": _read("uber-0001543151-26-000011-body.html"),
            "0001543151-26-000011-index.html": _read("uber-0001543151-26-000011-index.html"),
            "uberq425earningspressrelea.htm": _read("uber-0001543151-26-000011-ex991.html"),
        },
        report,
        index,
    )
    exhibit = next(doc for doc in docs if doc.get("exhibit") == "99.1")
    assert exhibit["url"] == UBER_EXHIBIT
    decision = decide_filing(
        ticker="UBER",
        form="8-K",
        items=["2.02", "5.02"],
        accession="0001543151-26-000011",
        documents=docs,
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["hide_reason"] == "two_categories"
    assert decision["person"] is None
    assert _line(decision, name="Uber", accepted_at="2026-02-04T11:56:12Z") is None


def test_msft_436122_shows_quarterly_results_on_oct_28():
    body = plain_text(_read("msft-0001193125-26-436122-body.html"))
    exhibit = plain_text(_read("msft-0001193125-26-436122-ex991.txt"))
    found = _find_exhibits(
        _read("msft-0001193125-26-436122-body.html"),
        "https://www.sec.gov/Archives/edgar/data/789019/000119312526436122/msft-20261028.htm",
    )
    assert ("99.1", MSFT_EXHIBIT) in found
    decision = decide_filing(
        ticker="MSFT",
        form="8-K",
        items=["2.02", "9.01"],
        accession="0001193125-26-436122",
        documents=[
            _doc(body, url="https://www.sec.gov/Archives/edgar/data/789019/000119312526436122/msft-20261028.htm"),
            _doc(exhibit, url=MSFT_EXHIBIT, exhibit="99.1"),
        ],
    )
    assert decision["h3_category"] == "earnings"
    assert decision["verified"] is True
    assert decision["hide_reason"] is None
    assert decision["is_quarter"] is True
    assert _line(decision, name="Microsoft", accepted_at="2026-10-28T20:30:00Z") == (
        "Microsoft shared its quarterly results in an SEC filing on Oct 28."
    )


def test_hidden_real_filings_stay_hidden():
    cases = (
        ("nvda-0001045810-26-000069.txt", "NVDA", "8-K", ["1.01", "7.01"], "0001045810-26-000069"),
        ("nvda-0001045810-26-000078.txt", "NVDA", "8-K", ["8.01"], "0001045810-26-000078"),
        ("msft-0001193125-26-448357.txt", "MSFT", "8-K", ["5.02"], "0001193125-26-448357"),
    )
    for name, ticker, form, items, accession in cases:
        text = plain_text(_read(name))
        assert len(text.encode("utf-8")) >= 200
        decision = decide_filing(
            ticker=ticker,
            form=form,
            items=items,
            accession=accession,
            documents=[_doc(text, url=f"https://www.sec.gov/Archives/edgar/data/x/{accession}.htm")],
        )
        assert decision["h3_category"] is None, name
        assert decision["verified"] is False
        assert decision["hide_reason"] is None
        assert _line(decision, name="NVIDIA", accepted_at="2026-11-01T16:00:00Z") is None


def test_msft_224155_uses_the_effective_board_date():
    text = plain_text(_read("msft-0001193125-26-224155.txt"))
    assert "effective May 13, 2026" in text
    assert "Carmine Di Sibio" in text
    decision = decide_filing(
        ticker="MSFT",
        form="8-K",
        items=["5.02", "9.01"],
        accession="0001193125-26-224155",
        documents=[_doc(
            text,
            url="https://www.sec.gov/Archives/edgar/data/789019/000119312526224155/d125909d8k.htm",
        )],
    )
    assert decision["person"] == "Carmine Di Sibio"
    assert decision["eff_date"] == "May 13"
    assert decision["eff_year"] == 2026
    line = _line(decision, name="Microsoft", accepted_at="2026-05-14T16:28:48Z")
    assert line == "Microsoft announced that Carmine Di Sibio joined its board of directors on May 13."
    assert "May 14" not in line


def test_aapl_035325_amendment_does_not_guess_an_accession():
    raw = _read("aapl-0001140361-26-035325.txt")
    assert "April 20, 2026" in raw
    assert "0001140361-26-015711" not in raw
    text = plain_text(raw)
    decision = decide_filing(
        ticker="AAPL",
        form="8-K/A",
        items=["5.02"],
        accession="0001140361-26-035325",
        documents=[_doc(text, url="https://www.sec.gov/Archives/edgar/data/320193/000114036126035325/ef20081427_8ka.htm")],
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["amends_accession"] is None
    assert _line(decision, name="Apple", accepted_at="2026-09-01T20:30:35Z", form="8-K/A") is None


def test_outlook_on_item_202_alone_is_two_categories():
    text = (
        "The company announced financial results for its fiscal 2026 first quarter ended "
        "December 27, 2025. Diluted earnings per share were $2.10. "
        "The Company also raised its outlook for the next quarter. "
        + ("The filing gives no other completed-period figure. " * 4)
    )
    decision = decide_filing(
        ticker="NVDA",
        form="8-K",
        items=["2.02"],
        accession="0001045810-26-000073",
        documents=[_doc(text, url="https://www.sec.gov/Archives/edgar/data/1/ex.htm", exhibit="99.1")],
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["hide_reason"] == "two_categories"


def test_candidate_cap_uses_the_shared_constants_and_logs_only_the_count(client, monkeypatch, tmp_path, caplog):
    assert CANDIDATE_LOOKBACK_DAYS == 365
    assert CANDIDATE_LIMIT_PER_TICKER == 10
    from app.services import sec_filings as sec

    monkeypatch.setattr(sec, "_utc_today", lambda: date(2026, 11, 10))
    recent_same_day = {
        "accessionNumber": [f"0001045810-26-{index:06d}" for index in range(1, 12)],
        "form": ["8-K"] * 11,
        "filingDate": ["2026-11-10"] * 11,
        "acceptanceDateTime": ["2026-11-10T18:00:00.000Z"] * 11,
        "items": ["2.02"] * 11,
        "primaryDocument": ["body.htm"] * 11,
    }
    chosen = _candidate_accessions(recent_same_day)
    assert chosen == {f"0001045810-26-{index:06d}" for index in range(2, 12)}
    boundary = {
        "accessionNumber": ["0001045810-25-000100", "0001045810-25-000099"],
        "form": ["8-K", "8-K"],
        "filingDate": ["2025-11-10", "2025-11-09"],
        "acceptanceDateTime": ["2025-11-10T18:00:00.000Z", "2025-11-09T18:00:00.000Z"],
        "items": ["2.02", "2.02"],
        "primaryDocument": ["new.htm", "old.htm"],
    }
    assert _candidate_accessions(boundary) == {"0001045810-25-000100"}

    monkeypatch.setattr(sec, "CANDIDATE_LOOKBACK_DAYS", 30)
    monkeypatch.setattr(sec, "CANDIDATE_LIMIT_PER_TICKER", 2)
    today = date(2026, 11, 10)
    dated = [
        ("0001045810-26-000011", today.isoformat(), "2.02"),
        ("0001045810-26-000010", (today - timedelta(days=1)).isoformat(), "2.02"),
        ("0001045810-26-000009", (today - timedelta(days=9)).isoformat(), "2.02"),
        ("0001045810-26-000008", (today - timedelta(days=31)).isoformat(), "2.02"),
        ("0001045810-26-000007", today.isoformat(), "9.01"),
    ]
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": [row[0] for row in dated],
                "form": ["8-K"] * len(dated),
                "filingDate": [row[1] for row in dated],
                "acceptanceDateTime": [f"{row[1]}T18:00:00.000Z" for row in dated],
                "items": [row[2] for row in dated],
                "primaryDocument": ["body.htm"] * len(dated),
            }
        }
    }

    user = client.post("/onboarding", json={"interests": ["gaming"]})
    assert user.status_code == 200
    user_id = user.json()["user_id"]
    liked = client.post("/like", json={"user_id": user_id, "ticker": "NVDA"})
    assert liked.status_code == 200
    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)

    def urlopen(request, timeout=30):
        url = request.full_url
        if "company_tickers" in url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "CIK" in url:
            return _Json(payload)
        return _Html("<html><body><p>UNIQUE_FILING_TEXT should never be logged.</p></body></html>")

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)
    with caplog.at_level(logging.INFO, logger="fund.sec"):
        sec.refresh_liked_8k_filings()
    queued = [record.getMessage() for record in caplog.records if "queued=" in record.getMessage()]
    assert queued == ["SEC candidate filings queued=2"]
    assert "UNIQUE_FILING_TEXT" not in caplog.text
    from app.db import SessionLocal
    from app.models import SecFiling

    session = SessionLocal()
    rows = {row.accession: row.h3_candidate for row in session.query(SecFiling).all()}
    session.close()
    assert rows["0001045810-26-000011"] is True
    assert rows["0001045810-26-000010"] is True
    assert rows["0001045810-26-000009"] is False
    assert rows["0001045810-26-000008"] is False
    assert rows["0001045810-26-000007"] is False


def test_msft_380280_restated_outlook_stays_hidden():
    body = plain_text(_read("msft-0001193125-26-380280-body.txt"))
    exhibit = plain_text(_read("msft-0001193125-26-380280-ex991.txt"))
    assert "As provided on" in exhibit
    assert "No change to outlook" in exhibit
    assert "$89.85 to $90.95 billion" in exhibit
    decision = decide_filing(
        ticker="MSFT",
        form="8-K",
        items=["7.01", "9.01"],
        accession="0001193125-26-380280",
        documents=[
            _doc(body, url="https://www.sec.gov/Archives/edgar/data/789019/000119312526380280/d291965d8k.htm"),
            _doc(
                exhibit,
                url="https://www.sec.gov/Archives/edgar/data/789019/000119312526380280/d291965dex991.htm",
                exhibit="99.1",
            ),
        ],
    )
    assert decision["h3_category"] is None
    assert decision["verified"] is False
    assert decision["hide_reason"] == "ambiguous"
    assert decision["figure"] is None
    line = _line(decision, name="Microsoft", accepted_at="2026-09-02T20:30:24Z")
    assert line is None
    assert "$89.85" not in (line or "")

    restated = (
        "The Company will reiterate its outlook for the next quarter. "
        "Revenue is expected to be $10 billion. "
        + ("The filing repeats an earlier view. " * 4)
    )
    again = decide_filing(
        ticker="MSFT",
        form="8-K",
        items=["7.01"],
        accession="0001193125-26-380280",
        documents=[_doc(restated, url="https://www.sec.gov/Archives/edgar/data/789019/000119312526380280/ex.htm", exhibit="99.1")],
    )
    assert again["h3_category"] is None
    assert again["hide_reason"] == "ambiguous"
    assert _line(again, name="Microsoft", accepted_at="2026-09-02T20:30:24Z") is None


def test_fresh_outlook_range_is_copied_verbatim():
    exhibit = (
        "The Company raised its outlook for the next quarter. "
        "It expects revenue of $89.85 to $90.95 billion. "
        + ("No other figure is stated in this release. " * 3)
    )
    url = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000099/ex99.htm"
    decision = decide_filing(
        ticker="NVDA",
        form="8-K",
        items=["7.01"],
        accession="0001045810-26-000099",
        documents=[_doc(exhibit, url=url, exhibit="99.1")],
    )
    assert decision["h3_category"] == "guidance"
    assert decision["figure"] == "$89.85 to $90.95 billion"
    assert decision["measure"] == "revenue"
    line = _line(decision, name="NVIDIA", accepted_at="2026-11-06T02:00:00Z")
    assert line == (
        "NVIDIA raised its outlook for the next quarter, according to an SEC filing on Nov 5. "
        "The company now expects revenue of $89.85 to $90.95 billion."
    )

    bare = (
        "The Company raised its outlook for the next quarter. "
        "It expects revenue of $89.85 to $90.95. "
        + ("No scale word is attached to that range. " * 3)
    )
    dropped = decide_filing(
        ticker="NVDA",
        form="8-K",
        items=["7.01"],
        accession="0001045810-26-000099",
        documents=[_doc(bare, url=url, exhibit="99.1")],
    )
    assert dropped["h3_category"] == "guidance"
    assert dropped["figure"] is None
    bare_line = _line(dropped, name="NVIDIA", accepted_at="2026-11-06T02:00:00Z")
    assert bare_line == "NVIDIA raised its outlook for the next quarter, according to an SEC filing on Nov 5."
    assert "$89.85" not in bare_line


def test_guidance_probe_clear_direction_shows_and_unclear_hides():
    """QA probe: clear raise/reaffirm may show. Mixed or missing direction stays hidden."""
    pad = " The filing was furnished to the regulator on the date shown." * 4
    main = "Item 7.01 Regulation FD Disclosure. The company furnished an exhibit." + pad
    exhibit_url = "https://www.sec.gov/Archives/edgar/data/1/ex99.htm"
    accepted = "2026-09-02T20:30:24Z"

    def run(text):
        decision = decide_filing(
            ticker="TEST",
            form="8-K",
            items=["7.01", "9.01"],
            accession="0000000000-26-000001",
            documents=[
                _doc(main, url="https://www.sec.gov/Archives/edgar/data/1/body.htm"),
                _doc(text + pad, url=exhibit_url, exhibit="99.1"),
            ],
        )
        line = _line(decision, name="Testco", accepted_at=accepted)
        return decision, line

    shown, line = run(
        "Testco raised its outlook for fiscal 2027. "
        "The company now expects revenue of $89.85 to $90.95 billion for fiscal 2027."
    )
    assert shown["h3_category"] == "guidance"
    assert shown["text_outcome"] == "confirmed"
    assert line == (
        "Testco raised its outlook for fiscal 2027, according to an SEC filing on Sep 2. "
        "The company now expects revenue of $89.85 to $90.95 billion."
    )

    reaffirmed, line = run(
        "Testco reaffirmed its outlook for fiscal 2027. "
        "Revenue is expected to be $89.85 to $90.95 billion."
    )
    assert reaffirmed["h3_category"] == "guidance"
    assert reaffirmed["guide_direction"] == "confirmed"
    assert line == (
        "Testco confirmed its earlier outlook for fiscal 2027, according to an SEC filing on Sep 2. "
        "The company now expects revenue of $89.85 to $90.95 billion."
    )

    billion_each, line = run(
        "Testco raised its outlook for fiscal 2027. "
        "The company now expects revenue of $89.85 billion to $90.95 billion."
    )
    assert billion_each["h3_category"] == "guidance"
    assert billion_each["text_outcome"] == "confirmed"
    assert line == "Testco raised its outlook for fiscal 2027, according to an SEC filing on Sep 2."

    single, line = run(
        "Testco raised its outlook for fiscal 2027. "
        "The company now expects revenue of $90 billion."
    )
    assert single["h3_category"] == "guidance"
    assert line == (
        "Testco raised its outlook for fiscal 2027, according to an SEC filing on Sep 2. "
        "The company now expects revenue of $90 billion."
    )

    for text in (
        "Testco updated its guidance for fiscal 2027. Revenue is expected to be $90 billion.",
        "Testco raised its revenue outlook and lowered its margin outlook for fiscal 2027. "
        "Revenue is expected to be $90 billion.",
    ):
        hidden, line = run(text)
        assert hidden["h3_category"] is None
        assert hidden["verified"] is False
        assert hidden["hide_reason"] == "ambiguous"
        assert hidden["text_outcome"] != "confirmed"
        assert line is None

    both = (
        "The company announced financial results for its fiscal 2027 first quarter ended June 30, 2026. "
        "Diluted earnings per share were $2.10. "
        "The Company also raised its outlook for the next quarter."
    )
    mixed = decide_filing(
        ticker="TEST",
        form="8-K",
        items=["2.02"],
        accession="0000000000-26-000002",
        documents=[_doc(both + pad, url=exhibit_url, exhibit="99.1")],
    )
    assert mixed["h3_category"] is None
    assert mixed["hide_reason"] == "two_categories"
    assert mixed["text_outcome"] != "confirmed"


def test_foreign_accession_exhibit_is_never_picked():
    base = "https://www.sec.gov/Archives/edgar/data/1045810/000119312526275783/d48176d8k.htm"
    foreign = (
        "http://www.sec.gov/Archives/edgar/data/1045810/000119312516711700/d260668dex41.htm"
    )
    html = f"""
    <html><body>
    <p>The notes were issued under an indenture filed as Exhibit 4.1.
    <a href="{foreign}">d260668dex41.htm</a></p>
    <table>
    <tr>
    <td>4.1</td>
    <td><a href="{foreign}">Indenture dated 2016</a></td>
    </tr>
    <tr>
    <td>99.1</td>
    <td><a href="ex99_1.htm">Press release</a></td>
    </tr>
    </table>
    </body></html>
    """
    found = _find_exhibits(html, base)
    assert all("000119312516711700" not in url and "d260668dex41" not in url for _number, url in found)
    assert found == [(
        "99.1",
        "https://www.sec.gov/Archives/edgar/data/1045810/000119312526275783/ex99_1.htm",
    )]
    assert _exhibit_number("indenture", "d260668dex41.htm") == "4.1"


def test_document_500_backs_off_then_hides(client, monkeypatch, tmp_path):
    from app.db import SessionLocal, utcnow
    from app.models import SecFetchState, SecFiling
    from app.services import sec_filings as sec

    assert sec.DOC_FAIL_BACKOFF == timedelta(hours=6)
    assert sec.DOC_FAIL_LIMIT == 3
    user = client.post("/onboarding", json={"interests": ["gaming"]})
    user_id = user.json()["user_id"]
    assert client.post("/like", json={"user_id": user_id, "ticker": "NVDA"}).status_code == 200
    monkeypatch.setenv("SEC_USER_AGENT", "fun(d) contact@example.com")
    monkeypatch.setattr(sec, "CACHE_DIR", tmp_path / "sec")
    monkeypatch.setattr(sec.time, "sleep", lambda *_args, **_kwargs: None)
    accession = "0001193125-26-275783"
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": [accession],
                "form": ["8-K"],
                "filingDate": ["2026-06-18"],
                "acceptanceDateTime": ["2026-06-18T16:00:00.000Z"],
                "items": ["8.01"],
                "primaryDocument": ["d48176d8k.htm"],
            }
        }
    }
    seen = []

    def urlopen(request, timeout=30):
        seen.append(request.full_url)
        url = request.full_url
        if "company_tickers" in url:
            return _Json({"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA"}})
        if "CIK" in url:
            return _Json(payload)
        if "d48176d8k" in url:
            raise urllib.error.HTTPError(url, 500, "err", hdrs=None, fp=None)
        raise AssertionError(url)

    monkeypatch.setattr(sec.urllib.request, "urlopen", urlopen)

    def expire():
        session = SessionLocal()
        row = session.get(SecFetchState, f"docfail:{accession}")
        row.backoff_until = utcnow() - timedelta(hours=1)
        session.commit()
        session.close()

    def outcome():
        session = SessionLocal()
        row = session.get(SecFiling, accession)
        state = session.get(SecFetchState, f"docfail:{accession}")
        result = (row.text_outcome if row else None, state.note if state else None, state.backoff_until if state else None)
        session.close()
        return result

    sec.refresh_liked_8k_filings()
    assert any("d48176d8k" in url for url in seen)
    text_outcome, note, until = outcome()
    assert text_outcome is None
    assert note == "1"
    assert until > utcnow() + timedelta(hours=5)
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert not any("d48176d8k" in url for url in seen)
    expire()
    sec.refresh_liked_8k_filings()
    assert outcome()[1] == "2"
    expire()
    sec.refresh_liked_8k_filings()
    assert outcome()[0] == "unconfirmable"
    assert outcome()[1] == "3"
    seen.clear()
    sec.refresh_liked_8k_filings()
    assert not any("d48176d8k" in url for url in seen)
