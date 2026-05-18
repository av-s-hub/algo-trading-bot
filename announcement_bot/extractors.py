import io
import re
from typing import Optional, Tuple

import requests

from announcement_bot.config import BSE_HEADERS, NSE_HEADERS
from announcement_bot.utils import clean_text

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
    re.compile(r"(?i)\bto\s+([A-Z][A-Za-z0-9&.,()\/\- ]{2,80})"),
]

TRAILING_CLIENT_NOISE = re.compile(
    r"(?i)\s+(?:for|worth|valued at|value of|amounting to|for an amount of|under)\b.*$"
)

HARD_REJECT_PHRASES = (
    "board meeting",
    "newspaper advertisement",
    "compliance",
    "clarification",
    "investor presentation",
    "shareholding pattern",
    "trading window",
    "disclosure under regulation",
    "loss of share certificate",
    "analyst meeting",
    "transcript",
    "outcome of meeting",
    "agm notice",
    "egm notice",
    "appointment of scrutinizer",
    "appointment of scrutinizers",
    "procedural filing",
    "generic update",
    "regulation 30",
)

ORDER_WIN_KEYWORDS = (
    "order", "contract", "loa", "letter of award", "work order", "purchase order", "letter of intent"
)
GOVERNMENT_CONTRACT_KEYWORDS = (
    "government order",
    "government contract",
    "psu",
    "railway",
    "defence",
    "ministry",
    "power authority",
    "public sector",
    "govt",
    "government agency",
    "municipality",
    "state government",
    "central government",
    "public sector undertaking",
    "central public sector enterprise",
)
CAPEX_KEYWORDS = ("expansion", "capex", "plant", "facility", "capacity", "commissioning", "project", "greenfield", "brownfield")
ACQUISITION_KEYWORDS = (
    "acquisition",
    "acquire",
    "merger",
    "merge",
    "stake sale",
    "buyout",
    "takeover",
    "purchase of shares",
)
FUNDRAISING_KEYWORDS = (
    "fundraise",
    "fundraising",
    "rights issue",
    "preferential allotment",
    "private placement",
    "ipo",
    "follow on",
    "convertible",
    "debt raising",
    "loan agreement",
    "term loan",
    "borrowing",
)
MANAGEMENT_CHANGE_KEYWORDS = (
    "resignation",
    "appointment",
    "ceo",
    "cfo",
    "md",
    "director",
    "chairman",
    "managing director",
    "key managerial person",
    "kmp",
    "succession",
)
REGULATORY_APPROVAL_KEYWORDS = (
    "approval",
    "licence",
    "license",
    "permit",
    "clearance",
    "regulatory approval",
    "environment clearance",
    "eia",
    "certificate",
    "authorization",
    "sanctioned",
    "nodal agency",
)
NEGATIVE_KEYWORDS = (
    "default",
    "penalty",
    "bankruptcy",
    "insolvency",
    "liquidation",
    "debt restructuring",
    "delisting",
    "lawsuit",
    "investigation",
    "fine",
    "notice",
    "adverse",
    "negative",
    "termination",
    "breach",
)
STRATEGIC_PARTNERSHIP_KEYWORDS = (
    "partnership",
    "joint venture",
    "strategic alliance",
    "collaboration",
    "moa",
    "memorandum of understanding",
    "mou",
    "tie-up",
    "strategic partner",
)
GENERAL_KEYWORDS = ("update", "disclosure", "notice", "announcement")

IMPORTANT_EVENTS = {
    "ORDER_WIN",
    "GOVERNMENT_CONTRACT",
    "CAPEX",
    "ACQUISITION",
    "FUNDRAISING",
    "MANAGEMENT_CHANGE",
    "REGULATORY_APPROVAL",
    "NEGATIVE_EVENT",
    "STRATEGIC_PARTNERSHIP",
}

GOVERNMENT_CLIENT_KEYWORDS = (
    "ministry",
    "railway",
    "defence",
    "power authority",
    "psu",
    "public sector",
    "govt",
    "government",
    "municipality",
    "central government",
    "state government",
    "public sector undertaking",
    "public sector enterprise",
    "bank of india",
    "state bank",
    "railways",
)
LARGE_CLIENT_KEYWORDS = (
    "limited",
    "ltd",
    "private limited",
    "corporation",
    "holding",
    "group",
    "financial services",
    "bank",
    "industrial",
)

