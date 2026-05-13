import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


BSE_ANNOUNCEMENTS_PAGE_URL = "https://www.bseindia.com/corporates/ann.html?anntype=C"
BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
NSE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements"
SEEN_FILE = os.getenv("SEEN_FILE", "seen.txt")
BOT_ENABLED = env_bool("BOT_ENABLED", True)
SEND_STARTUP_MESSAGE = env_bool("SEND_STARTUP_MESSAGE", True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": BSE_ANNOUNCEMENTS_PAGE_URL,
    "Accept": "application/json",
}

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

BSE_PARAMS = {
    "pageno": 1,
    "strCat": "-1",
    "strPrevDate": "",
    "strScrip": "",
    "strSearch": "P",
    "strToDate": "",
    "strType": "C",
    "subcategory": "-1",
}

IGNORE_WORDS = {
    "disclosure",
    "regulation",
    "meeting",
    "results",
    "presentation",
    "shareholding",
    "board",
}

KEYWORDS = {
    "order",
    "contract",
    "awarded",
    "bagged",
    "work order",
    "project",
    "secured",
}

MONEY_PATTERN = re.compile(
    r"(?i)("
    r"(?:₹|rs\.?|inr)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:crore|crores|lakh|lakhs|million|billion|cr|mn|bn))?"
    r"|"
    r"\d[\d,]*(?:\.\d+)?\s*(?:crore|crores|lakh|lakhs|million|billion|cr|mn|bn)"
    r")"
)


def env_int(name, default):
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        print(
            f"Invalid integer for {name}: {value!r}. Using default {default}.",
            file=sys.stderr,
            flush=True,
        )
        return default


POLL_SECONDS = env_int("POLL_SECONDS", 15)
MAX_SEEN_HEADLINES = env_int("MAX_SEEN_HEADLINES", 10000)


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        lines = []

    if len(lines) > MAX_SEEN_HEADLINES:
        lines = lines[-MAX_SEEN_HEADLINES:]
        rewrite_seen(lines)

    return deque(lines, maxlen=MAX_SEEN_HEADLINES), set(lines)


def rewrite_seen(lines):
    with open(SEEN_FILE, "w", encoding="utf-8") as file:
        if lines:
            file.write("\n".join(lines) + "\n")


def remember_seen(headline, seen_queue, seen_lookup):
    if headline in seen_lookup:
        return

    if len(seen_queue) == seen_queue.maxlen:
        evicted = seen_queue.popleft()
        seen_lookup.discard(evicted)
        seen_queue.append(headline)
        seen_lookup.add(headline)
        rewrite_seen(list(seen_queue))
        return

    seen_queue.append(headline)
    seen_lookup.add(headline)
    with open(SEEN_FILE, "a", encoding="utf-8") as file:
        file.write(headline + "\n")


def check_signal(text):
    normalized = text.lower()

    if any(word in normalized for word in IGNORE_WORDS):
        return False

    return any(word in normalized for word in KEYWORDS)


def clean_text(value, default="Unknown"):
    text = BeautifulSoup(value or "", "html.parser").get_text(" ").strip()
    return " ".join(text.split()) or default


