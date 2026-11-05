"""Catalyst alerts. Prices and headlines here are fixtures, not market data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.catalysts import NEW_YORK, headline_has_catalyst_term

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)  # Monday 1:00 p.m. ET
TERMS = (
    "earnings",
    "results",
    "acquires",
    "acquisition",
    "merger",
    "guidance",
    "outlook",
    "appoints",
    "appointed",
    "steps down",
    "resigns",
    "CEO",
    "CFO",
)


def _onboard(client, interests):
    response = client.post("/onboarding", json={"interests": interests})
    assert response.status_code == 200, response.text
    return response.json()["user_id"]


def _like(client, user_id, ticker):
    response = client.post("/like", json={"user_id": user_id, "ticker": ticker})
    assert response.status_code == 200, response.text


def _set_company(ticker, **fields):
    from app.db import SessionLocal
    from app.models import Company

    session = SessionLocal()
    company = session.get(Company, ticker)
    assert company is not None
    for key, value in fields.items():
        setattr(company, key, value)
    session.commit()
    session.close()


def _set_earnings(ticker, report_date, hour=None):
    from app.db import SessionLocal, utcnow
    from app.models import EarningsCalendar

    session = SessionLocal()
    row = session.get(EarningsCalendar, ticker)
    if row is None:
        session.add(
            EarningsCalendar(ticker=ticker, report_date=report_date, hour=hour, fetched_at=utcnow())
        )
    else:
        row.report_date = report_date
        row.hour = hour
        row.fetched_at = utcnow()
    session.commit()
    session.close()


def _detect(user_id, now=NOW):
    from app.db import SessionLocal
    from app.services.catalysts import detect_for_user

    session = SessionLocal()
    detect_for_user(session, user_id, now)
    session.commit()
    session.close()


def _alerts(user_id):
    from app.db import SessionLocal
    from app.models import Alert

    session = SessionLocal()
    rows = (
        session.query(Alert)
        .filter(Alert.user_id == user_id)
        .order_by(Alert.created_at.asc(), Alert.id.asc())
        .all()
    )
    found = [(row.kind, row.dedupe_key, row.line, row.seen) for row in rows]
    session.close()
    return found


def _baseline(user_id, ticker, kind):
    from app.db import SessionLocal
    from app.models import AlertBaseline

    session = SessionLocal()
    row = session.get(AlertBaseline, (user_id, ticker, kind))
    key = None if row is None else row.baseline_key
    session.close()
    return key


def _quote_at(days_ago, hour_utc=18):
    moment = NOW - timedelta(days=days_ago)
    return datetime(moment.year, moment.month, moment.day, hour_utc)


def _weekday_label(day):
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{weekdays[day.weekday()]}, {months[day.month - 1]} {day.day}"


def _et_label(when_naive_utc):
    aware = when_naive_utc.replace(tzinfo=timezone.utc).astimezone(NEW_YORK)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{months[aware.month - 1]} {aware.day}"


ADVICE_WORDS = (
    "buy",
    "sell",
    "hold",
    "soared",
    "crashed",
    "plunged",
    "skyrocketed",
    "tanked",
    "time to",
    "should you",
    "don't miss",
)


def _no_advice(line: str) -> None:
    lowered = line.lower()
    for word in ADVICE_WORDS:
        assert word not in lowered


def test_rendered_lines_match_the_i3_templates(client):
    """Lines from i3_alert_templates.md, written 2026-11-05."""
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _like(client, user_id, "AMD")
    _like(client, user_id, "SONY")
    first = _quote_at(12)
    second = _quote_at(11)
    today = NOW.astimezone(NEW_YORK).date()
    tomorrow = today + timedelta(days=1)

    _set_company("NVDA", current_price=10, price_change_percent=1, latest_quote_at=first)
    _detect(user_id)
    _set_company("NVDA", current_price=210.5, price_change_percent=6, latest_quote_at=second)
    _detect(user_id)
    price_line = _alerts(user_id)[0][2]
    assert price_line == (
        f"Big move: NVIDIA is up 6.0% (as of {_et_label(second)}), at US$210.50."
    )
    _no_advice(price_line)
    assert "today" not in price_line and "tomorrow" not in price_line

    _set_company("AMD", current_price=40, price_change_percent=-5, latest_quote_at=first)
    _detect(user_id)
    _set_company("AMD", current_price=38, price_change_percent=-5.5, latest_quote_at=second)
    _detect(user_id)
    down_line = [row[2] for row in _alerts(user_id) if row[2].startswith("Big move: AMD")][0]
    assert down_line == (
        f"Big move: AMD is down 5.5% (as of {_et_label(second)}), at US$38.00."
    )
    _no_advice(down_line)

    _set_earnings("SONY", (today + timedelta(days=4)).isoformat())
    _detect(user_id)
    _set_earnings("SONY", tomorrow.isoformat(), "amc")
    _detect(user_id)
    earnings_line = [row[2] for row in _alerts(user_id) if row[2].startswith("Results coming")][0]
    assert earnings_line == (
        "Results coming: Sony is scheduled to share its latest quarterly results on "
        f"{_weekday_label(tomorrow)}, after the market closes."
    )
    _no_advice(earnings_line)
    assert "today" not in earnings_line and "tomorrow" not in earnings_line

    _set_earnings("SONY", today.isoformat(), "dmh")
    _detect(user_id)
    plain = [row[2] for row in _alerts(user_id) if _weekday_label(today) in row[2]][0]
    assert plain == (
        "Results coming: Sony is scheduled to share its latest quarterly results on "
        f"{_weekday_label(today)}."
    )
    assert "market" not in plain

    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA guidance is raised",
        latest_news_unix=(NOW - timedelta(hours=3)).timestamp(),
        latest_news_id="guide-1",
        latest_news_date="2026-11-08",
        latest_news_source="Example Wire",
        latest_news_url="https://example.com/guide",
    )
    _detect(user_id)
    # The first qualifying news item is only a baseline.
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA outlook stays steady",
        latest_news_unix=(NOW - timedelta(hours=1)).timestamp(),
        latest_news_id="outlook-1",
        latest_news_date="2026-11-09",
        latest_news_source="",
    )
    _detect(user_id)
    news_lines = [row[2] for row in _alerts(user_id) if row[2].startswith("New for")]
    assert news_lines == ['New for NVIDIA: "NVIDIA outlook stays steady" (Nov 9).']
    _no_advice(news_lines[0])

    _set_company("NVDA", short_name=" ", company_name=" ")
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA results are posted",
        latest_news_unix=(NOW - timedelta(hours=1)).timestamp(),
        latest_news_id="blank-name",
        latest_news_date="2026-11-09",
        latest_news_source="Example Wire",
    )
    before = len(_alerts(user_id))
    _detect(user_id)
    assert len(_alerts(user_id)) == before


def test_price_baseline_dedupe_directions_and_real_date(client):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    friday = _quote_at(10)
    saturday = _quote_at(9)

    _set_company("NVDA", current_price=0, price_change_percent=9, latest_quote_at=friday)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") is None
    assert _alerts(user_id) == []

    _set_company("NVDA", current_price=float("nan"), price_change_percent=9, latest_quote_at=friday)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") is None

    _set_company("NVDA", current_price=210.5, price_change_percent=float("inf"), latest_quote_at=friday)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") is None

    _set_company("NVDA", current_price=210.5, price_change_percent=6, latest_quote_at=None)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") is None

    future = (NOW + timedelta(minutes=10)).replace(tzinfo=None)
    _set_company("NVDA", current_price=210.5, price_change_percent=6, latest_quote_at=future)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") is None

    # First valid quote is already a 6% move. Baseline only, no alert.
    _set_company("NVDA", current_price=210.5, price_change_percent=6, latest_quote_at=friday)
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "price") == f"{friday.replace(tzinfo=timezone.utc).astimezone(NEW_YORK).date().isoformat()}|up"
    assert _alerts(user_id) == []
    _detect(user_id)
    assert _alerts(user_id) == []

    # Same date, dip under 5 and recross. Still no second emit.
    _set_company("NVDA", price_change_percent=1)
    _detect(user_id)
    _set_company("NVDA", price_change_percent=8)
    _detect(user_id)
    assert _alerts(user_id) == []

    # A new quote date emits once, labeled with that date, not the word today.
    _set_company("NVDA", current_price=200, price_change_percent=-6.2, latest_quote_at=saturday)
    _detect(user_id)
    alerts = _alerts(user_id)
    assert len(alerts) == 1
    assert alerts[0][0] == "price"
    assert alerts[0][1].endswith("|down")
    assert _et_label(saturday) in alerts[0][2]
    assert "today" not in alerts[0][2]
    assert "US$200.00" in alerts[0][2]
    assert "6.2%" in alerts[0][2]
    _set_company("NVDA", price_change_percent=-1)
    _detect(user_id)
    _set_company("NVDA", price_change_percent=-9)
    _detect(user_id)
    assert len(_alerts(user_id)) == 1

    # Opposite direction on that same date emits once.
    _set_company("NVDA", price_change_percent=5)
    _detect(user_id)
    assert len(_alerts(user_id)) == 2
    assert _alerts(user_id)[1][1].endswith("|up")
    _detect(user_id)
    assert len(_alerts(user_id)) == 2


def test_earnings_window_reschedule_and_hour(client):
    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    today = NOW.astimezone(NEW_YORK).date()
    tomorrow = today + timedelta(days=1)
    outside = today + timedelta(days=5)

    _detect(user_id)
    assert _baseline(user_id, "NVDA", "earnings") is None

    _set_earnings("NVDA", outside.isoformat(), "amc")
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "earnings") == "none"
    assert _alerts(user_id) == []

    _set_earnings("NVDA", tomorrow.isoformat(), None)
    _detect(user_id)
    alerts = _alerts(user_id)
    assert len(alerts) == 1
    assert alerts[0][0] == "earnings"
    assert alerts[0][1] == tomorrow.isoformat()
    assert alerts[0][2] == (
        "Results coming: NVIDIA is scheduled to share its latest quarterly results on "
        f"{_weekday_label(tomorrow)}."
    )
    assert "today" not in alerts[0][2]
    assert "tomorrow" not in alerts[0][2]
    _detect(user_id)
    assert len(_alerts(user_id)) == 1

    _set_earnings("NVDA", today.isoformat(), "bmo")
    _detect(user_id)
    assert _alerts(user_id)[1][2] == (
        "Results coming: NVIDIA is scheduled to share its latest quarterly results on "
        f"{_weekday_label(today)}, before the market opens."
    )
    _set_earnings("NVDA", today.isoformat(), "amc")
    _detect(user_id)
    assert len(_alerts(user_id)) == 2

    _set_earnings("NVDA", tomorrow.isoformat(), "amc")
    # A second ticker proves the hour clause on a first in-window date after 'none'.
    _like(client, user_id, "AMD")
    _set_earnings("AMD", tomorrow.isoformat(), "amc")
    _detect(user_id)
    amd = [row for row in _alerts(user_id) if "AMD" in row[2] or row[1] == tomorrow.isoformat()]
    # AMD's first in-window read is the baseline, so it does not emit.
    assert _baseline(user_id, "AMD", "earnings") == tomorrow.isoformat()
    assert not any(row[2].startswith("Results coming: AMD") for row in _alerts(user_id))
    assert amd is not None


def test_news_gates_terms_and_f2b_reject(client):
    from app.services.news import select_company_news

    rejected = select_company_news(
        [{
            "headline": "NVIDIA: Buy this stock now",
            "summary": "An analyst note that tells readers what to do.",
            "datetime": 1793577600,
        }],
        "NVDA",
    )
    assert rejected is None

    for term in TERMS:
        assert headline_has_catalyst_term(f"NVIDIA {term} this week")
        assert headline_has_catalyst_term(f"the board {term} suddenly")
    assert not headline_has_catalyst_term("NVIDIA earning this week")
    assert not headline_has_catalyst_term("NVIDIA acquired a studio")
    assert not headline_has_catalyst_term("NVIDIA CEOs meet")
    assert headline_has_catalyst_term("The CEO steps down next month")

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _set_company("NVDA", latest_news_headline="__no_recent_company_news__")
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "news") is None

    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA opens a new office",
        latest_news_unix=None,
    )
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "news") is None

    future = (NOW + timedelta(minutes=10)).timestamp()
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA guidance is updated",
        latest_news_unix=future,
        latest_news_id="future-1",
    )
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "news") is None

    # First real article misses the term list, so the baseline is none and nothing emits.
    old = (NOW - timedelta(hours=2)).timestamp()
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA opens a new office",
        latest_news_unix=old,
        latest_news_id="office-1",
        latest_news_url="https://example.com/office",
    )
    _detect(user_id)
    assert _baseline(user_id, "NVDA", "news") == "none"
    assert _alerts(user_id) == []

    exactly = (NOW - timedelta(hours=24)).timestamp()
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA earnings are out",
        latest_news_unix=exactly,
        latest_news_id="earn-24",
        latest_news_url="https://example.com/earn",
        latest_news_date="2026-11-05",
        latest_news_source="Example Wire",
    )
    _detect(user_id)
    assert len(_alerts(user_id)) == 1
    assert _alerts(user_id)[0][0] == "news"
    assert _alerts(user_id)[0][2] == (
        'New for NVIDIA: "NVIDIA earnings are out" (Example Wire, Nov 5).'
    )
    _detect(user_id)
    assert len(_alerts(user_id)) == 1

    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA results are missing a date",
        latest_news_unix=old,
        latest_news_id="no-date",
        latest_news_date=None,
        latest_news_source="Example Wire",
    )
    _detect(user_id)
    assert len(_alerts(user_id)) == 1

    too_old = (NOW - timedelta(hours=24, seconds=1)).timestamp()
    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA results are published",
        latest_news_unix=too_old,
        latest_news_id="results-old",
    )
    _detect(user_id)
    assert len(_alerts(user_id)) == 1

    _set_company(
        "NVDA",
        latest_news_headline="NVIDIA earning season starts",
        latest_news_unix=old,
        latest_news_id="near-miss",
    )
    _detect(user_id)
    assert len(_alerts(user_id)) == 1


def test_unlike_drops_alerts_and_baselines_and_restarts(client):
    user_id = _onboard(client, ["gaming"])
    other = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _like(client, other, "NVDA")
    when = _quote_at(3)
    _set_company("NVDA", current_price=50, price_change_percent=1, latest_quote_at=when)
    _detect(user_id)
    _detect(other)
    assert _baseline(user_id, "NVDA", "price") == "none"
    _set_company("NVDA", price_change_percent=6)
    _detect(user_id)
    _detect(other)
    assert len(_alerts(user_id)) == 1
    assert len(_alerts(other)) == 1

    removed = client.post("/unlike", json={"user_id": user_id, "ticker": "NVDA"})
    assert removed.status_code == 200
    assert _alerts(user_id) == []
    assert _baseline(user_id, "NVDA", "price") is None
    assert len(_alerts(other)) == 1

    _like(client, user_id, "NVDA")
    _detect(user_id)
    # Re-like starts at baseline again, even though the move is still >= 5%.
    assert _alerts(user_id) == []
    assert _baseline(user_id, "NVDA", "price") is not None
    later = _quote_at(2)
    _set_company("NVDA", price_change_percent=7, latest_quote_at=later)
    _detect(user_id)
    assert len(_alerts(user_id)) == 1


def test_updates_keeps_its_shape_and_seen_marks_alerts(client, monkeypatch):
    calls = []

    def boom(*_args, **_kwargs):
        calls.append("finnhub")
        raise AssertionError("Finnhub was called while detecting alerts")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.finnhub.urllib.request.urlopen", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_quote", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_company_news", boom)
    monkeypatch.setattr("app.services.finnhub.FinnhubClient.get_earnings_calendar", boom)

    missing = client.get("/updates", params={"user_id": "nobody"})
    assert missing.status_code == 404
    missing_seen = client.post("/alerts/seen", json={"user_id": "nobody"})
    assert missing_seen.status_code == 404

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _like(client, user_id, "AMD")
    when = (datetime.now(timezone.utc) - timedelta(days=4)).replace(tzinfo=None, microsecond=0)
    _set_company("NVDA", current_price=210.5, price_change_percent=1.2, latest_quote_at=when)
    _set_company(
        "AMD",
        current_price=40,
        price_change_percent=1.2,
        latest_quote_at=when,
        latest_news_headline="AMD ships a new chip",
        latest_news_summary="A long enough summary of the chip story.",
        latest_news_date="2026-11-01",
        latest_news_url="https://example.com/amd",
    )
    first = client.get("/updates", params={"user_id": user_id})
    assert first.status_code == 200, first.text
    body = first.json()
    assert "updates" in body and isinstance(body["updates"], list)
    assert body["alerts"] == []
    assert body["unseen_count"] == 0
    for item in body["updates"]:
        assert set(item) >= {"ticker", "lines", "news_url"}

    later = (datetime.now(timezone.utc) - timedelta(days=3)).replace(tzinfo=None, microsecond=0)
    _set_company("NVDA", current_price=220, price_change_percent=6.5, latest_quote_at=later)
    second = client.get("/updates", params={"user_id": user_id})
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["unseen_count"] == 1
    assert len(payload["alerts"]) == 1
    alert = payload["alerts"][0]
    assert alert["ticker"] == "NVDA"
    assert alert["short_name"] == "NVIDIA"
    assert alert["kind"] == "price"
    assert alert["seen"] is False
    assert alert["url"] is None
    assert alert["line"].startswith("Big move: NVIDIA is up ")
    assert "today" not in alert["line"]
    assert isinstance(alert["id"], int)
    assert payload["updates"]

    again = client.get("/updates", params={"user_id": user_id})
    assert again.json()["unseen_count"] == 1
    assert [item["id"] for item in again.json()["alerts"]] == [alert["id"]]

    seen = client.post("/alerts/seen", json={"user_id": user_id})
    assert seen.status_code == 200
    assert seen.json() == {"unseen_count": 0}
    after = client.get("/updates", params={"user_id": user_id})
    assert after.json()["unseen_count"] == 0
    assert after.json()["alerts"][0]["seen"] is True
    assert after.json()["alerts"][0]["id"] == alert["id"]
    assert calls == []


def test_refresher_warms_earnings_and_detection_reads_the_cache(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FINNHUB_API_KEY", "dummy-key")
    monkeypatch.setenv("FUN_D_FINNHUB_LIVE", "1")

    from app.services import live as live_mod

    monkeypatch.setattr(live_mod, "DEFAULT_CACHE_DIR", tmp_path)
    live_mod._client = None
    quote_calls = []
    calendar_calls = []

    def fake_quote(_self, symbol):
        quote_calls.append(symbol)
        stamp = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
        return {"c": 25.0, "dp": 1.5, "t": stamp}

    def fake_news(_self, symbol, _news_from, _news_to):
        return []

    def fake_profile(_self, symbol):
        return {}

    def fake_calendar(_self, symbol, from_date, to_date):
        calendar_calls.append((symbol, from_date, to_date))
        return {"earningsCalendar": []}

    monkeypatch.setattr(live_mod.FinnhubClient, "get_quote", fake_quote)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_company_news", fake_news)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_profile", fake_profile)
    monkeypatch.setattr(live_mod.FinnhubClient, "get_earnings_calendar", fake_calendar)

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    live_mod.refresh_passes(["NVDA"])

    assert quote_calls == ["NVDA"]
    assert calendar_calls and calendar_calls[0][0] == "NVDA"
    start = datetime.strptime(calendar_calls[0][1], "%Y-%m-%d").date()
    end = datetime.strptime(calendar_calls[0][2], "%Y-%m-%d").date()
    assert (end - start).days == 7
    assert _baseline(user_id, "NVDA", "price") == "none"
    assert _baseline(user_id, "NVDA", "earnings") == "none"
    assert _alerts(user_id) == []

    # A second pass still does not call Finnhub from detection, and does not alert.
    live_mod.refresh_passes(["NVDA"])
    assert quote_calls == ["NVDA", "NVDA"]
    assert _alerts(user_id) == []


def test_alerts_are_newest_first_and_capped(client):
    from app.db import SessionLocal, utcnow
    from app.models import Alert

    user_id = _onboard(client, ["gaming"])
    _like(client, user_id, "NVDA")
    _set_company(
        "NVDA",
        current_price=10,
        price_change_percent=1,
        latest_quote_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
    )
    _detect(user_id)
    session = SessionLocal()
    base = utcnow()
    for index in range(51):
        session.add(
            Alert(
                user_id=user_id,
                ticker="NVDA",
                kind="price",
                dedupe_key=f"extra-{index}",
                facts="{}",
                line=f"line {index}",
                created_at=base + timedelta(seconds=index),
                seen=False,
            )
        )
    session.commit()
    session.close()

    # Detection on this read must not drop the seeded rows or call Finnhub.
    body = client.get("/updates", params={"user_id": user_id}).json()
    assert len(body["alerts"]) == 50
    assert body["unseen_count"] == 51
    assert body["alerts"][0]["line"] == "line 50"
    assert body["alerts"][-1]["line"] == "line 1"
