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

### 8.3 Names and dates with no year (PL ruling for K2c PR #31, 2026-11-13)
- **Date with no year (exact rule, PL-approved 2026-11-13):** use the year of the filing's New York date, with only two exceptions:
  - The filing is dated in Nov or Dec and the date is in Jan or Feb: use the next year.
  - The filing is dated in Jan or Feb and the date is in Nov or Dec: use the year before.
  - Don't use "nearest year" or "closest of three years".
  - Tests:
    - Filed 2026-12-30, "effective January 5": Jan 5, 2027, future.
    - Filed 2027-01-03, "effective December 31": Dec 31, 2026, past.
    - Filed 2026-06-30, "effective December 31": Dec 31, 2026, future.
    - Filed 2026-06-30, "effective January 15": Jan 15, 2026, past.
    - Filed 2026-11-15, "effective January 10": Jan 10, 2027, future.
    - Filed 2026-11-05, "effective May 1": May 1, 2026, past.
- **Tense vs. date (PL ruling, 2026-11-13, replaces the earlier "will" tweak):**
  - "will …" with a date before the filing's NY date: show the past-tense line if the date is within 7 days before the filing's NY date (normal 8-K timing). If it's more than 7 days before, hide the filing. Test: filed 2026-11-05, "Effective May 1, Jane Doe will step down" is hidden.
  - Any past-tense leaving verb (resigned, retired, stepped down, left, departed, ceased to serve, was removed) with a date after the filing's NY date: hide the filing. Test: filed 2026-11-05, "Jane Doe retired as CFO effective December 1, 2026" is hidden.
  - A board action with a later effective date still shows the future line ("the Board appointed / elected / named Jane Doe … effective June 1"). Test: filed 2026-05-01, "the Board appointed Jane Doe as CFO effective June 1, 2026" shows "will become …, starting Jun 1".
- **Board action dated only by "On …" (PL ruling, 2026-11-13):** if the board appointed, elected or named someone, the only date is a leading "On <date>," on or before the filing's NY date (same day included, per PL 2026-11-14), and there's no effective or starting date, hide the filing. Past tense for this case is on the post-M3 list. Tests: filed 2026-11-05, "On May 1, 2026, the Board appointed Jane Doe as CFO" is hidden, and "On November 5, 2026, the Board appointed Jane Doe as CFO" is also hidden.
- **Self-contradicting sentence (PL ruling, 2026-11-13):** if any sentence in a filing contradicts itself (a tense and date conflict as above), hide the whole filing, not just that person.
- **Post-M3:** recognising past-tense leaving verbs (left, departed, ceased to serve, was removed, stepped down) so they show a line when the date is past. For M3 they always hide.
- **Which date is {eff_date} (QA pre-check, PL-confirmed):** an "effective" or "starting" date always wins. A leading "On <date>," is used only when it's the date of the action itself ("On May 1, 2026, Jane Doe resigned"), never when "announced", "will" or "appointed … effective" follows. Tests:
  - MSFT -224155 reads May 13, not May 14.
  - "Effective May 1, 2026, Jane Doe resigned" shows.
