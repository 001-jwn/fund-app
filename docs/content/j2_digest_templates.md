# J2: Daily "For you" digest templates (fun(d) voice)

Written 2026-11-05 (America/New_York) by the Content Writer, for H2 (John, 2026-11-05 18:30 ET): a short daily "For you" digest at the top of Updates, covering liked stocks that moved or had news since yesterday. It uses the same voice as G2 and I3.

These templates use placeholders only and never contain a made-up number, date or headline. Every value comes from the J1 digest payload (cache-only). If J1 names its fields differently, the Backend maps them to the placeholders below, and the wording doesn't change. If a value a line needs is missing, that line is skipped and never filled with a guess.

## Placeholders
- `{name}`: `short_name`, falling back to `company_name` (same as G2 and I3).
- `{pct}`: absolute value of `dp`, with one decimal place and no sign. The wording gives the direction.
- `{price}`: `c`, with two decimal places (all 31 trade in US dollars).
- `{quote_date}`: the quote's own date in New York time, shown as "Nov 5".
- `{headline}`: the F2b-picked headline, shown exactly as cached.
- `{source}`: the news source name.
- `{date}`: the news date, shown as "Nov 5".
- `{digest_date}`: the date the digest was built, in New York time, shown as "Thu, Nov 5".
- `{count}`: the number of liked stocks that have at least one line in the digest.

The words "today", "tomorrow" and "yesterday" never appear in the copy. Real dates are always used instead (same ruling as I3).

## Digest header
1. `For you, {digest_date}`

## Intro line (pick one)
2. One stock: `1 of your liked stocks has something new.`
3. Several: `{count} of your liked stocks have something new.`

## Per-stock lines
J1 decides which stocks count as "moved" and which headlines are new. These lines only say what happened. For each included stock, show its price line (if it moved), then its news line (if it has news).

4. Price up: `{name} is up {pct}% (as of {quote_date}), at US${price}.`
5. Price down: `{name} is down {pct}% (as of {quote_date}), at US${price}.`
6. News with a source: `In the news for {name}: "{headline}" ({source}, {date}).`
7. News without a source: `In the news for {name}: "{headline}" ({date}).`

Lines 4–7 are the G2 lines word for word, so the digest reads the same as the rest of Updates. There is no "flat" line, because a stock that didn't move isn't in the digest for its price.

## Quiet day (has likes, nothing qualifies)
8. `Quiet one: no big moves or new headlines for your liked stocks since the last digest.`

## No likes
9. Reuse G2's `Like a few stocks and their daily updates will show up here.` (one empty line for the whole Updates tab, no separate digest message).

## Rules
- Keep it short. Show at most 5 stocks, in Matches order. If more qualify, end with `+ {more} more in your updates below.`, where `{more}` is the count not shown.
- Facts only: price change, price, dates and headlines. No reasons, predictions or summaries of what a headline "means".
- No advice words: buy, sell, hold, "time to…", "should you", "don't miss". No hype words: soared, crashed, plunged, skyrocketed, tanked, huge.
- If a line I3 already showed as an alert has the same item, the digest can repeat it. The digest is a daily roundup, and alerts stay separate (H1/H2).
- Don't guess. If a stock has no `{quote_date}` or price, skip its price line. If it has no headline, skip its news line. If both are skipped, leave the stock out and don't count it in `{count}`.

## Shape example (placeholders, not real data)
```
For you, {digest_date}
2 of your liked stocks have something new.
Sony is down {pct}% (as of {quote_date}), at US${price}.
In the news for Nvidia: "{headline}" ({source}, {date}).
```

## Sources
- M3 plan, H2 and J1–J4: `/workspace/fund/m3-tasks.md`
- G2 Updates templates (voice and lines): `/workspace/fund/content/g2_update_templates.md`
- I3 alert templates (date rules, no-advice list): `/workspace/fund/content/i3_alert_templates.md`
