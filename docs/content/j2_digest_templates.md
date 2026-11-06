# J2: Daily "For you" digest templates (fun(d) voice)

Written 2026-11-05 (America/New_York) by the Content Writer, for H2 (John, 2026-11-05 18:30 ET): a short daily "For you" digest at the top of Updates, covering liked stocks that moved or had news since yesterday. It uses the same voice as G2 and I3.

These templates use placeholders only and never contain a made-up number, date or headline. Every value comes from the J1 digest (cache-only). If a value a line needs is missing, that part is skipped and never filled with a guess.

## Payload (J1, agreed in the room 2026-11-05)
`GET /updates` adds `digest: {date, header, intro, items: [{ticker, short_name, line}], more_count, more_line, empty_line}`. `date` is the New York date (YYYY-MM-DD). `items` is always present, with at most 5 entries. There is one item per liked stock that qualifies in a rolling 24-hour window: a cached quote that moved 2% or more either way, or an F2b headline published in that window, or both. Items are ordered biggest move first, then news-only items newest first (not Matches order), so the cap keeps the most notable stocks. The server fills `header`, `intro`, `line`, `more_line` and `empty_line` from the templates below. With no likes, `intro`, `more_line` and `empty_line` are null.

## Placeholders
- `{name}`: `short_name`, falling back to `company_name` (same as G2 and I3).
- `{pct}`: absolute value of `dp`, with one decimal place and no sign. The wording gives the direction.
- `{price}`: `c`, with two decimal places (all 31 trade in US dollars).
- `{quote_date}`: the quote's own date in New York time, shown as "Nov 5".
- `{headline}`: the F2b-picked headline, shown exactly as cached.
- `{source}`: the news source name.
- `{date}`: the headline's date in New York time (not UTC), shown as "Nov 5".
- `{digest_date}`: `digest.date`, shown as "Thu, Nov 5".
- `{count}`: the number of items shown (1 to 5).
- `{more}`: `more_count`, the number of qualifying stocks left out by the cap.

The words "today", "tomorrow" and "yesterday" never appear. Every line carries its own real date, because an item from last night can sit under the next day's `digest.date` (same ruling as I3).

## Header (`header`)
1. `For you, {digest_date}`

## Intro (`intro`, only when `items` isn't empty)
- One item: `1 of your liked stocks has something new.`
- Several: `{count} of your liked stocks have something new.`

## Item lines (`line`, one per item)
2. Price only, up: `{name} is up {pct}% (as of {quote_date}), at US${price}.`
3. Price only, down: `{name} is down {pct}% (as of {quote_date}), at US${price}.`
4. News only, with a source: `In the news for {name}: "{headline}" ({source}, {date}).`
5. News only, without a source: `In the news for {name}: "{headline}" ({date}).`
6. Price and news: line 2 or 3, then a space, then `In the news: "{headline}" ({source}, {date}).` Without a source: `In the news: "{headline}" ({date}).`

Lines 2–5 are the G2 lines word for word, so the digest reads like the rest of Updates. The digest never says "Big move". That label stays reserved for alerts (5% or more), and the digest gate is 2%.

## More (`more_line`, only when `more_count` > 0; otherwise null)
- `+ {more} more in your updates below.`

## Empty state (`empty_line`, has likes and `items` is [])
7. `Quiet one: no price moves of 2% or more and no new headlines for your liked stocks in the last day.`

## No likes
8. Reuse G2's `Like a few stocks and their daily updates will show up here.` Show it once for the whole Updates tab, with no separate digest message.

## Rules
- Facts only: price change, price, dates and headlines. No reasons, no predictions, and no explaining what a headline "means".
- No advice words: buy, sell, hold, "time to…", "should you", "don't miss". No hype words: soared, crashed, plunged, skyrocketed, tanked, huge.
- An item can repeat something an alert already showed. The digest is a daily roundup, and alerts stay separate (H1/H2).
- Don't guess. A price part needs `dp`, `c` and `{quote_date}`, and a news part needs `{headline}` and `{date}`. If a part is missing, drop that part. If both are missing, drop the item.

## Shape example (placeholders, not real data)
```
For you, {digest_date}
2 of your liked stocks have something new.
Sony is down {pct}% (as of {quote_date}), at US${price}. In the news: "{headline}" ({source}, {date}).
In the news for Nvidia: "{headline}" ({source}, {date}).
```

## Sources
- M3 plan, H2 and J1–J4: `/workspace/fund/m3-tasks.md`
- G2 Updates templates (voice and lines): `/workspace/fund/content/g2_update_templates.md`
- I3 alert templates (date rules, no-advice list): `/workspace/fund/content/i3_alert_templates.md`
