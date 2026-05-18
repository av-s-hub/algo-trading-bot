import os
import sys
from pathlib import Path


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


# Runtime detection: prefer GitHub Actions when the env var is present.
GITHUB_ACTIONS_FLAG = os.getenv("GITHUB_ACTIONS", "").strip().lower() in {"1", "true"}
RUNNING_MODE = "GITHUB_ACTIONS" if GITHUB_ACTIONS_FLAG else "LOCAL"


def _load_dotenv_if_present():
    """Load a simple .env file from repository root into environment for LOCAL runs.
    This does not require python-dotenv and will not overwrite existing env vars.
    """
    if GITHUB_ACTIONS_FLAG:
        return

    root = Path(os.getcwd())
    dotenv = root / ".env"
    if not dotenv.exists():
        return

    try:
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and os.getenv(key) is None:
                os.environ[key] = val
    except Exception:
        # best-effort only; don't fail startup for parser errors
        pass


# Load .env for local development if present
_load_dotenv_if_present()


BSE_ANNOUNCEMENTS_PAGE_URL = "https://www.bseindia.com/corporates/ann.html?anntype=C"
BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
NSE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements"

SEEN_FILE = os.getenv("SEEN_FILE", "seen.txt")
BOT_ENABLED = env_bool("BOT_ENABLED", True)
SEND_STARTUP_MESSAGE = env_bool("SEND_STARTUP_MESSAGE", True)
# Prefer secrets provided by the environment (GitHub Actions) or local .env / env var.
TELEGRAM_TOKEN = "8289424285:AAE3MH2uyBFjfndu9xyIuS8tInYaIknAHTw" 
TELEGRAM_CHAT_ID = "967350904"
POLL_SECONDS = env_int("POLL_SECONDS", 15)
MAX_LOOKBACK_HOURS = env_int("MAX_LOOKBACK_HOURS", 24)
MAX_NOTIFICATIONS_PER_RUN = env_int("MAX_NOTIFICATIONS_PER_RUN", 20)
MAX_SEEN_HEADLINES = env_int("MAX_SEEN_HEADLINES", 10000)
DEBUG_FILTERS = env_bool("DEBUG_FILTERS", True)

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