UNIT_SCALE = {
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "lakh": 1e5,
    "lakhs": 1e5,
    "million": 1e6,
    "mn": 1e6,
    "billion": 1e9,
    "bn": 1e9,
}

AMOUNT_CONTEXT_KEYWORDS = (
    "order",
    "contract",
    "award",
    "worth",
    "value",
    "amount",
    "consideration",
    "capex",
    "investment",
    "bid",
)

STRONG_MANAGEMENT_KEYWORDS = (
    "ceo",
    "cfo",
    "md",
    "chairman",
    "managing director",
    "chief executive",
)


def _normalize_keywords(text: str) -> str:
    return clean_text(text, default="").lower()


def is_hard_reject(text: str) -> bool:
    normalized = _normalize_keywords(text)
    return any(phrase in normalized for phrase in HARD_REJECT_PHRASES)


def classify_event(text: str) -> str:
    normalized = _normalize_keywords(text)

    if any(keyword in normalized for keyword in GOVERNMENT_CONTRACT_KEYWORDS):
        return "GOVERNMENT_CONTRACT"
    if any(keyword in normalized for keyword in ACQUISITION_KEYWORDS):
        return "ACQUISITION"
    if any(keyword in normalized for keyword in FUNDRAISING_KEYWORDS):
        return "FUNDRAISING"
    if any(keyword in normalized for keyword in REGULATORY_APPROVAL_KEYWORDS):
        return "REGULATORY_APPROVAL"
    if any(keyword in normalized for keyword in STRATEGIC_PARTNERSHIP_KEYWORDS):
        return "STRATEGIC_PARTNERSHIP"
    if any(keyword in normalized for keyword in CAPEX_KEYWORDS):
        return "CAPEX"
    if any(keyword in normalized for keyword in ORDER_WIN_KEYWORDS):
        return "ORDER_WIN"
    if any(keyword in normalized for keyword in NEGATIVE_KEYWORDS):
        return "NEGATIVE_EVENT"
    if any(keyword in normalized for keyword in MANAGEMENT_CHANGE_KEYWORDS):
        return "MANAGEMENT_CHANGE"
    return "GENERAL"


def classify_signal(text, event_type=None):
    event_type = event_type or classify_event(text)
    if event_type == "NEGATIVE_EVENT":
        return "BEARISH"
    if event_type in {
        "ORDER_WIN",
        "GOVERNMENT_CONTRACT",
        "CAPEX",
        "ACQUISITION",
        "FUNDRAISING",
        "STRATEGIC_PARTNERSHIP",
    }:
        return "BULLISH"
    return "NEUTRAL"


def parse_amount_value(amount_text: str) -> Optional[Tuple[float, str]]:
    amount_text = amount_text.lower().replace("₹", " rs ").replace("inr", " rs ")
    amount_text = amount_text.replace(",", "").strip()
    match = re.search(r"(?P<number>\d+(?:\.\d+)?)", amount_text)
    if not match:
        return None

    value = float(match.group("number"))
    unit = ""
    for token, scale in UNIT_SCALE.items():
        if token in amount_text:
            unit = token
            value *= scale
            break

    if not unit and " rs" in amount_text:
        return value

    return value, unit


def _is_material_amount(amount_text: str) -> bool:
    parsed = parse_amount_value(amount_text)
    if not parsed:
        return False

    value, unit = parsed
    if unit in {"crore", "crores", "cr", "million", "mn", "billion", "bn"}:
        return value >= 1.0 or value >= 1e6
    if unit == "rs":
        return value >= 1e7
    return False


def extract_amount(text: str) -> str:
    normalized = clean_text(text, default="")
    if not normalized:
        return "Not Mentioned"

    candidates = []
    for match in AMOUNT_PATTERN.finditer(normalized):
        snippet = " ".join(match.group(0).split())
        parsed = parse_amount_value(snippet)
        if not parsed:
            continue

        value, unit = parsed
        if unit not in UNIT_SCALE and unit != "rs":
            continue

        score = 0
        if _is_material_amount(snippet):
            score += 5
        if any(token in snippet.lower() for token in ("₹", "rs", "inr")):
            score += 3
        if any(keyword in normalized[max(0, match.start() - 50): match.end() + 50].lower() for keyword in AMOUNT_CONTEXT_KEYWORDS):
            score += 2

        candidates.append((score, value, snippet))

    if not candidates:
        return "Not Mentioned"

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    amount_text = candidates[0][2]
    return amount_text if _is_material_amount(amount_text) else "Not Mentioned"


