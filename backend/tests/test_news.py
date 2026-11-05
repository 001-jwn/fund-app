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

    # F1 rule 4 rejects the article when the summary is only boilerplate, a copy
    # of the headline, or shorter than the minimum. M1 still returned that
    # headline with summary=None. The card now tries the next story, or shows
    # no news, instead of a headline with an empty blurb.
    assert select_company_news(
        [{
            "headline": "Roblox posts its quarter",
            "summary": TREFIS,
            "datetime": 50,
        }],
        "RBLX",
    ) is None

    assert select_company_news(
        [{
            "headline": "NetEase games keep growing this year",
            "summary": "NetEase games keep growing this year",
            "datetime": 50,
        }],
        "NTES",
    ) is None

    assert select_company_news(
        [{
            "headline": "Expedia adds another city to its app",
            "summary": "More cities.",
            "datetime": 50,
        }],
        "EXPE",
    ) is None


def test_f1_skips_roundup_and_passing_mention_headlines():
    roundup = select_company_news(
        [{
            "headline": "META, AAPL, AMD... In Focus",
            "summary": "Apple was one of several large names traders watched today.",
            "datetime": 10,
        }],
        "AAPL",
    )
    assert roundup is None

    clickbait = select_company_news(
        [{
            "headline": "Microsoft and Oracle can't cool data centers without this growth stock",
            "summary": "The piece is about a different supplier, not Microsoft's own results.",
            "datetime": 11,
        }],
        "MSFT",
    )
    assert clickbait is None


def test_f1_requires_the_company_name_in_the_headline():
    summary_only = select_company_news(
        [{
            "headline": "Suppliers ride a hardware upgrade cycle",
            "summary": "Apple told investors that iPhone demand held up through the quarter.",
            "datetime": 12,
        }],
        "AAPL",
    )
    assert summary_only is None


def test_f1_newest_passing_headline_wins():
    picked = select_company_news(
        [
            {
                "headline": "Apple opens a new store",
                "summary": "The company added a location and hired more retail staff.",
                "datetime": 10,
            },
            {
                "headline": "META, AAPL, AMD... In Focus",
                "summary": "Traders watched a handful of large technology names today.",
                "datetime": 30,
            },
            {
                "headline": "Apple services revenue climbs again",
                "summary": "App Store sales were ahead of the same quarter last year.",
                "datetime": 20,
            },
        ],
        "AAPL",
    )
    assert picked is not None
    assert picked.headline == "Apple services revenue climbs again"


def test_trailing_ellipsis_is_trimmed_from_headline_and_summary():
    assert clean_summary(
        "The auto supplier pointed to steady demand this quarter…  ",
        "Aptiv raises its outlook",
    ) == "The auto supplier pointed to steady demand this quarter"

    picked = select_company_news(
        [{
            "headline": "Aptiv raises its outlook...",
            "summary": "The auto supplier pointed to steady demand this quarter... ",
            "datetime": 20,
        }],
        "APTV",
    )
    assert picked is not None
    assert picked.headline == "Aptiv raises its outlook"
    assert picked.summary == "The auto supplier pointed to steady demand this quarter"

    # A real sentence period is not a cut-off and stays on the card.
    assert clean_summary(
        "The auto supplier pointed to steady demand this quarter.",
        "Aptiv raises its outlook",
    ) == "The auto supplier pointed to steady demand this quarter."


ADVICE_PATTERNS = [
    "buy",
    "buying",
    "sell",
    "selling",
    "take profit",
    "take profits",
    "should you",
    "stock to own",
    "stocks to own",
    "maintains",
    "reiterates",
    "price target",
    "upgrade",
    "upgrades",
    "downgrade",
    "downgrades",
    "outperform",
    "underperform",
    "overweight",
    "underweight",
]


