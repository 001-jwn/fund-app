"""Confirm an 8-K category from filing text and build the K3 line.

Item numbers only decide whether text is worth reading. They never confirm a
category and they never produce a sentence. Unsure means hide.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
DUPLICATE_WINDOW = timedelta(days=7)
MIN_TEXT_BYTES = 200

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_FULL_MONTHS = {
    "january": "Jan",
    "february": "Feb",
    "march": "Mar",
    "april": "Apr",
    "may": "May",
    "june": "Jun",
    "july": "Jul",
    "august": "Aug",
    "september": "Sep",
    "october": "Oct",
    "november": "Nov",
    "december": "Dec",
}

_ADVICE = re.compile(
    r"\b(?:buy|sell|hold|soared|crashed|plunged|skyrocketed|tanked|blockbuster|shock)\b"
    r"|time to|should you|don'?t miss|\bbig move\b",
    re.I,
)
_ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")
_UP = "A-ZÀ-ÖØ-Þ"
_LETTERS = "A-Za-zÀ-ÖØ-öø-ÿ"
# A comma is allowed only directly before a suffix: "John Smith, Jr."
_WORD_GAP = r"[ \u00a0]+"
_SUFFIX_GAP = r"(?:[ \u00a0]*,[ \u00a0]+|[ \u00a0]+)"
_NAME_WORD = rf"[{_UP}][{_LETTERS}'’\-]*[{_LETTERS}]"
_NAME_INITIAL = rf"[{_UP}]\."
_NAME_SUFFIX = r"(?:Jr\.|Sr\.|II|III|IV)"
_NAME_PARTICLE = r"(?:de|del|van|la|di)"
_NAME_INNER = rf"(?:{_NAME_PARTICLE}|{_NAME_INITIAL}|{_NAME_WORD})"
_NAME = rf"(?-i:({_NAME_WORD}(?:{_WORD_GAP}{_NAME_INNER}){{0,5}}(?:{_SUFFIX_GAP}{_NAME_SUFFIX})?))"
_DATE_LEAD = (
    r"(?:On\s+[A-Za-z]+\s+\d{1,2},\s+\d{4},\s+"
    r"|(?:[Ee]ffective|[Ss]tarting)\s+[A-Za-z]+\s+\d{1,2},\s+)"
)
_HONORIFIC = r"(?:Mr|Ms|Mrs|Dr)\.\s+"
# The name starts after a date clause or an honorific, or at the sentence / "that".
_NAME_BOUND = (
    rf"(?:{_DATE_LEAD}(?:{_HONORIFIC})?|{_HONORIFIC}|^|\b(?:that|announced)\s+(?:{_HONORIFIC})?)"
)
_SUFFIXES = frozenset({"Jr.", "Sr.", "II", "III", "IV"})
_PARTICLES = frozenset({"de", "del", "van", "la", "di"})
_BLOCKED_NAME = frozenset({
    "holdings",
    "inc",
    "corporation",
    "company",
    "llc",
    "group",
    "interim",
    "acting",
    "senior",
    "executive",
    "vice",
    "president",
    "chief",
    "officer",
    "mr",
    "dr",
})
_OFFICER_ROLE = (
    r"chief executive officer|chief financial officer|\bCEO\b|\bCFO\b|"
    r"lead independent director|"
    r"board chair|chair of the board|chairman of the board|chairperson of the board"
)
# A comma clause may sit between a person's name and the verb ("Jane Doe, the CFO, will...").
_APPOS = r"(?:\s*,\s*[\s\S]{0,220}?)?"
# A named executive officer confirms leadership. The phrase is not a job title.
_NEO = r"(?:\b(?:a|an|its|the)\s+)?\bnamed executive officer\b"
_REAL_TITLE = re.compile(
    r"\b(chief [a-z]+ officer|CEO|CFO|COO|lead independent director|"
    r"board chair|chair of the board|chairman of the board|chairperson of the board)\b",
    re.I,
)
_GUIDANCE_LATER = re.compile(
    r"\b(?:will|to)\s+(?:provide|discuss|give|issue)\b[\s\S]{0,120}?\b(?:guidance|outlook)\b",
    re.I,
)
# A restated outlook is not a new event. Hide the filing instead of saying "now expects".
_RESTATED_OUTLOOK = re.compile(
    r"\bas provided on\b|\bno change to outlook\b|\breiterat(?:e|es|ed|ing)\b",
    re.I,
)
_MONEY = r"\$[\d,]+(?:\.\d+)?"
_SCALE = r"(?:billion|million|thousand)"
# The whole amount, including a range and its scale word. Never the first dollar alone.
_GUIDANCE_FIGURE = re.compile(
    rf"({_MONEY}\s+to\s+{_MONEY}\s+{_SCALE}"
    rf"|{_MONEY}\s*[-–—]\s*{_MONEY}\s+{_SCALE}"
    rf"|between\s+{_MONEY}\s+and\s+{_MONEY}\s+{_SCALE}"
    rf"|{_MONEY}\s+{_SCALE})",
    re.I,
)
_NEGATION = re.compile(r"\b(?:not|no|never|neither|nor|cannot)\b|n't\b", re.I)
_EXPLICIT_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_NOT_A_NAME = frozenset({
    "did",
    "not",
    "does",
    "chief",
    "financial",
    "executive",
    "officer",
    "president",
    "vice",
    "senior",
    "director",
    "independent",
    "lead",
    "board",
    "chair",
    "chairman",
    "chairperson",
    "company",
    "current",
    "today",
    "yesterday",
    "separately",
    "additionally",
    "also",
    "further",
    "furthermore",
    "accordingly",
    "effective",
})
_BAD_DEAL = re.compile(
    r"\b(?:credit agreement|guarant(?:y|ee)|lease agreement|partnership agreement|"
    r"commercial agreement|supply agreement|license agreement)\b",
    re.I,
)
_BOILER = re.compile(
    r"forward-looking statements|safe harbor|private securities litigation",
    re.I,
)


def plain_text(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(?:p|div|tr|h\d|li)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    # Decode entities before any matcher runs. &#160; and &nbsp; become U+00A0.
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def text_is_unreadable(text: str) -> bool:
    return len((text or "").encode("utf-8")) < MIN_TEXT_BYTES


def ny_dates(accepted_at: str | None) -> tuple[str, str] | None:
    """Return (YYYY-MM-DD, 'Nov 5') in America/New_York, or None."""
    parsed = _parse_accepted(accepted_at)
    if parsed is None:
        return None
    local = parsed.astimezone(NEW_YORK)
    pretty = f"{_MONTHS[local.month - 1]} {local.day}"
    return local.date().isoformat(), pretty


def decide_filing(*, ticker: str, form: str, items: list[str], accession: str, documents: list[dict]) -> dict:
    """Decide from text. `retry` means a later run may try again."""
    blank = _blank(outcome="unconfirmable")
    if ticker in {"NTES", "SONY", "SPOT", "TM", "RACE"}:
        return blank
    if form not in {"8-K", "8-K/A"}:
        return blank
    usable = [doc for doc in documents if _usable(doc)]
    if form == "8-K/A":
        blank["amends_accession"] = _prior_accession(accession, documents)
        return blank
    if any(doc.get("too_long") for doc in documents):
        return blank
    if not usable:
        return blank

    hits = []
    earnings = _earnings(items, usable)
    if earnings is not None:
        hits.append(earnings)
    deal = _deal(items, usable)
    if deal is not None:
        hits.append(deal)
    leaders = _leadership(items, usable, _filing_year(accession))
    if leaders is not None:
        hits.append(leaders)
    guidance = _guidance(items, usable)
    if guidance is not None:
        hits.append(guidance)
    if len(hits) != 1:
        if len(hits) > 1:
            reason = "two_categories"
        elif _outlook_is_restated(usable):
            reason = "ambiguous"
        else:
            reason = None
        return _blank(outcome="unconfirmable", hide_reason=reason)
    found = hits[0]
    # A clear raise, lower, or reaffirmation can show. Mixed or missing direction cannot.
    if found.get("h3_category") == "guidance" and found.get("guide_direction") not in {"raised", "lowered", "confirmed"}:
        return _blank(outcome="unconfirmable", hide_reason="ambiguous")
    found["text_outcome"] = "confirmed"
    found["verified"] = True
    return found


def build_summary(*, category: str | None, form: str, accepted_at: str | None, name: str, fields: dict) -> str | None:
    """K3 sentence. Empty fields use that group's fallback. None hides the row."""
    dated = ny_dates(accepted_at)
    if not category or not name or dated is None:
        return None
    _date_ny, pretty = dated
    phrase = "an updated SEC filing" if form == "8-K/A" else "an SEC filing"
    if category == "earnings":
        line = _earnings_line(name, phrase, pretty, fields)
    elif category == "acquisition_sale":
        line = _deal_line(name, phrase, pretty, fields)
    elif category == "leadership":
        line = _leadership_line(name, phrase, pretty, fields, _date_ny)
    elif category == "guidance":
        line = _guidance_line(name, phrase, pretty, fields)
    else:
        return None
    if not line or _ADVICE.search(line):
        return None
    return line


