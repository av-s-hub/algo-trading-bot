import os
import sys


def env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


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


BSE_ANNOUNCEMENTS_PAGE_URL = "https://www.bseindia.com/corporates/ann.html?anntype=C"
BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
NSE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements"

SEEN_FILE = os.getenv("SEEN_FILE", "seen.txt")
BOT_ENABLED = env_bool("BOT_ENABLED", True)
SEND_STARTUP_MESSAGE = env_bool("SEND_STARTUP_MESSAGE", True)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_SECONDS = env_int("POLL_SECONDS", 15)
MAX_SEEN_HEADLINES = env_int("MAX_SEEN_HEADLINES", 10000)

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

LOW_VALUE_FILINGS = {
    "board meeting",
    "disclosure",
    "compliance",
    "shareholding",
    "newspaper publication",
}
