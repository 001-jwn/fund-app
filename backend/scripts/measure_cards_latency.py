#!/usr/bin/env python3
"""Time GET /cards on a temp database with a warm cache.

No network and no API keys. Prints median and p95 milliseconds for N calls
with the limit query omitted and with limit=10.

Run from the backend directory:

    python scripts/measure_cards_latency.py
    python scripts/measure_cards_latency.py --n 80
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path


def _no_network(*_args, **_kwargs):
    raise RuntimeError("measure_cards_latency does not use the network")


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return ordered[rank]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _warm_cache() -> None:
    """Fill quote and news fields so cards read the database, not the network."""
    from app.db import SessionLocal
    from app.models import Company

    quote_at = datetime(2026, 11, 4, 4, 30, 0)
    session = SessionLocal()
    try:
        for company in session.query(Company).all():
            company.current_price = 100.0
            company.price_change_percent = 1.25
            company.latest_quote_at = quote_at
            company.latest_news_headline = f"{company.ticker} ships an update"
            company.latest_news_summary = "A cached summary."
            company.latest_news_date = "2026-11-03"
            company.latest_news_source = "Example Wire"
            company.latest_news_url = "https://example.com/cached"
            company.logo_url = "https://example.com/logo.png"
        session.commit()
    finally:
        session.close()


def _time_calls(client, path: str, n: int) -> list[float]:
    for _ in range(5):
        response = client.get(path)
        if response.status_code != 200:
            raise SystemExit(f"warmup failed: {response.status_code}")
    samples = []
    for _ in range(n):
        started = time.perf_counter()
        response = client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise SystemExit(f"timed call failed: {response.status_code}")
        samples.append(elapsed_ms)
    return samples


def _print_stats(label: str, samples: list[float]) -> None:
    print(
        f"{label}: median {_median(samples):.2f} ms, p95 {_percentile(samples, 95):.2f} ms (n={len(samples)})",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=80, help="timed calls per series")
    args = parser.parse_args()
    if args.n < 2:
        raise SystemExit("--n must be at least 2")

    # Set these before importing the app so a local .env cannot supply a key.
    os.environ["FINNHUB_API_KEY"] = ""
    os.environ["FUN_D_FINNHUB_LIVE"] = "0"
    os.environ["SEC_USER_AGENT"] = ""
    urllib.request.urlopen = _no_network

    backend_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_dir))

    with tempfile.TemporaryDirectory(prefix="fund-cards-latency-") as tmp:
        os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tmp) / "latency.db")
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()) as client:
            _warm_cache()
            onboard = client.post(
                "/onboarding",
                json={"interests": ["gaming", "travel", "music", "automobile"]},
            )
            if onboard.status_code != 200:
                raise SystemExit(f"onboarding failed: {onboard.status_code}")
            user_id = onboard.json()["user_id"]
            omitted = f"/cards?user_id={user_id}"
            limited = f"/cards?user_id={user_id}&limit=10"
            _print_stats("without limit", _time_calls(client, omitted, args.n))
            _print_stats("with limit=10", _time_calls(client, limited, args.n))


if __name__ == "__main__":
    main()
