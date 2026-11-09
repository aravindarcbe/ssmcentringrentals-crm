"""Best-effort text extraction for vendor purchase bills (PDF), used to
pre-fill the Purchase Bill form so staff can review/correct it instead of
typing every line from scratch.

No AI/OCR — plain text extraction only (see docs/change-requests-2026-11.md
§2 for why). A scanned/photographed PDF with no real text layer, or a bill
laid out as a complex multi-column table, will come back with a short or
empty item list; the caller always shows the result in an editable popup
before anything is saved, so a partial or wrong guess here is expected and
corrected by the person doing the import, not treated as a hard failure.
"""
import re
from datetime import datetime

from pypdf import PdfReader


_DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), "%d/%m/%Y"),
    (re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b"), "%Y/%m/%d"),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b"), "%d/%m/%y"),
]

# description, then count, an optional "x"/"@", rate, then amount
_THREE_NUMBER_RE = re.compile(
    r"^(?P<description>.+?)\s+"
    r"(?P<count>\d+(?:\.\d+)?)\s+"
    r"(?:x|@)?\s*"
    r"(?P<rate>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<amount>[\d,]+(?:\.\d+)?)\s*$"
)

# fallback: description then just a trailing amount
_TWO_NUMBER_RE = re.compile(r"^(?P<description>.+?)\s+(?P<amount>[\d,]+(?:\.\d+)?)\s*$")

_SKIP_WORDS = ("subtotal", "total", "grand total", "gst", "tax", "invoice no", "bill no", "page ")


def _clean_number(value):
    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _find_date(text):
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        normalized = m.group(0).replace("-", "/")
        try:
            dt = datetime.strptime(normalized, fmt.replace("-", "/"))
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def _parse_line_items(text):
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 4:
            continue
        if sum(c.isalpha() for c in line) < 3:
            continue
        if any(skip in line.lower() for skip in _SKIP_WORDS):
            continue

        m = _THREE_NUMBER_RE.match(line)
        if m:
            count = _clean_number(m.group("count"))
            rate = _clean_number(m.group("rate"))
            amount = _clean_number(m.group("amount"))
            if count and amount:
                items.append({
                    "description": m.group("description").strip(" .:-"),
                    "count": count,
                    "rate": rate if rate is not None else round(amount / count, 2),
                    "amount": amount,
                })
                continue

        m = _TWO_NUMBER_RE.match(line)
        if m:
            amount = _clean_number(m.group("amount"))
            description = m.group("description").strip(" .:-")
            if amount and len(description) >= 3:
                items.append({"description": description, "count": 1, "rate": amount, "amount": amount})

    return items


def parse_purchase_pdf(file_obj):
    """Returns {"date": "YYYY-MM-DD" | None, "items": [{"description", "count", "rate", "amount"}, ...]}."""
    reader = PdfReader(file_obj)
    # "layout" mode preserves column spacing (critical for a tabular bill) far
    # better than the default extraction, which often runs adjacent table
    # cells together with no space between them.
    full_text = "\n".join((page.extract_text(extraction_mode="layout") or "") for page in reader.pages)
    return {"date": _find_date(full_text), "items": _parse_line_items(full_text)}
