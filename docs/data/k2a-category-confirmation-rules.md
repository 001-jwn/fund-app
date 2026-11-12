# K2a: How an 8-K category gets confirmed

Author: fun(d) Data Specialist, 2026-11-10. Accepted by the Product Lead.

These rules are what the backend uses before it shows an SEC filing line. An item number is only a reason to read the filing. It is never enough to confirm a category, and it never produces a sentence.

`h3_category` is one of: `earnings`, `acquisition_sale`, `leadership`, `guidance`. If the filing is not confirmed, `h3_category` stays empty, `verified` stays false, `summary_plain` stays empty, and nothing is shown.

## What we fetch

For one accession, read the main 8-K document plus at most two exhibits. Exhibit 99.1 comes first. That is three documents at most.

Use the same `SEC_USER_AGENT` as the metadata fetch, the same shared pace of about one request per second, and the same stop on HTTP 403 or 429. Do not change headers, switch hosts, or try to get around a block. A block stops the whole run and sets a short backoff.

Stop reading a document at 2,000,000 bytes and treat it as too long. If the confirming sentence might have been in the unread part, do not confirm. After markup is removed, fewer than 200 bytes of text means the document is unreadable.

Log each fetched document's byte size only. Never log the text.

Cache fetched documents and the result under the exact accession. A 7-day cache is fine. Do not download a confirmed filing again every cycle, and do not download one that has already been marked permanently unconfirmable.

## earnings

The filing is a candidate when item 2.02 is present. Confirm only if the body or the press-release exhibit states results for a completed period (a named quarter or fiscal year).

If the 8-K points to Exhibit 99.1 as the results disclosure, that exhibit has to be fetched and read. If it is missing or the fetch fails, do not confirm.

Do not confirm a conference-call notice, an earnings date, or a future-only outlook.

Fields: `measure` (revenue, net income, or earnings per share, in the filing's own words), `figure` (one value copied word for word, including currency and period), `exhibit_url` (required before a figure sentence is used), `is_quarter` (true only if the text says quarter).

Use `measure` and `figure` only when both are in the exhibit and the body, the exhibit, the prose, and the table do not disagree. If several figures are present and the choice is unclear, or if anything disagrees, leave both empty and use the default line.

Example: AAPL `0000320193-26-000024` confirms earnings, and it is a quarter. The prose says $114.5 billion and a table says 114,477. Those disagree, so use a figure that does not conflict (diluted EPS $2.10) or leave the figure empty.

## acquisition_sale

Candidates are items 1.01 and 2.01 only. Confirm only if the text plainly states a definitive agreement to acquire, to be acquired, or to hand over a named business or assets, or that such a deal completed, and which side the company is on.

Do not confirm credit agreements, guaranties, leases, partnerships, or ordinary commercial agreements. Example: NVDA `0001045810-26-000069` is not a deal.

A deal that is described only under item 7.01 or 8.01 stays hidden. Example: NVDA `0001045810-26-000078`.

Fields: `counterparty`, `side` (`acquirer`, `acquired`, or `seller`), `stage` (`agreed` or `completed`, only as the text states; empty if unclear, which uses the fallback line), `asset` when it is named.

Never call a deal major or material in our own wording. The fallback sentence from the K3 templates is the exception, and it is used only when a confirmed deal is missing a name.

## leadership

The filing is a candidate when item 5.02 is present. Confirm only if the text names a person joining or leaving CEO, CFO, board chair, or board member, or a role the 8-K itself calls a named executive officer.

Do not confirm compensation-only filings, annual-meeting election results, or other officers.

Fields: `person`, `role` (wording unchanged, sentence case unless it is a proper name), `direction` (`joining` or `leaving`), `resigned_or_retired` (true only if the text says resign, resigned, retire, retired, or retirement). "Step down", "transition", "will leave", termination, and non-renewal are false. `eff_date` only if the text states it.

If three or more qualifying people are named, use the K3 fallback leadership line. Example: AAPL `0001140361-26-015711` names three people, so it is confirmed and the fallback line is used. The effective date in that filing is September 1, 2026.

## guidance

Candidates are items 7.01 and 8.01. Never confirm from the item number or from a headline. Confirm only when the text explicitly gives an outlook, guidance, or an expectation for a future period.

Do not confirm completed-period results, dividends, or forward-looking boilerplate.

`direction` comes from the filing's words only: `raised`, `lowered`, `confirmed`, or `unclear`. Missing, hedged, or mixed wording is `unclear`. Raising one measure and lowering another is `unclear`. Never infer a direction by comparing numbers.

`period_label` stays as worded. `measure` and `figure` are stored only when both are stated.

## Leave it hidden

Do not confirm, and do not show a line, when any of these is true:

- The only signal is an item number.
- A required exhibit is missing.
- The fetch fails, returns HTTP 403 or 429, or times out.
- The text is ambiguous.
- More than one category could be confirmed for the same accession. Examples: item 2.02 results plus an Outlook section (NVDA `0001045810-26-000073`), or item 2.02 plus item 5.02 (UBER `0001543151-26-000011`). Do not pick a winner.
- The form is 8-K/A. Keep that accession as its own record. Set `amends_accession` only when the amendment text itself gives the prior accession number. AAPL `0001140361-26-035325` only says the Form 8-K filed on April 20, 2026 and does not give an accession number, so `amends_accession` stays null. Do not infer it from the date. An 8-K/A is never confirmed automatically.
- The text is legal-heavy and has no plain statement.
- The document is unreadable or too long.
- Item 5.02 is only compensation or only an election.
- Item 1.01 or 2.01 is not a qualifying deal.
- The ticker is NTES, SONY, SPOT, TM, or RACE, or the form is not an 8-K.

## Shared rules

One record per exact accession. Never merge filings because they are on the same day or share an item number.

If two confirmed accessions would produce the same line for the same ticker within 7 days, show only the later one. Keep both records.

No advice words and no hype words. Never copy a legal sentence into `summary_plain`.

When a field the sentence needs is empty, use the matching fallback line from `docs/content/k3_8k_templates.md`. The date in the line is the New York calendar date of `accepted_at`, written like `Nov 5`.