def same_line_within_window(left_at: str | None, right_at: str | None) -> bool:
    left = _parse_accepted(left_at)
    right = _parse_accepted(right_at)
    if left is None or right is None:
        return False
    return abs(left - right) <= DUPLICATE_WINDOW


def _blank(outcome: str, hide_reason: str | None = None) -> dict:
    return {
        "text_outcome": outcome,
        "verified": False,
        "h3_category": None,
        "summary_plain": None,
        "amends_accession": None,
        "measure": None,
        "figure": None,
        "exhibit_url": None,
        "is_quarter": None,
        "counterparty": None,
        "side": None,
        "stage": None,
        "asset": None,
        "person": None,
        "role": None,
        "lead_direction": None,
        "resigned_or_retired": None,
        "eff_date": None,
        "guide_direction": None,
        "period_label": None,
        "leaders_json": None,
        "hide_reason": hide_reason,
    }


def _usable(doc: dict) -> bool:
    if doc.get("too_long"):
        return False
    text = doc.get("text") or ""
    return not text_is_unreadable(text)


def _combined(docs: list[dict]) -> str:
    return "\n".join(doc.get("text") or "" for doc in docs)


def _sentences(text: str) -> list[str]:
    protected = re.sub(
        r"\b(?:[A-ZÀ-ÖØ-Þ]|Jr|Sr|Mr|Ms|Dr)\.",
        lambda match: match.group(0).replace(".", "\0"),
        text or "",
    )
    parts = re.split(r"(?<=[.!?])\s+", protected)
    kept = []
    for part in parts:
        sentence = part.replace("\0", ".").strip()
        if not sentence or _BOILER.search(sentence):
            continue
        kept.append(sentence)
    return kept