def test_advice_headlines_are_skipped_and_hold_or_buyback_are_kept():
    assert load_rules()["advice_headline_patterns"] == ADVICE_PATTERNS
    assert "hold" not in ADVICE_PATTERNS
    assert load_rules()["max_other_notable_names_in_headline"] == 0

    assert select_company_news(
        [{
            "headline": "Apple: Buy, Hold or Sell?",
            "summary": "A broker note weighs the shares after the latest quarter.",
            "datetime": 50,
        }],
        "AAPL",
    ) is None
    assert select_company_news(
        [{
            "headline": "Spotify Maintains Hold",
            "summary": "The firm left its rating unchanged after the latest report.",
            "datetime": 50,
        }],
        "SPOT",
    ) is None
    assert select_company_news(
        [{
            "headline": "Tesla Price Target Raised",
            "summary": "The new target sits above the last close for the shares.",
            "datetime": 50,
        }],
        "TSLA",
    ) is None

    held = select_company_news(
        [{
            "headline": "Apple: Free Cash Flow Is the Number That Has to Hold",
            "summary": "The column looks at cash generation rather than a rating.",
            "datetime": 40,
        }],
        "AAPL",
    )
    assert held is not None
    assert held.headline == "Apple: Free Cash Flow Is the Number That Has to Hold"

    # "buy" is an advice word, but it must not match inside "buyback".
    buyback = select_company_news(
        [{
            "headline": "Apple announces a large buyback",
            "summary": "The board approved a new repurchase program this quarter.",
            "datetime": 30,
        }],
        "AAPL",
    )
    assert buyback is not None
    assert buyback.headline == "Apple announces a large buyback"


def test_booking_own_name_is_not_counted_as_another_company():
    # "Booking" is on the other-names list and is also a word in Booking Holdings.
    # That used to reject BKNG's own headlines. A real rival still does.
    picked = select_company_news(
        [
            {
                "headline": "Booking Holdings Price Target Raised",
                "summary": "A broker lifted its target after the latest travel note.",
                "datetime": 30,
            },
            {
                "headline": "Booking Holdings raises its full-year outlook",
                "summary": "Travel demand stayed ahead of the same quarter last year.",
                "datetime": 10,
            },
        ],
        "BKNG",
    )
    assert picked is not None
    assert picked.headline == "Booking Holdings raises its full-year outlook"
    assert select_company_news(
        [{
            "headline": "Booking Holdings tops Expedia on summer trips",
            "summary": "Both travel names pointed to stronger demand this season.",
            "datetime": 12,
        }],
        "BKNG",
    ) is None


def test_stricter_rules_pick_bwa_spot_gm_tsla_and_aapl():
    cases = [
        (
            "BWA",
            [
                {
                    "headline": "BorgWarner: Buy, Hold or Sell?",
                    "summary": "A rating roundup that is not a story about the supplier.",
                    "datetime": 30,
                },
                {
                    "headline": "BorgWarner and Tesla win a supply contract",
                    "summary": "The note names two companies and is not BorgWarner alone.",
                    "datetime": 20,
                },
                {
                    "headline": "BorgWarner raises its full-year outlook",
                    "summary": "The supplier pointed to steady demand from automakers.",
                    "datetime": 10,
                },
            ],
            "BorgWarner raises its full-year outlook",
        ),
        (
            "SPOT",
            [
                {
                    "headline": "Spotify Maintains Hold",
                    "summary": "The firm left its rating unchanged after the latest report.",
                    "datetime": 30,
                },
                {
                    "headline": "Spotify adds listeners in the latest quarter",
                    "summary": "Monthly users grew from the same quarter a year earlier.",
                    "datetime": 15,
                },
            ],
            "Spotify adds listeners in the latest quarter",
        ),
        (
            "GM",
            [
                {
                    "headline": "GM stock jumps on a truck rumor",
                    "summary": "The bare ticker is not enough to count as the company name.",
                    "datetime": 40,
                },
                {
                    "headline": "General Motors Price Target Raised",
                    "summary": "A broker set a higher target after the delivery update.",
                    "datetime": 25,
                },
                {
                    "headline": "General Motors raises truck output",
                    "summary": "The company pointed to steady demand for full-size trucks.",
                    "datetime": 12,
                },
            ],
            "General Motors raises truck output",
        ),
        (
            "TSLA",
            [
                {
                    "headline": "Tesla and Apple share a supplier update",
                    "summary": "The note is about two companies, not Tesla on its own.",
                    "datetime": 28,
                },
                {
                    "headline": "Tesla starts production at a new factory",
                    "summary": "The plant began building vehicles for customer deliveries.",
                    "datetime": 14,
                },
            ],
            "Tesla starts production at a new factory",
        ),
        (
            "AAPL",
            [
                {
                    "headline": "Apple Price Target Raised",
                    "summary": "The new target sits above the last close for the shares.",
                    "datetime": 40,
                },
                {
                    "headline": "META, AAPL, AMD... In Focus",
                    "summary": "Traders watched a handful of large technology names today.",
                    "datetime": 35,
                },
                {
                    "headline": "Apple announces a large buyback",
                    "summary": "The board approved a new repurchase program this quarter.",
                    "datetime": 22,
                },
                {
                    "headline": "Apple opens a new store",
                    "summary": "The company added a location and hired more retail staff.",
                    "datetime": 11,
                },
            ],
            "Apple announces a large buyback",
        ),
    ]
    for ticker, articles, headline in cases:
        picked = select_company_news(articles, ticker)
        assert picked is not None, ticker
        assert picked.headline == headline, ticker