- **Impossible date** ("February 30", or Feb 29 in a year that isn't a leap year): hide the filing; never show the date.
- **Names (PL and CW):**
  - Hide all-caps names.
  - Keep the name exactly as written, including ", Jr." and other suffixes. A comma is allowed only before Jr./Sr./II/III/IV.
  - Lead-in words (Today, Yesterday, Separately, Additionally, Also, Further, Furthermore, Accordingly, Effective) are never part of a name.
  - Hide a name that ends in a particle such as "de".
  - Hide partial or non-person names.
  - Leading initials ("J. P. Smith") are hidden for M3 and are on the post-M3 list.
  - Mr./Ms./Dr. are allowed but dropped from {person}, so "Dr. Jane Doe" reads "Jane Doe". A title with only a surname ("Ms. Doe") is hidden.
  - A leading date clause ("On May 1, 2026," or "Effective May 1,") is accepted but never appears in the line; {eff_date} carries the date.

### 8.4 M4 P0c notes: hide_reason and restated outlook (Data Specialist, 2026-11-15; for Backend P0a)

Checked against main `e3edc67` (`backend/app/services/sec_text.py`, `sec_filings.py`).

**Today on main.** `decide_filing` returns `hide_reason` but nothing stores it (no column, `_apply_decision` drops it). Only two values are ever set: `two_categories` and `ambiguous`. Most hide paths leave it null. Line ~215 labels a filing with no hits but a restated outlook as `ambiguous`.

**A. hide_reason: store one value on every row whose `text_outcome` is `unconfirmable`; null when confirmed or not yet decided.** Use exactly these values (first match wins, in this order):

| value | when (code path on main) |
| --- | --- |
| `skipped_fpi` | ticker in NTES, SONY, SPOT, TM, RACE |
| `not_8k` | form is not 8-K or 8-K/A |
| `amendment` | form 8-K/A (§5 item 6) |
| `too_long` | any document over the §5.1 cutoff |
| `no_text` | no usable document, or `_mark_document_unreadable` (fetch failed or unreadable after retries) |
| `two_categories` | more than one category confirmed (§5 item 5) |
| `restated_outlook` | outlook only repeats an earlier one (see B) and nothing else confirmed. Replaces today's `ambiguous` label at line ~215 |
| `unclear_direction` | guidance with direction missing, hedged or mixed. Replaces today's `ambiguous` at line ~223 |
| `leadership_rejected` | any `_clear_leadership` path: impossible date, tense vs date conflict, "On …" board action on or before the filing date, self-contradicting sentence, rejected name (all §8.3) |
| `no_line` | a category confirmed but `build_summary` returned None (missing name or date, or advice wording) in `_apply_decision` |
| `no_category` | anything else: no confirming text found |

Rules: hide_reason is internal only. Never show it to users or put it in a K3 line. Keep `verified`, `h3_category` and `summary_plain` behavior unchanged. A filing that shows today must still show, and one that hides must still hide, except the change in B.

**Re-deciding old rows.** Rows with `text_outcome` already set are never re-read (`_confirm_pending` takes only null). So after P0a ships, existing rows keep a null hide_reason and the old outlook behavior. P0a should re-decide candidate rows once from cached documents (no new SEC fetches beyond the normal throttle), for example by resetting `text_outcome` to null for `h3_candidate` rows when a stored rules version changes.

**B. "Reaffirmed" vs "reiterated" (the inconsistency).** On main, "reiterate(s/d/ing)" is in `_RESTATED_OUTLOOK`, so the outlook is ignored. But "reaffirm / affirm / confirm" + outlook/guidance sets direction `confirmed`, so:
- a 7.01/8.01 saying "reaffirms its outlook" shows "…confirmed its earlier outlook…", while "reiterates its outlook" hides;
- a 2.02 release saying "reaffirms" hides as `two_categories`, while "reiterates" shows the earnings line alone (TTWO Nov 9 `0001628280-26-072175` is the "reiterates" case).

**Rule (DS recommendation, consistent with §8.2 and the PL M3 override that a repeated outlook is not a new event):** treat confirm / affirm / reaffirm the same as reiterate. The existing "reiterate(s/d/ing)", "as provided on" and "no change to outlook" keep matching exactly as on main (anywhere in the text, no outlook word needed). Only the newly added confirm / affirm / reaffirm need outlook or guidance in the same sentence. Either marks a restated outlook:

*Clarified 2026-11-21 after QA's PR #36 review: the earlier wording here could be read as narrowing the three existing phrases to outlook sentences. That was not intended; it would break the keep-as-before rule (TTWO `0001628280-26-072175`).*

1. A restated outlook never confirms `guidance`. With nothing else confirmed, hide with `restated_outlook`.
2. In a 2.02 release, a restated outlook is not a second category, so the earnings line can show alone (same as TTWO today). That line only says the company shared its quarterly results, so it stays true.
3. If any sentence in the filing restates the outlook, guidance is not confirmed from that filing even if another sentence raises or lowers (today's whole-filing check, unchanged). Hiding a real raise is acceptable; a wrong line is not.
4. The `confirmed` direction and K3's "confirmed its earlier outlook" line become unused. Keep the wording in K3 but dormant until John decides (see list below).

Tests P0a should add: "reaffirms outlook" on 8.01 hides as `restated_outlook`; "reiterates outlook" same; 2.02 + "reaffirms its outlook" shows the earnings line; 2.02 + "raises outlook" still hides as `two_categories`; "raises revenue outlook and reaffirms EPS outlook" on 8.01 hides; "confirmed the date of its conference call" (no outlook word) is not affected; one test per hide_reason value.

**C. Post-M3 items: who decides.**

Need a product call from John (visible to users):
1. Two-category earnings: show the earnings line when a 2.02 release also has a new outlook (today NVDA, UBER and some TTWO quarters always hide).
2. §8.1 "not to stand for re-election": show it as a leadership change or keep it hidden.
3. Restated outlooks: keep hiding them (DS recommendation) or show "confirmed its earlier outlook".
4. How far back the Updates filings go (now 365 days, 10 per ticker; John saw about nine months). PL ruled this intended for M3; only if John wants it shorter.

Team can decide without John (accuracy or technical, PL rules):
- hide_reason storage and re-deciding old rows (P0a), syncing §8.3 and this §8.4 to `docs/data/` (P0a).
- Case d: copy a range with the scale word on both ends in full.
- Exhibit plain-link fallback.
- Leading initials ("J. P. Smith") showing instead of hiding.
- Past tense for "On …" board actions, and past-tense leaving verbs with a past date (wording: CW + PL).
- Frontend fixture wording (P0b).
