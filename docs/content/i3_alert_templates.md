# I3: Catalyst alert message templates (fun(d) voice)

Written 2026-11-05 (America/New_York) by the Content Writer. These follow the I1 catalyst rule (`/workspace/fund/data/i1-catalyst-rule.md`, §2–§4, §7, §9) and use the same voice as the G2 Updates templates.

The messages use placeholders only and never contain a made-up number, date or headline. Every value comes from the alert payload that I2 stores (§9). If a value a template needs is missing, the server skips the alert (I1 §1) and never fills in a guess.

## Placeholders
- `{name}`: `short_name`, falling back to `company_name` (same as G2).
- `{pct}`: absolute value of `dp`, with one decimal place and no sign. The wording gives the direction.
- `{price}`: `c`, with two decimal places (all 31 trade in US dollars).
- `{quote_date}`: `quote_date_et`, shown as "Nov 5". The word "today" is never used, because the quote may be from an earlier session (I1 §2, step 4).
- `{earnings_date}`: the calendar `date`, shown as "Thu, Nov 6". The words "today" and "tomorrow" are never used. The date stays correct however late the user opens the app.
- `{when}`: built only from a non-empty `hour`. `bmo` becomes ", before the market opens". `amc` becomes ", after the market closes". Any other value or an empty one becomes an empty string, so we never guess the session.
- `{headline}`: the F2b-picked headline, shown exactly as cached.
- `{source}`: the news source name.
- `{date}`: the news date, shown as "Nov 5".

## Templates

### price (|dp| >= 5, new price_key)
1. Up: `Big move: {name} is up {pct}% (as of {quote_date}), at US${price}.`
2. Down: `Big move: {name} is down {pct}% (as of {quote_date}), at US${price}.`

Optional helper line, shown once under the first price alert a user ever sees: `We flag a liked stock when its price moves 5% or more in a day.`

### earnings (calendar date is today or tomorrow ET, new (ticker, date))
3. `Results coming: {name} is scheduled to share its latest quarterly results on {earnings_date}{when}.`

Optional helper line, shown once: `Companies share their results every three months.`

### news (F2b + news24h gate, new fingerprint)
4. With a source: `New for {name}: "{headline}" ({source}, {date}).`
5. Without a source: `New for {name}: "{headline}" ({date}).`

## Rules
- Facts only: `dp`, `c`, `quote_date_et`, the headline, and the earnings `date` and `hour`. No reasons, no predictions.
- No advice words: buy, sell, hold, "time to…", "should you", "don't miss". No hype words: soared, crashed, plunged, skyrocketed, tanked. "Big move" is the only label and only means |dp| >= 5.
- Never call a quote "today's move". Always show `{quote_date}`.
- One template per alert. Don't merge alerts, so each one stays tied to its own dedupe key (I1 §6).
- If a placeholder is missing (except `{when}` and `{source}`, which have the fallbacks above), skip the alert.
- Order alerts newest first. Ties go in Matches order.
- Empty state (no alerts yet, with at least one like): `No big news on your liked stocks right now. We'll flag big price moves, upcoming results and fresh headlines here.`
- Empty state (no likes): reuse G2's `Like a few stocks and their daily updates will show up here.`

## Shape examples (placeholders, not real data)
- `Big move: Sony is down {pct}% (as of {quote_date}), at US${price}.`
- `Results coming: Airbnb is scheduled to share its latest quarterly results on {earnings_date}, after the market closes.`
- `New for Nvidia: "{headline}" ({source}, {date}).`

## Sources
- I1 catalyst rule, revised 2026-11-05 18:40 ET: `/workspace/fund/data/i1-catalyst-rule.md`
- G2 Updates templates (voice, placeholders): `/workspace/fund/content/g2_update_templates.md`
- Finnhub earnings calendar `hour` field (bmo/amc): https://finnhub.io/docs/api/earnings-calendar