def _prior_accession(accession: str, documents: list[dict]) -> str | None:
    text = _combined(documents)
    if not re.search(r"\bamend", text, re.I):
        return None
    found = [item for item in _ACCESSION.findall(text) if item != accession]
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return None


def _earnings(items: list[str], docs: list[dict]) -> dict | None:
    if "2.02" not in items:
        return None
    exhibit = next((doc for doc in docs if doc.get("exhibit") == "99.1"), None)
    if exhibit is None:
        return None
    body = _combined(docs)
    if not _completed_results(exhibit.get("text") or "") and not _completed_results(body):
        return None
    measure, figure = _pick_figure(docs)
    result = _blank(outcome="confirmed")
    result.update(
        {
            "h3_category": "earnings",
            "verified": True,
            "measure": measure,
            "figure": figure,
            "exhibit_url": exhibit.get("url"),
            "is_quarter": bool(re.search(r"\bquarter\b", body, re.I)),
        }
    )
    return result


def _completed_results(text: str) -> bool:
    period = re.search(
        r"\b(?:quarter|fiscal year|full year|year|three months|six months|nine months)\s+ended\b"
        r"|\bresults for (?:its |the )?(?:first |second |third |fourth |fiscal )?(?:quarter|year)\b"
        r"|\bfiscal\s+\d{4}\s+(?:first |second |third |fourth )?quarter\b",
        text,
        re.I,
    )
    results = re.search(r"\b(?:results|revenue|net income|net sales|earnings per share)\b", text, re.I)
    if not period or not results:
        return False
    if re.search(r"\b(?:will report|earnings date|scheduled to report|conference call to discuss)\b", text, re.I):
        if not re.search(r"\b(?:ended|reported|posted)\b", text, re.I):
            return False
    return True


def _pick_figure(docs: list[dict]) -> tuple[str | None, str | None]:
    """One prose figure whose measure does not disagree across prose or tables."""
    buckets: dict[str, list[tuple[str, str]]] = {"revenue": [], "net income": [], "eps": []}
    figure_re = r"(\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|thousand))?)"
    patterns = (
        (r"\b(diluted earnings per share|basic earnings per share|earnings per share|diluted eps)\b", "eps"),
        (r"\b(net income)\b", "net income"),
        (r"\b(revenue|net sales|total net sales)\b", "revenue"),
    )
    for doc in docs:
        text = doc.get("text") or ""
        for sentence in _sentences(text):
            for pattern, bucket in patterns:
                match = re.search(rf"{pattern}.{{0,50}}?(?:of|were|was|:)?\s*{figure_re}", sentence, re.I)
                if match is None:
                    continue
                buckets[bucket].append((match.group(1).strip().lower(), re.sub(r"\s+", " ", match.group(2).strip())))
        for label, value in _table_pairs(doc.get("raw") or ""):
            bucket = _table_bucket(label)
            if bucket is None:
                continue
            cleaned = re.sub(r"\s+", " ", value).strip()
            if cleaned:
                buckets[bucket].append((bucket, cleaned))
    clean: list[tuple[str, str]] = []
    for pairs in buckets.values():
        if not pairs:
            continue
        prose = [(label, figure) for label, figure in pairs if figure.startswith("$")]
        if len({_amount(figure) for _label, figure in pairs if _amount(figure) is not None}) > 1:
            continue
        if len(prose) == 1:
            clean.append(prose[0])
        elif len(prose) > 1 and len({figure for _label, figure in prose}) == 1:
            clean.append(prose[0])
    if len(clean) != 1:
        return None, None
    return clean[0]


