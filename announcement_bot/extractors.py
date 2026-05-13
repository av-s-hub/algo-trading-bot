import io
import re

import requests

from announcement_bot.config import BSE_HEADERS, LOW_VALUE_FILINGS, NSE_HEADERS
from announcement_bot.utils import clean_text

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


AMOUNT_PATTERN = re.compile(
    r"(?i)("
    r"(?:\u20B9|rs\.?|inr)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crore|crores|lakh|lakhs|million|billion|cr|mn|bn))?"
    r"|"
    r"\d[\d,]*(?:\.\d+)?\s*(?:crore|crores|lakh|lakhs|million|billion|cr|mn|bn)"
    r")"
)

CLIENT_PATTERNS = [
    re.compile(r"(?i)\bfrom\s+([A-Z][A-Za-z0-9&.,()\/\- ]{2,80})"),
    re.compile(r"(?i)\bawarded by\s+([A-Z][A-Za-z0-9&.,()\/\- ]{2,80})"),
    re.compile(r"(?i)\breceived from\s+([A-Z][A-Za-z0-9&.,()\/\- ]{2,80})"),
]

TRAILING_CLIENT_NOISE = re.compile(
    r"(?i)\s+(?:for|worth|valued at|value of|amounting to|for an amount of|under)\b.*$"
)

ORDER_WIN_KEYWORDS = ("order", "contract", "loa", "letter of award", "work order")
MA_KEYWORDS = ("acquisition", "acquire", "merger", "merge")
EXPANSION_KEYWORDS = ("expansion", "capex")
NEGATIVE_KEYWORDS = ("default", "penalty", "resignation")
IMPORTANT_EVENTS = {"Order Win", "M&A", "Expansion", "Negative"}


def is_low_value_filing(text):
    normalized = clean_text(text, default="").lower()
    return any(keyword in normalized for keyword in LOW_VALUE_FILINGS)


def classify_event(text):
    normalized = clean_text(text, default="").lower()

    if any(keyword in normalized for keyword in ORDER_WIN_KEYWORDS):
        return "Order Win"
    if any(keyword in normalized for keyword in MA_KEYWORDS):
        return "M&A"
    if any(keyword in normalized for keyword in EXPANSION_KEYWORDS):
        return "Expansion"
    if any(keyword in normalized for keyword in NEGATIVE_KEYWORDS):
        return "Negative"
    return "General"


def classify_signal(text, event_type=None):
    normalized = clean_text(text, default="").lower()
    event_type = event_type or classify_event(normalized)

    if event_type == "Negative":
        return "BEARISH"
    if event_type in {"Order Win", "M&A", "Expansion"}:
        return "BULLISH"
    return "NEUTRAL"


def extract_amount(text):
    normalized = clean_text(text, default="")
    if not normalized:
        return "Not Mentioned"

    candidates = []
    for match in AMOUNT_PATTERN.finditer(normalized):
        snippet = " ".join(match.group(0).split())
        lower_snippet = snippet.lower()
        context = normalized[max(0, match.start() - 50): match.end() + 50].lower()
        score = 0

        if any(token in lower_snippet for token in ("\u20b9", "rs", "inr")):
            score += 5
        if any(
            unit in lower_snippet
            for unit in ("crore", "crores", "lakh", "lakhs", "million", "billion", "cr", "mn", "bn")
        ):
            score += 4
        if any(
            keyword in context
            for keyword in ("order", "contract", "award", "worth", "value", "amount", "consideration", "capex")
        ):
            score += 3

        candidates.append((score, snippet))

    if not candidates:
        return "Not Mentioned"

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def extract_client(text):
    normalized = clean_text(text, default="")
    if not normalized:
        return "Unknown"

    for pattern in CLIENT_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue

        client = TRAILING_CLIENT_NOISE.sub("", match.group(1)).strip(" ,.;:-")
        if client:
            return client

    return "Unknown"


def _read_pdf_with_pdfplumber(pdf_bytes):
    if pdfplumber is None:
        return ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = []
        for page in pdf.pages[:5]:
            text = page.extract_text() or ""
            if text:
                pages.append(text)
        return "\n".join(pages)


def _read_pdf_with_pypdf2(pdf_bytes):
    if PdfReader is None:
        return ""

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages[:5]:
        text = page.extract_text() or ""
        if text:
            pages.append(text)
    return "\n".join(pages)


def parse_pdf_if_needed(headline, link, event_type, amount, session=None):
    normalized_headline = clean_text(headline, default="")
    needs_pdf = (
        amount == "Not Mentioned"
        or len(normalized_headline.split()) < 6
        or event_type in IMPORTANT_EVENTS
    )
    if not needs_pdf or not link or ".pdf" not in link.lower():
        return ""

    session = session or requests.Session()
    headers = BSE_HEADERS if "bseindia" in link.lower() else NSE_HEADERS
    try:
        response = session.get(link, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    pdf_bytes = response.content

    text = _read_pdf_with_pdfplumber(pdf_bytes)
    if text:
        return clean_text(text, default="")

    text = _read_pdf_with_pypdf2(pdf_bytes)
    return clean_text(text, default="")