def extract_amount(text):
    normalized = clean_text(text, default="")
    if not normalized:
        return "Not mentioned"

    candidates = []
    for match in MONEY_PATTERN.finditer(normalized):
        snippet = " ".join(match.group(0).split())
        lower_snippet = snippet.lower()
        context = normalized[max(0, match.start() - 40): match.end() + 40].lower()
        score = 0

        if any(token in lower_snippet for token in ("₹", "rs", "inr")):
            score += 5
        if any(
            unit in lower_snippet
            for unit in ("crore", "crores", "lakh", "lakhs", "million", "billion", "cr", "mn", "bn")
        ):
            score += 4
        if any(
            keyword in context
            for keyword in (
                "order",
                "contract",
                "award",
                "worth",
                "value",
                "amount",
                "consideration",
                "project",
                "fund",
                "issue",
            )
        ):
            score += 3

        numeric_part = re.sub(r"(?i)[^0-9.]", "", snippet) or "0"
        try:
            score += min(float(numeric_part) / 1000, 2)
        except ValueError:
            pass

        candidates.append((score, snippet))

    if not candidates:
        return "Not mentioned"

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def classify_event(text):
    normalized = clean_text(text, default="").lower()

    if any(keyword in normalized for keyword in ("order", "contract", "award", "awarded", "bagged", "work order")):
        return "Order Win"
    if any(keyword in normalized for keyword in ("acquisition", "acquire", "merge", "merger", "amalgamation")):
        return "M&A"
    if any(keyword in normalized for keyword in ("penalty", "default", "fine", "insolvency", "fraud")):
        return "Negative"
    if any(
        keyword in normalized
        for keyword in (
            "fund raising",
            "fundraise",
            "rights issue",
            "qip",
            "preferential issue",
            "qualified institutions placement",
            "warrant issue",
            "issue of securities",
        )
    ):
        return "Fund Raising"
    return "General"


def classify_signal(text):
    normalized = clean_text(text, default="").lower()

    if any(keyword in normalized for keyword in ("penalty", "default", "fine", "insolvency", "fraud", "loss", "downgrade")):
        return "BEARISH"
    if any(
        keyword in normalized
        for keyword in ("order", "contract", "award", "awarded", "bagged", "expansion", "capacity", "commissioned")
    ):
        return "BULLISH"
    return "NEUTRAL"


def build_bse_attachment_url(item):
    attachment_name = item.get("ATTACHMENTNAME") or item.get("ATTACHMENT") or item.get("NSURL")
    if attachment_name:
        return urljoin(BSE_ATTACHMENT_BASE_URL, str(attachment_name).lstrip("/"))
    return BSE_ANNOUNCEMENTS_PAGE_URL


def extract_announcement_link(item):
    exchange = item.get("EXCHANGE", "BSE")
    if exchange == "BSE":
        return build_bse_attachment_url(item)
    return item.get("URL", NSE_URL)


def format_telegram_message(exchange, company, event_type, amount, signal, link):
    safe_exchange = escape(exchange or "Unknown")
    safe_company = escape(company or "Unknown company")
    safe_event_type = escape(event_type)
    safe_amount = escape(amount)
    safe_signal = escape(signal)
    safe_link = escape(link, quote=True)
    return (
        "🔥 <b>SIGNAL FOUND</b>\n\n"
        f"🏦 Exchange: <b>{safe_exchange}</b>\n"
        f"🏢 Company: <b>{safe_company}</b>\n"
        f"📊 Event: <b>{safe_event_type}</b>\n"
        f"💰 Amount: <b>{safe_amount}</b>\n"
        f"📈 Signal: <b>{safe_signal}</b>\n\n"
        "🔗 Announcement Link:\n"
        f'<a href="{safe_link}">Open Filing</a>'
    )