def _table_pairs(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for row in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", raw or ""):
        cells = [plain_text(cell) for cell in re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", row)]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        # A bare "$" (no digits) is a currency marker, not a figure. Use the next numeric cell.
        values = [cell for cell in cells[1:] if re.search(r"\d", cell)]
        if not values:
            continue
        pairs.append((cells[0], values[0]))
    return pairs


def _table_bucket(label: str) -> str | None:
    lowered = label.lower()
    if "earnings per share" in lowered or re.search(r"\beps\b", lowered):
        return "eps"
    if "net income" in lowered:
        return "net income"
    if "revenue" in lowered or "net sales" in lowered:
        return "revenue"
    return None


def _amount(figure: str) -> float | None:
    text = figure.lower().replace("$", "").replace(",", "").strip()
    mult = 1.0
    if "billion" in text:
        mult = 1_000_000_000.0
        text = text.replace("billion", "")
    elif "million" in text:
        mult = 1_000_000.0
        text = text.replace("million", "")
    elif "thousand" in text:
        mult = 1_000.0
        text = text.replace("thousand", "")
    try:
        return float(text.strip()) * mult
    except ValueError:
        return None


def _deal(items: list[str], docs: list[dict]) -> dict | None:
    if "1.01" not in items and "2.01" not in items:
        return None
    found = None
    for sentence in _sentences(_combined(docs)):
        parsed = _deal_sentence(sentence)
        if parsed is None:
            continue
        if found is not None and (
            parsed["side"] != found["side"] or parsed["stage"] != found["stage"] or parsed["counterparty"] != found["counterparty"]
        ):
            found["stage"] = None
            break
        found = parsed
    if found is None:
        return None
    result = _blank(outcome="confirmed")
    result.update({"h3_category": "acquisition_sale", "verified": True, **found})
    return result


def _deal_sentence(sentence: str) -> dict | None:
    if _BAD_DEAL.search(sentence) and not re.search(r"\b(?:acquir|sell|sale of|handover|disposition)\b", sentence, re.I):
        return None
    patterns = (
        ("acquirer", "completed", r"\bcompleted (?:its |the )?acquisition of\s+(.+?)(?:\.|$)"),
        ("seller", "completed", r"\bcompleted the (?:sale|handover|disposition) of\s+(.+?)\s+to\s+(.+?)(?:\.|$)"),
        ("acquired", "agreed", r"\b(?:definitive agreement to be acquired by|agreed to be acquired by)\s+(.+?)(?:\.|$)"),
        ("acquirer", "agreed", r"\b(?:definitive agreement to acquire|agreed to acquire)\s+(.+?)(?:\.|$)"),
        ("seller", "agreed", r"\b(?:definitive agreement to sell|agreed to sell)\s+(.+?)\s+to\s+(.+?)(?:\.|$)"),
    )
    for side, stage, pattern in patterns:
        match = re.search(pattern, sentence, re.I)
        if match is None:
            continue
        if side == "seller":
            asset = _clean_party(match.group(1))
            counterparty = _clean_party(match.group(2))
        else:
            asset = None
            counterparty = _clean_party(match.group(1))
        if not counterparty:
            return None
        return {"side": side, "stage": stage, "counterparty": counterparty, "asset": asset}
    return None


def _clean_party(value: str) -> str | None:
    text = re.sub(r"\s+", " ", value).strip(" .;,")
    text = re.split(r"\s+(?:under|pursuant|dated)\s+", text, maxsplit=1)[0].strip(" .;,")
    text = re.sub(r"^(?:its|the)\s+", "", text, flags=re.I)
    if len(text) < 2 or text.lower() in {"company", "business", "assets"}:
        return None
    return text


def _filing_year(accession: str) -> int | None:
    match = re.fullmatch(r"\d{10}-(\d{2})-\d{6}", (accession or "").strip())
    if match is None:
        return None
    year = int(match.group(1))
    if year >= 70:
        return 1900 + year
    return 2000 + year


def _leadership(items: list[str], docs: list[dict], filing_year: int | None) -> dict | None:
    if "5.02" not in items:
        return None
    people = []
    seen = set()
    for sentence in _sentences(_combined(docs)):
        if re.search(r"\bannual meeting\b", sentence, re.I) and re.search(r"\belected\b", sentence, re.I):
            continue
        person = _leader_in_sentence(sentence, filing_year)
        if person is None:
            continue
        key = (
            person["person"].lower(),
            (person.get("role") or "").lower(),
            person.get("lead_direction") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        people.append(person)
    if not people:
        return None
    result = _blank(outcome="confirmed")
    result["h3_category"] = "leadership"
    result["verified"] = True
    if len(people) >= 3:
        return result
    if len(people) == 1:
        result.update(people[0])
        return result
    result["leaders_json"] = people
    return result


def _sentence_hides_leadership(sentence: str, filing_year: int | None) -> bool:
    """Hide when the sentence itself is negated or names an earlier year."""
    if _NEGATION.search(sentence):
        return True
    years = [int(year) for year in _EXPLICIT_YEAR.findall(sentence)]
    if not years:
        return False
    if filing_year is None:
        return True
    return any(year < filing_year for year in years)


def _leader_in_sentence(sentence: str, filing_year: int | None) -> dict | None:
    if _sentence_hides_leadership(sentence, filing_year):
        return None
    role = _OFFICER_ROLE
    leaving = (
        rf"{_NAME_BOUND}{_NAME}\s+(?:has\s+|will\s+)?resign(?:ed|s)?\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+will\s+transition\s+from\s+(?:his|her|their)\s+role\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}{_APPOS}\s+will\s+step\s+down\s+from\s+(?:his|her|their)\s+role(?:\s+as\s+(?:its\s+|the\s+)?({role}))?",
        rf"{_NAME_BOUND}{_NAME}\s+will\s+(?:retire|step\s+down|transition|leave)(?:\s+from)?(?:\s+the\s+role\s+of)?\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+will\s+step\s+down\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+will\s+transition\s+from\s+(?:the\s+role\s+of\s+)?(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+will\s+leave\s+(?:the\s+role\s+of\s+)?(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+(?:has\s+)?retir(?:ed|e|ement)\s+as\s+(?:its\s+|the\s+)?({role})",
    )
    joining = (
        rf"\bappointed\s+(?:{_HONORIFIC})?{_NAME}{_APPOS}\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}\s+(?:has been|was|will be)\s+appointed\s+as\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}{_APPOS}\s+will\s+assume\s+the\s+role\s+of\s+(?:its\s+|the\s+)?({role})",
        rf"{_NAME_BOUND}{_NAME}{_APPOS}\s+will\s+become\s+(?:its\s+|the\s+)?({role})",
    )
    board_join = (
        rf"\bappointed\s+(?:{_HONORIFIC})?{_NAME}\s+to\s+(?:its\s+|the\s+)?board of directors"
        rf"|{_NAME_BOUND}{_NAME}\s+will\s+join\s+(?:its\s+|the\s+)?board of directors"
    )
    board_leave = rf"{_NAME_BOUND}{_NAME}\s+will\s+(?:leave|resign from)\s+(?:its\s+|the\s+)?board of directors"
    for pattern in leaving:
        found = _matched_leader(pattern, sentence, "leaving")
        if found:
            return found
    for pattern in joining:
        found = _matched_leader(pattern, sentence, "joining")
        if found:
            return found
    match = re.search(board_join, sentence, re.I)
    if match:
        person = next((group for group in match.groups() if group), None)
        if person:
            found = _leader_fields(person, "board of directors", "joining", sentence)
            if found:
                return found
    match = re.search(board_leave, sentence, re.I)
    if match:
        found = _leader_fields(match.group(1), "board of directors", "leaving", sentence)
        if found:
            return found
    return _named_executive_officer(sentence)


def _matched_leader(pattern: str, sentence: str, direction: str) -> dict | None:
    for match in re.finditer(pattern, sentence, re.I):
        groups = match.groups()
        person = groups[0]
        role = groups[1] if len(groups) > 1 else None
        if not role:
            role = _real_title(sentence)
        if not role:
            continue
        found = _leader_fields(person, role, direction, sentence)
        if found:
            return found
    return None


def _named_executive_officer(sentence: str) -> dict | None:
    gap = r"[\s\S]{0,80}?"
    patterns = (
        (rf"\bappointed\s+{_NAME}\s+as\s+{gap}{_NEO}", "joining"),
        (rf"{_NAME_BOUND}{_NAME}\s+(?:has been|was|will be)\s+appointed\s+as\s+{gap}{_NEO}", "joining"),
        (rf"{_NAME_BOUND}{_NAME}\s+will\s+become\s+{gap}{_NEO}", "joining"),
        (rf"{_NAME_BOUND}{_NAME}\s+(?:has\s+|will\s+)?resign(?:ed|s)?\s+as\s+{gap}{_NEO}", "leaving"),
        (rf"{_NAME_BOUND}{_NAME}\s+will\s+step\s+down\s+as\s+{gap}{_NEO}", "leaving"),
        (rf"{_NAME_BOUND}{_NAME}\s+will\s+(?:retire|leave|transition)\s+as\s+{gap}{_NEO}", "leaving"),
        (rf"{_NAME_BOUND}{_NAME}\s+(?:has\s+)?retired\s+as\s+{gap}{_NEO}", "leaving"),
    )
    for pattern, direction in patterns:
        match = re.search(pattern, sentence, re.I)
        if match is None:
            continue
        found = _leader_fields(match.group(1), _real_title(sentence), direction, sentence)
        if found:
            return found
    return None


def _real_title(sentence: str) -> str | None:
    found = []
    for match in _REAL_TITLE.finditer(sentence):
        title = _role_case(match.group(1))
        if title not in found:
            found.append(title)
    if len(found) == 1:
        return found[0]
    return None


def _name_key(token: str) -> str:
    return token.lower().rstrip(".,")


def _is_name_word(token: str) -> bool:
    """A word needs lowercase letters. All caps, and a run of capitals, stay hidden."""
    if not token or not token[0].isalpha() or not token[0].isupper():
        return False
    if _name_key(token) in _NOT_A_NAME or _name_key(token) in _BLOCKED_NAME:
        return False
    pieces = re.split(r"['’\-]", token)
    if any(not piece or not piece.isalpha() for piece in pieces):
        return False
    for piece in pieces:
        if not piece[0].isupper():
            return False
        if len(piece) > 1 and not any(ch.islower() for ch in piece):
            return False
        if any(left.isupper() and right.isupper() for left, right in zip(piece, piece[1:])):
            return False
    return True


def _valid_person_name(name: str) -> bool:
    parts = [part.rstrip(",") for part in name.split(" ") if part.rstrip(",")]
    if not 2 <= len(parts) <= 6 or _name_key(parts[0]) == "the":
        return False
    core = parts[:-1] if parts[-1] in _SUFFIXES else parts
    if not core or any(part in _SUFFIXES for part in core):
        return False
    words = 0
    for part in core:
        key = _name_key(part)
        if key in _NOT_A_NAME or key in _BLOCKED_NAME or "n't" in key:
            return False
        if key in _PARTICLES:
            if part == core[-1]:
                return False
            continue
        if re.fullmatch(r"[A-ZÀ-ÖØ-Þ]\.", part):
            continue
        if not _is_name_word(part):
            return False
        words += 1
    return words >= 2


def _leader_fields(person: str, role: str | None, direction: str, sentence: str) -> dict | None:
    cleaned = person.replace("\u00a0", " ")
    cleaned = re.sub(r" +", " ", cleaned).strip()
    if not _valid_person_name(cleaned):
        return None
    if role and _role_case(role) == "named executive officer":
        role = _real_title(sentence)
    stored = _role_case(role) if role else None
    if stored == "named executive officer":
        stored = None
    if _impossible_calendar_day(sentence):
        return None
    resigned = bool(re.search(r"\b(?:resign|resigned|retire|retired|retirement)\b", sentence, re.I))
    shown, year = _eff_date(sentence)
    return {
        "person": cleaned,
        "role": stored,
        "lead_direction": direction,
        "resigned_or_retired": resigned,
        "eff_date": shown,
        "eff_year": year,
    }


def _role_case(role: str) -> str:
    words = []
    for word in re.sub(r"\s+", " ", role).strip().split(" "):
        if word.isupper() and len(word) <= 4:
            words.append(word)
        else:
            words.append(word.lower())
    return " ".join(words)


def _eff_date(sentence: str) -> tuple[str | None, int | None]:
    match = re.search(
        r"\b(?:effective|starting)\s+([A-Za-z]+)\s+(\d{1,2})(?:,\s*(\d{4}))?"
        r"|\bOn\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
        sentence,
        re.I,
    )
    if match is None:
        return None, None
    if match.group(1):
        month_word, day_text, year_text = match.group(1), match.group(2), match.group(3)
    else:
        month_word, day_text, year_text = match.group(4), match.group(5), match.group(6)
    month = _FULL_MONTHS.get(month_word.lower())
    if month is None:
        return None, None
    year = int(year_text) if year_text else None
    return f"{month} {int(day_text)}", year


def _impossible_calendar_day(sentence: str) -> bool:
    for match in re.finditer(
        r"\b(?:effective|starting|on)\s+([A-Za-z]+)\s+(\d{1,2})\b",
        sentence,
        re.I,
    ):
        month_name = _FULL_MONTHS.get(match.group(1).lower())
        if month_name is None:
            continue
        month = _MONTHS.index(month_name) + 1
        day = int(match.group(2))
        if month == 2 and day > 29:
            return True
        if month in {4, 6, 9, 11} and day > 30:
            return True
        if day < 1 or day > 31:
            return True
    return False


def _guidance_sentence(sentence: str) -> bool:
    """True when the sentence states an outlook, not a promise to give one later."""
    if re.search(r"\bdividend\b", sentence, re.I) and not re.search(r"\b(?:outlook|guidance)\b", sentence, re.I):
        return False
    if _GUIDANCE_LATER.search(sentence):
        return False
    if re.search(r"\b(?:outlook|guidance)\b", sentence, re.I) and re.search(
        r"\b(?:raise[ds]?|raising|lower(?:ed|s)?|lowering|confirm(?:ed|s)?|reaffirm(?:ed|s)?|affirm(?:ed|s)?)\b",
        sentence,
        re.I,
    ):
        return True
    if re.search(r"\b(?:outlook|guidance)\s+for\b", sentence, re.I):
        return True
    if re.search(r"\b(?:outlook|guidance)\b", sentence, re.I) and re.search(
        r"\bexpect(?:s|ed)?\s+to\s+be\b|\brevenue\s+is\s+expected\b",
        sentence,
        re.I,
    ):
        return True
    if re.search(r"\bexpects?\b", sentence, re.I) and re.search(
        r"\b(?:next quarter|next year|coming year|fiscal\s+\d{4}|full year|the coming)\b",
        sentence,
        re.I,
    ):
        return True
    return False


def _outlook_is_restated(docs: list[dict]) -> bool:
    """True when the filing only repeats an earlier outlook."""
    return any(_RESTATED_OUTLOOK.search(sentence) for sentence in _sentences(_combined(docs)))


def _guidance_figure(sentences: list[str]) -> tuple[str | None, str | None]:
    """One verbatim amount or range, with its scale word. Unclear means no figure."""
    found: list[tuple[str, str]] = []
    labels = (
        (r"diluted earnings per share|earnings per share", "earnings per share"),
        (r"net income", "net income"),
        (r"revenue|net sales", "revenue"),
    )
    for sentence in sentences:
        for match in _GUIDANCE_FIGURE.finditer(sentence):
            figure = re.sub(r"\s+", " ", match.group(1)).strip()
            window = sentence[max(0, match.start() - 80) : match.start()]
            measure = None
            for pattern, name in labels:
                if re.search(rf"\b(?:{pattern})\b", window, re.I):
                    measure = name
                    break
            if measure:
                found.append((measure, figure))
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return None, None


def _guidance(_items: list[str], docs: list[dict]) -> dict | None:
    """Outlook text confirms guidance on any item list, including a 2.02 earnings release."""
    if _outlook_is_restated(docs):
        return None
    sentences = [sentence for sentence in _sentences(_combined(docs)) if _guidance_sentence(sentence)]
    if not sentences:
        return None
    direction = _guide_direction(sentences)
    period = _period_label(sentences, direction)
    exhibit = next((doc for doc in docs if doc.get("exhibit") == "99.1"), None)
    measure = figure = exhibit_url = None
    if exhibit is not None:
        measure, figure = _guidance_figure(_sentences(exhibit.get("text") or ""))
        if measure and figure:
            exhibit_url = exhibit.get("url")
        else:
            measure = figure = None
    result = _blank(outcome="confirmed")
    result.update(
        {
            "h3_category": "guidance",
            "verified": True,
            "guide_direction": direction,
            "period_label": period,
            "measure": measure,
            "figure": figure,
            "exhibit_url": exhibit_url,
        }
    )
    return result


def _guide_direction(sentences: list[str]) -> str:
    raised = lowered = confirmed = False
    for sentence in sentences:
        if re.search(r"\b(?:may|might|could|possibly)\b", sentence, re.I):
            continue
        if re.search(r"\b(?:raise[ds]?|raising)\b", sentence, re.I) and re.search(r"\b(?:outlook|guidance)\b", sentence, re.I):
            raised = True
        if re.search(r"\b(?:lower(?:ed|s)?|lowering)\b", sentence, re.I) and re.search(r"\b(?:outlook|guidance)\b", sentence, re.I):
            lowered = True
        if re.search(r"\b(?:confirm(?:ed|s)?|reaffirm(?:ed|s)?|affirm(?:ed|s)?)\b", sentence, re.I) and re.search(
            r"\b(?:outlook|guidance)\b", sentence, re.I
        ):
            confirmed = True
    flags = [raised, lowered, confirmed]
    if sum(flags) != 1:
        return "unclear"
    if raised:
        return "raised"
    if lowered:
        return "lowered"
    return "confirmed"


def _period_label(sentences: list[str], direction: str) -> str | None:
    if direction == "unclear":
        return None
    labels = []
    for sentence in sentences:
        match = re.search(r"\b(?:outlook|guidance)\s+for\s+([^.,;]+)", sentence, re.I)
        if match:
            label = re.sub(r"\s+", " ", match.group(1)).strip()
            if label and len(label) <= 80:
                labels.append(label)
    unique = list(dict.fromkeys(labels))
    if len(unique) == 1:
        return unique[0]
    return None


def _calendar_date(year: int, month: int, day: int):
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def _chosen_year(filing_month: int, filing_year: int, month: int, eff_year: int | None) -> int:
    """Filing year, except a Nov/Dec filing naming Jan/Feb, or a Jan/Feb filing naming Nov/Dec."""
    if eff_year is not None:
        return eff_year
    if filing_month in {11, 12} and month in {1, 2}:
        return filing_year + 1
    if filing_month in {1, 2} and month in {11, 12}:
        return filing_year - 1
    return filing_year


def _placed_effective(eff_date: str | None, eff_year: int | None, filing_iso: str | None):
    """Return the calendar date, or 'impossible' when that day does not exist in the chosen year."""
    if not eff_date or not filing_iso:
        return None
    parts = eff_date.split(" ")
    if len(parts) != 2 or parts[0] not in _MONTHS:
        return None
    filing = datetime.fromisoformat(filing_iso).date()
    month = _MONTHS.index(parts[0]) + 1
    day = int(parts[1])
    year = _chosen_year(filing.month, filing.year, month, eff_year)
    placed = _calendar_date(year, month, day)
    if placed is None:
        return "impossible"
    return placed


def _impossible_effective(person: dict, filing_iso: str | None) -> bool:
    return _placed_effective(person.get("eff_date"), person.get("eff_year"), filing_iso) == "impossible"


def _eff_on_or_before(eff_date: str | None, eff_year: int | None, filing_iso: str | None) -> bool:
    placed = _placed_effective(eff_date, eff_year, filing_iso)
    if placed is None or placed == "impossible" or not filing_iso:
        return False
    return placed <= datetime.fromisoformat(filing_iso).date()


def _earnings_line(name: str, phrase: str, pretty: str, fields: dict) -> str:
    kind = "quarterly results" if fields.get("is_quarter") else "results"
    line = f"{name} shared its {kind} in {phrase} on {pretty}."
    if fields.get("measure") and fields.get("figure") and fields.get("exhibit_url"):
        line += f" The company reported {fields['measure']} of {fields['figure']}."
    return line


def _deal_line(name: str, phrase: str, pretty: str, fields: dict) -> str:
    side = fields.get("side")
    stage = fields.get("stage")
    counterparty = fields.get("counterparty")
    asset = fields.get("asset")
    if stage == "agreed" and side == "acquirer" and counterparty:
        return f"{name} agreed to acquire {counterparty}, according to {phrase} on {pretty}."
    if stage == "agreed" and side == "acquired" and counterparty:
        return f"{name} agreed to be acquired by {counterparty}, according to {phrase} on {pretty}."
    if stage == "agreed" and side == "seller" and counterparty and asset:
        return f"{name} agreed to make {counterparty} the new owner of {asset}, according to {phrase} on {pretty}."
    if stage == "completed" and side == "acquirer" and counterparty:
        return f"{name} completed its deal to acquire {counterparty}, according to {phrase} on {pretty}."
    if stage == "completed" and side == "seller" and counterparty and asset:
        return f"{name} completed the handover of {asset} to {counterparty}, according to {phrase} on {pretty}."
    return f"{name} reported a major deal in {phrase} on {pretty}. The filing has the details."


def _leadership_line(name: str, phrase: str, pretty: str, fields: dict, filing_iso: str | None = None) -> str | None:
    people = fields.get("leaders_json")
    if isinstance(people, list) and people:
        sentences = []
        blocked = False
        for person in people[:2]:
            if _impossible_effective(person, filing_iso):
                blocked = True
                continue
            sentence = _one_leader_line(name, person, filing_iso)
            if sentence:
                sentences.append(sentence)
        if sentences:
            return " ".join(sentences)
        if blocked:
            return None
    elif _impossible_effective(fields, filing_iso):
        return None
    if fields.get("person") and fields.get("role") and fields.get("lead_direction"):
        sentence = _one_leader_line(name, fields, filing_iso)
        if sentence:
            return sentence
    return f"{name} announced a leadership change in {phrase} on {pretty}."


def _one_leader_line(name: str, person: dict, filing_iso: str | None = None) -> str | None:
    who = person.get("person")
    role = person.get("role")
    direction = person.get("lead_direction")
    if not who or not role or direction not in {"joining", "leaving"}:
        return None
    if _impossible_effective(person, filing_iso):
        return None
    eff = person.get("eff_date")
    past = _eff_on_or_before(eff, person.get("eff_year"), filing_iso)
    if past and eff:
        if "board of directors" in role:
            if direction == "joining":
                return f"{name} announced that {who} joined its board of directors on {eff}."
            return f"{name} announced that {who} left its board of directors on {eff}."
        if direction == "joining":
            return f"{name} announced that {who} became its {role} on {eff}."
        if person.get("resigned_or_retired"):
            return f"{name} announced that {who} stepped down from the role of {role} on {eff}."
        return f"{name} announced that {who} left the role of {role} on {eff}."
    clause = f", starting {eff}" if eff else ""
    if "board of directors" in role:
        if direction == "joining":
            return f"{name} announced that {who} will join its board of directors{clause}."
        return f"{name} announced that {who} will leave its board of directors{clause}."
    if direction == "joining":
        return f"{name} announced that {who} will become its {role}{clause}."
    if person.get("resigned_or_retired"):
        return f"{name} announced that {who}, its {role}, will step down{clause}."
    return f"{name} announced that {who}, its {role}, will leave that role{clause}."


def _guidance_line(name: str, phrase: str, pretty: str, fields: dict) -> str:
    direction = fields.get("guide_direction") or "unclear"
    period = fields.get("period_label")
    for_clause = f" for {period}" if period else ""
    stems = {
        "raised": f"{name} raised its outlook{for_clause}, according to {phrase} on {pretty}.",
        "lowered": f"{name} lowered its outlook{for_clause}, according to {phrase} on {pretty}.",
        "confirmed": f"{name} confirmed its earlier outlook{for_clause}, according to {phrase} on {pretty}.",
        "unclear": f"{name} updated its outlook{for_clause}, according to {phrase} on {pretty}.",
    }
    line = stems.get(direction, stems["unclear"])
    if fields.get("measure") and fields.get("figure") and fields.get("exhibit_url"):
        line += f" The company now expects {fields['measure']} of {fields['figure']}."
    return line


def _parse_accepted(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
