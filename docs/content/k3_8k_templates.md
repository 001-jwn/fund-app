# K3: Plain-language SEC filing templates (fun(d) voice)

Written 2026-11-10 (America/New_York) by the Content Writer. These cover the four H3 filing types from K1 (`/workspace/fund/data/k1-8k-source.md`, §2 and §8): earnings, major deal, leadership change and guidance. They use the same voice as the G2 and I3 templates.

Each template fills the `summary_plain` field that K2 stores. A template is used only after the filing's content has been checked and `h3_category` is set. An item number alone never picks a template and never produces a summary (K1 §2, rule 2). If the category is not confirmed, `summary_plain` stays empty and no line is shown.

All placeholders come from the cached filing record or from the verified filing text. No value is ever guessed. Where an optional value is missing, the template uses the plain fallback below it, never an invented value.

## Placeholders
- `{name}`: `short_name`, falling back to `company_name` (same as G2 and I3).
- `{date}`: the filing's accepted date as a New York date, shown as "Nov 5". The words "today", "tomorrow" and "yesterday" are never used.
- `{filing_phrase}`: `an SEC filing` for form 8-K, and `an updated SEC filing` for form 8-K/A.
- `{period_label}`: the period exactly as the filing words it, such as "the full year" or "the next quarter". If the filing does not name one, the template leaves the phrase out.
- `{counterparty}`: the other company in a deal, exactly as the filing names it.
- `{asset}`: the business, brand or assets being handed over, exactly as the filing names them.
- `{person}`: the person's name exactly as the filing writes it.
- `{role}`: the job title exactly as the filing writes it, such as "chief executive officer" or "chief financial officer". Only CEO, CFO, other named executive officers, board chair and board member changes qualify. Routine pay or contract filings do not (K1 §2).
- `{eff_date}`: the date the change starts, shown as "Dec 1", only if the filing states it.
- `{measure}`: what the outlook covers, in the filing's own simple word, such as "revenue" or "earnings per share". Only if the filing states it.
- `{figure}`: a number or range copied word for word from the company's press release exhibit, with its currency and period as written. Only if the exhibit shows it.
- `{filing_url}`: the filing index link, shown by the app as a "Read the filing" link (K4 handles the link).

## Templates
Every line is 1 or 2 sentences.

### earnings (h3_category = earnings)
1. Default: `{name} shared its latest quarterly results in {filing_phrase} on {date}.`
2. With a figure from the press release: `{name} shared its latest quarterly results in {filing_phrase} on {date}. The company reported {figure}.`
   - Use line 2 only if the figure appears in the exhibit and K2 stores the exhibit link. One figure only. If the exhibit and the filing disagree, use line 1.

### major deal (h3_category = acquisition_sale)
3. Agreed to acquire: `{name} agreed to acquire {counterparty}, according to {filing_phrase} on {date}.`
4. Agreed to be acquired: `{name} agreed to be acquired by {counterparty}, according to {filing_phrase} on {date}.`
5. Agreed to hand over a business: `{name} agreed to make {counterparty} the new owner of {asset}, according to {filing_phrase} on {date}.`
6. Deal finished (acquisition): `{name} completed its deal to acquire {counterparty}, according to {filing_phrase} on {date}.`
7. Deal finished (handed over a business): `{name} completed the handover of {asset} to {counterparty}, according to {filing_phrase} on {date}.`
8. Fallback when the deal is confirmed but a name is not stated: `{name} reported a major deal in {filing_phrase} on {date}. The filing has the details.`
   - Pick 3 to 7 only when the filing text states who is on each side. If it is unclear, use line 8.

### leadership change (h3_category = leadership)
9. New person: `{name} announced that {person} will become its {role}{eff_clause}.`
10. Stepping down: `{name} announced that {person}, its {role}, will step down{eff_clause}.`
11. Board member added: `{name} announced that {person} is joining its board of directors{eff_clause}.`
12. Board member leaving: `{name} announced that {person} is leaving its board of directors{eff_clause}.`
13. Fallback when the details are unclear: `{name} announced a leadership change in {filing_phrase} on {date}.`
   - `{eff_clause}` is `, starting {eff_date}` when the filing states a start date, and an empty string otherwise.
   - If one filing covers two people, use two sentences (one per person), never more.
   - The line says "announced", not "has left" or "has joined", so it is correct whenever the user reads it.