def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variable."
        )

    response = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        params={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(
            f"Telegram API error {response.status_code}: {response.text}"
        )


def describe_config():
    token_status = "set" if TELEGRAM_TOKEN else "missing"
    chat_status = "set" if TELEGRAM_CHAT_ID else "missing"
    print(
        "Config: "
        f"BOT_ENABLED={BOT_ENABLED}, "
        f"TELEGRAM_BOT_TOKEN={token_status}, "
        f"TELEGRAM_CHAT_ID={chat_status}, "
        f"POLL_SECONDS={POLL_SECONDS}, "
        f"SEND_STARTUP_MESSAGE={SEND_STARTUP_MESSAGE}",
        flush=True,
    )


def fetch_announcements():
    session = requests.Session()
    session.get(BSE_ANNOUNCEMENTS_PAGE_URL, headers=BSE_HEADERS, timeout=20)
    response = session.get(
        BSE_API_URL,
        headers=BSE_HEADERS,
        params=BSE_PARAMS,
        timeout=20,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type:
        raise RuntimeError(
            "BSE announcements API returned a non-JSON response. "
            f"Expected JSON from {BSE_API_URL}, got {content_type or 'unknown content type'}."
        )

    data = response.json()
    return data.get("Table", [])


def parse_nse_announcements(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        values = [clean_text(cell.get_text(" "), default="") for cell in cells]
        if len(values) < 3:
            continue

        if values[0].lower() == "symbol" and "subject" in values[1].lower():
            continue

        link = ""
        anchor = row.find("a", href=True)
        if anchor:
            link = urljoin("https://www.nseindia.com", anchor["href"])

        rows.append(
            {
                "EXCHANGE": "NSE",
                "SLONGNAME": values[0],
                "HEADLINE": values[1],
                "BROADCASTDATE": values[2],
                "URL": link or NSE_URL,
            }
        )

    if rows:
        return rows

    text = soup.get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    try:
        start_index = lines.index("Latest Announcements")
    except ValueError:
        return []

    rows = []
    saw_header = False
    index = start_index + 1

    while index < len(lines):
        line = lines[index]

        if line in {
            "Corporate Actions",
            "Board Meetings",
            "Financial Results",
            "Shareholding Patterns",
            "Note :",
        }:
            break

        if line == "Symbol Subject Broadcast Date":
            saw_header = True
            index += 1
            continue

        if not saw_header:
            index += 1
            continue

        if index + 2 >= len(lines):
            break

        symbol = lines[index]
        subject = lines[index + 1]
        broadcast_date = lines[index + 2]

        if broadcast_date.count("-") < 2:
            index += 1
            continue

        rows.append(
            {
                "EXCHANGE": "NSE",
                "SLONGNAME": symbol,
                "HEADLINE": subject,
                "BROADCASTDATE": broadcast_date,
                "URL": NSE_URL,
            }
        )
        index += 3

    return rows


def fetch_nse_announcements():
    session = requests.Session()
    session.get("https://www.nseindia.com/", headers=NSE_HEADERS, timeout=20)
    response = session.get(NSE_URL, headers=NSE_HEADERS, timeout=20)
    response.raise_for_status()
    return parse_nse_announcements(response.text)


def run():
    describe_config()

    if not BOT_ENABLED:
        print(
            "BOT_ENABLED=false, so the alert worker is exiting cleanly.",
            flush=True,
        )
        sys.exit(0)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. "
            "Set them in Railway Variables.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    seen_queue, seen_lookup = load_seen()
    print(
        f"Running live alert system. Loaded {len(seen_lookup)} seen headlines.",
        flush=True,
    )

    if SEND_STARTUP_MESSAGE:
        try:
            started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            send_telegram_message(f"Scheduled alert run started at {started_at}.")
            print("Startup Telegram message sent.", flush=True)
        except Exception as error:
            print(
                f"Startup Telegram message failed: {error}",
                file=sys.stderr,
                flush=True,
            )

    try:
        announcements = []

        for fetcher in (fetch_announcements, fetch_nse_announcements):
            announcements.extend(fetcher())

        new_count = 0
        signal_count = 0

        for item in announcements:
            exchange = item.get("EXCHANGE", "BSE")
            raw_text = item.get("HEADLINE", "")
            company = clean_text(item.get("SLONGNAME"), default="Unknown company")
            headline = clean_text(raw_text, default="")
            source_url = extract_announcement_link(item)
            seen_key = f"{exchange}|{company}|{headline}"

            if not headline or seen_key in seen_lookup:
                continue

            if not check_signal(headline):
                remember_seen(seen_key, seen_queue, seen_lookup)
                new_count += 1
                continue

            event_type = classify_event(headline)
            signal = classify_signal(headline)
            amount = extract_amount(headline)
            message = format_telegram_message(
                exchange=exchange,
                company=company,
                event_type=event_type,
                amount=amount,
                signal=signal,
                link=source_url,
            )

            print(message, flush=True)
            send_telegram_message(message)
            remember_seen(seen_key, seen_queue, seen_lookup)
            new_count += 1
            signal_count += 1

        print(
            "Run complete: "
            f"{len(announcements)} announcements, "
            f"{new_count} new, "
            f"{signal_count} signals.",
            flush=True,
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
