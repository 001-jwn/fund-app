"""Company-news filtering from news_match_rules.json. No live Finnhub calls."""

from __future__ import annotations

import json

from app.seed.load_seed import SEED_PATH
from app.services.news import (
    NO_RECENT_NEWS_MESSAGE,
    RULES_PATH,
    clean_summary,
    format_news_date_label,
    format_quarter_label,
    load_rules,
    select_company_news,
)

TREFIS = (
    "For questions about this article or underlying research, "
    "email help@trefis.com or visit trefis.com."
)


def test_rules_file_covers_every_seed_ticker():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    tickers = {company["ticker"] for company in seed["companies"]}
    assert set(rules["aliases"]) == tickers
    assert load_rules()["no_bare_ticker"] == rules["no_bare_ticker"]


def test_irrelevant_news_is_rejected_and_the_latest_match_wins():
    amzn = [
        {
            "headline": "CrowdStrike lifts its outlook",
            "summary": "Security software demand stayed strong across the quarter.",
            "related": "AMZN",
            "datetime": 300,
        },
        {
            "headline": "Amazon expands grocery delivery",
            "summary": "The retail business added more cities this quarter.",
            "related": "AMZN,WMT,TGT",
            "datetime": 100,
        },
        {
            "headline": "Amazon holiday forecast rises",
            "summary": "Shoppers are ordering earlier this year than last year.",
            "datetime": 200,
        },
    ]
    picked = select_company_news(amzn, "AMZN")
    assert picked is not None
    assert picked.headline == "Amazon holiday forecast rises"

    assert select_company_news(
        [{
            "headline": "BorgWarner wins a new contract",
            "summary": "The supplier raised its full-year guidance.",
            "related": "TM",
            "datetime": 5,
        }],
        "TM",
    ) is None
    assert select_company_news(
        [{"headline": "Marriott adds hotels in Asia", "summary": "Room demand improved across the region.", "datetime": 5}],
        "HLT",
    ) is None
    assert select_company_news(
        [{"headline": "Stellantis cuts a factory shift", "summary": "The automaker cited weaker demand.", "datetime": 5}],
        "GM",
    ) is None
    assert select_company_news(
        [{"headline": "5 Best Warren Buffett Stocks", "summary": "A list of widely held names.", "related": "DAL", "datetime": 5}],
        "DAL",
    ) is None

    election = [{
        "headline": "Stocks swing on election night",
        "summary": "U.S. markets moved as results came in across the board.",
        "related": "AMD,NVDA,MSFT,U",
        "datetime": 9,
    }]
    for ticker in ("AMD", "NVDA", "MSFT", "U"):
        assert select_company_news(election, ticker) is None


def test_bare_tickers_in_the_block_list_do_not_match():
    assert select_company_news(
        [{"headline": "AMD stock jumps", "summary": "Shares moved after the open today.", "datetime": 3}],
        "AMD",
    ) is None
    assert select_company_news(
        [{"headline": "Advanced Micro Devices raises its outlook", "summary": "Data-center demand stayed ahead of plan.", "datetime": 3}],
        "AMD",
    ) is not None
    assert select_company_news(
        [{"headline": "Chip demand lifts ($AMD) after hours", "summary": "Traders cited a stronger data-center forecast.", "datetime": 3}],
        "AMD",
    ) is not None

    toyota = select_company_news(
        [{"headline": "Toyota recalls a hybrid", "summary": "Owners will be notified by mail over the next month.", "datetime": 4}],
        "TM",
    )
    assert toyota is not None
    assert select_company_news(
        [{"headline": "TM recalls a hybrid", "summary": "Owners will be notified by mail over the next month.", "datetime": 4}],
        "TM",
    ) is None

    assert select_company_news(
        [{"headline": "NVDA rallies after a chip update", "summary": "Traders bought the shares into the close.", "datetime": 4}],
        "NVDA",
    ) is not None

    unity = select_company_news(
        [{"headline": "Unity (U) updates its engine", "summary": "Game makers get a new release this month.", "datetime": 4}],
        "U",
    )
    assert unity is not None
    assert select_company_news(
        [{"headline": "Unity updates its engine", "summary": "Game makers get a new release this month.", "datetime": 4}],
        "U",
    ) is None
    assert select_company_news(
        [{"headline": "U.S. stocks were mixed", "summary": "The U.K. market was quiet too.", "datetime": 8}],
        "U",
    ) is None

    ford = select_company_news(
        [{"headline": "Ford Motor raises truck output", "summary": "The company pointed to steady F-series demand.", "datetime": 6}],
        "F",
    )
    assert ford is not None
    assert select_company_news(
        [{"headline": "F raises truck output", "summary": "The company pointed to steady demand this quarter.", "datetime": 6}],
        "F",
    ) is None


def test_summaries_hide_boilerplate_short_text_and_headline_copies():
    kept = clean_summary(f"Roblox daily users rose. {TREFIS}", "Roblox posts its quarter")
    assert kept == "Roblox daily users rose."
    assert clean_summary(TREFIS) is None
    assert clean_summary("   ") is None
    assert clean_summary(None) is None
    assert clean_summary("Shares rose.") is None
    assert clean_summary(
        "Looking for stock market analysis and research with a free feed.",
        "Some headline",
    ) is None

    zacks = clean_summary(
        "Booking demand stayed ahead of last year across the hotels group. "
        "Zacks Investment Research readers can get a free report today.",
        "Hotels stayed busy",
    )
    assert zacks == "Booking demand stayed ahead of last year across the hotels group."

    headline = "Airbnb bookings rose in the latest quarter"
    assert clean_summary(headline, headline) is None
    assert clean_summary(headline + ".", headline) is None

    article = select_company_news(
        [{
            "headline": "Roblox posts its quarter",
            "summary": TREFIS,
            "datetime": 50,
        }],
        "RBLX",
    )
    assert article is not None
    assert article.summary is None

    copied = select_company_news(
        [{
            "headline": "NetEase games keep growing this year",
            "summary": "NetEase games keep growing this year",
            "datetime": 50,
        }],
        "NTES",
    )
    assert copied is not None
    assert copied.summary is None

    short = select_company_news(
        [{
            "headline": "Expedia adds another city to its app",
            "summary": "More cities.",
            "datetime": 50,
        }],
        "EXPE",
    )
    assert short is not None
    assert short.summary is None


def test_date_labels_use_the_card_copy():
    assert format_news_date_label("2026-11-02") == "News from Nov 2"
    assert format_quarter_label("2026-09-30") == "Last quarter (ended Sep 30, 2026)"
    assert format_quarter_label("2026-07-26") == "Last quarter (ended Jul 26, 2026)"
    assert format_news_date_label(None) is None
    assert format_quarter_label("not-a-date") is None
    assert NO_RECENT_NEWS_MESSAGE == "No recent news about this company yet."