### guidance (h3_category = guidance)
"Guidance" means the company's own estimate of what it expects. The app calls it the company's outlook.
14. Raised: `{name} raised its outlook{for_clause}, according to {filing_phrase} on {date}.`
15. Lowered: `{name} lowered its outlook{for_clause}, according to {filing_phrase} on {date}.`
16. Confirmed: `{name} confirmed its earlier outlook{for_clause}, according to {filing_phrase} on {date}.`
17. Changed with no clear direction: `{name} updated its outlook{for_clause}, according to {filing_phrase} on {date}.`
18. With a figure from the press release: add one sentence, `The company now expects {measure} of {figure}.`
   - `{for_clause}` is ` for {period_label}` when the filing names a period, and an empty string otherwise.
   - Pick 14, 15 or 16 only when the filing text clearly says raised, lowered or confirmed. Anything unclear uses line 17. Never pick a direction from an item number or from a headline alone.
   - Add the sentence in line 18 only when `{measure}` and `{figure}` both come word for word from the exhibit.

### Helper lines (shown once per user, under the first filing line they ever see)
- `An SEC filing is a report a company must send to the US regulator, the Securities and Exchange Commission.`
- Under the first guidance line: `An outlook is the company's own estimate of what it expects. It is not a promise.`

## Rules
- Facts only: the form type, the filing date and what the filing text clearly says. No reasons, no predictions, no opinions about what it means for the stock price.
- No advice words: buy, sell, hold, "time to…", "should you", "don't miss". No hype words: soared, crashed, plunged, skyrocketed, tanked, blockbuster, shock. Words like "raised", "lowered" and "agreed to acquire" describe what the company did, and nothing more.
- Never call the form by its code in the user-facing line. Say "SEC filing", not "8-K" or "Item 2.02". The words "Big move" stay reserved for 5% price alerts (I3).
- Never say "today", "tomorrow" or "yesterday". Always show the real date.
- One filing, one line. Never merge two filings, even if they share the same ticker, day and item numbers (K1 §7). If two filings would give the same line for the same ticker in a short window, K2 shows only the latest (K1 §7, rule 3).
- Copy names, titles and figures exactly as the filing words them. Do not round, convert or restate a figure.
- Strip legal wording. No sentence quotes dense legal text.
- Strict 8-K scope: no lines for NTES, SONY, SPOT, TM or RACE (John's decision, Nov 9). A 6-K never gets one of these lines.
- If a required placeholder is missing, use the fallback line in that group. If there is no fallback, show nothing.

## Shape examples (placeholders, not real data)
- `Airbnb shared its latest quarterly results in an SEC filing on {date}.`
- `Uber announced that {person}, its chief financial officer, will step down, starting {eff_date}.`
- `Nvidia raised its outlook for {period_label}, according to an SEC filing on {date}.`
- `Take-Two agreed to acquire {counterparty}, according to an SEC filing on {date}.`

## Hand-off notes for K2, K4 and K5
- Fill `summary_plain` only after `h3_category` is confirmed from the filing text. K5 should spot-check that the text matches the filing for several liked tickers.
- Store `{person}`, `{role}`, `{counterparty}`, `{asset}`, `{eff_date}`, `{figure}` and the exhibit link with the record so QA can trace each word back to the filing.
- 8-K/A filings use `an updated SEC filing` and are separate records (K1 §7).

## Sources
- K1 source doc, §2 (categories), §7 (dedupe), §8 (fields): `/workspace/fund/data/k1-8k-source.md`
- SEC investor bulletin, How to Read an 8-K: https://www.sec.gov/files/readan8k.pdf
- SEC Form 8-K item list: https://www.sec.gov/files/form8-k.pdf
- Voice and rules: `/workspace/fund/content/i3_alert_templates.md` and `/workspace/fund/content/g2_update_templates.md`