def is_government_client(client: str, text: str = "") -> bool:
    normalized = clean_text(client, default="").lower()
    text_lower = clean_text(text, default="").lower()
    if any(keyword in normalized for keyword in GOVERNMENT_CLIENT_KEYWORDS):
        return True
    return any(keyword in text_lower for keyword in GOVERNMENT_CLIENT_KEYWORDS)


def _is_large_client(client: str) -> bool:
    normalized = clean_text(client, default="").lower()
    return any(keyword in normalized for keyword in LARGE_CLIENT_KEYWORDS)


def extract_client(text: str) -> str:
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

    snippet = normalized
    for keyword in GOVERNMENT_CLIENT_KEYWORDS + LARGE_CLIENT_KEYWORDS:
        if keyword in snippet:
            start = snippet.find(keyword)
            return clean_text(snippet[start : start + 80], default="Unknown")

    return "Unknown"


def assess_materiality(
    event_type: str,
    amount_text: str,
    client: str,
    headline: str,
) -> Tuple[str, bool, int, str]:
    normalized = _normalize_keywords(headline)
    amount_value = 0.0
    parsed = parse_amount_value(amount_text) if amount_text != "Not Mentioned" else None
    if parsed:
        amount_value, _ = parsed

    government_client = is_government_client(client, headline)
    strong_client = government_client or _is_large_client(client)

    score = 0
    reasons = []

    if event_type == "GOVERNMENT_CONTRACT":
        score += 8
        reasons.append("government contract")
    elif event_type == "ORDER_WIN":
        score += 6
        reasons.append("large order win")
    elif event_type == "CAPEX":
        score += 7
        reasons.append("capital expenditure")
    elif event_type == "ACQUISITION":
        score += 8
        reasons.append("strategic acquisition")
    elif event_type == "FUNDRAISING":
        score += 6
        reasons.append("fundraising")
    elif event_type == "REGULATORY_APPROVAL":
        score += 6
        reasons.append("regulatory approval")
    elif event_type == "NEGATIVE_EVENT":
        score += 8
        reasons.append("negative risk")
    elif event_type == "STRATEGIC_PARTNERSHIP":
        score += 6
        reasons.append("strategic partnership")
    elif event_type == "MANAGEMENT_CHANGE":
        if any(keyword in normalized for keyword in STRONG_MANAGEMENT_KEYWORDS):
            score += 6
            reasons.append("senior management change")
        else:
            score += 3
            reasons.append("management update")
    else:
        score += 1
        reasons.append("general announcement")

    if amount_text != "Not Mentioned":
        if amount_value >= 1e9:
            score += 5
            reasons.append("very large amount")
        elif amount_value >= 1e8:
            score += 4
            reasons.append("large amount")
        elif amount_value >= 1e7:
            score += 3
            reasons.append("material amount")
        else:
            score -= 2
            reasons.append("amount below material threshold")
    else:
        if event_type in {"ORDER_WIN", "GOVERNMENT_CONTRACT", "CAPEX", "ACQUISITION", "FUNDRAISING"}:
            score -= 1

    if government_client:
        score += 3
        reasons.append("government or PSU client")
    elif strong_client:
        score += 2
        reasons.append("large corporate client")

    if event_type == "GENERAL" and amount_text == "Not Mentioned":
        score -= 2

    if any(keyword in normalized for keyword in GENERAL_KEYWORDS):
        score -= 1

    if amount_text == "Not Mentioned" and event_type == "NEGATIVE_EVENT":
        score += 1

    if score >= 11:
        confidence = "HIGH"
    elif score >= 7:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    strong_confidence = confidence == "HIGH" or (
        confidence == "MEDIUM" and (government_client or amount_value >= 1e8 or event_type in {"ACQUISITION", "GOVERNMENT_CONTRACT", "CAPEX"})
    )

    reason = " ".join(reasons)
    if not reason:
        reason = "material business event"

    return confidence, strong_confidence, score, reason


def _read_pdf_with_pdfplumber(pdf_bytes):
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = []
        for page in pdf.pages[:5]:
            text = page.extract_text() or ""
            if text:
                pages.append(text)
        return "\n".join(pages)


def _read_pdf_with_pypdf2(pdf_bytes):
    try:
        from PyPDF2 import PdfReader
    except ImportError:  # pragma: no cover
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