def test_no_passing_story_keeps_the_empty_news_message():
    # Nothing left to show becomes the same empty-state line on the card.
    blocked = [
        ("BKNG", "Booking Holdings Price Target Raised"),
        ("BWA", "BorgWarner: Buy, Hold or Sell?"),
        ("SPOT", "Spotify Maintains Hold"),
        ("GM", "General Motors Price Target Raised"),
        ("TSLA", "Tesla and Apple share a supplier update"),
        ("AAPL", "Apple: Buy, Hold or Sell?"),
    ]
    for ticker, headline in blocked:
        assert select_company_news(
            [{
                "headline": headline,
                "summary": "Nothing in this note is a plain story about the company itself.",
                "datetime": 5,
            }],
            ticker,
        ) is None
    assert NO_RECENT_NEWS_MESSAGE == "No recent news about this company yet."


def test_unusable_news_timestamps_are_not_turned_into_jan_1():
    from app.services.news import _iso_from_unix

    assert _iso_from_unix(0) is None
    assert _iso_from_unix(-1) is None
    assert _iso_from_unix(-0.5) is None
    assert _iso_from_unix(None) is None
    assert _iso_from_unix("0") is None
    assert _iso_from_unix("yesterday") is None
    assert _iso_from_unix(True) is None
    assert _iso_from_unix(float("nan")) is None
    assert _iso_from_unix(float("inf")) is None
    assert _iso_from_unix(float("-inf")) is None

    story = {
        "headline": "NVIDIA ships a new chip",
        "summary": "A short summary of the news.",
        "source": "Example Wire",
        "url": "https://example.com/nvda-news",
    }
    for bad in (0, -5, None, "0", "nope", True, float("nan"), float("inf")):
        assert select_company_news([{**story, "datetime": bad}], "NVDA") is None

    picked = select_company_news(
        [
            {**story, "datetime": 0},
            {**story, "headline": "NVIDIA ships a newer chip", "datetime": 1793577600},
        ],
        "NVDA",
    )
    assert picked is not None
    assert picked.news_date == "2026-11-02"
    assert picked.headline == "NVIDIA ships a newer chip"
    assert "1970" not in picked.news_date


def test_date_labels_use_the_card_copy():
    assert format_news_date_label("2026-11-02") == "News from Nov 2"
    assert format_quarter_label("2026-09-30") == "Last quarter (ended Sep 30, 2026)"
    assert format_quarter_label("2026-07-26") == "Last quarter (ended Jul 26, 2026)"
    assert format_news_date_label(None) is None
    assert format_quarter_label("not-a-date") is None
    assert NO_RECENT_NEWS_MESSAGE == "No recent news about this company yet."
