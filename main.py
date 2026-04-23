import os
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
SEEN_FILE = os.getenv("SEEN_FILE", "seen.txt")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))
SEND_STARTUP_MESSAGE = os.getenv("SEND_STARTUP_MESSAGE", "true").lower() == "true"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
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


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as file:
            return {line.strip() for line in file if line.strip()}
    except FileNotFoundError:
        return set()


def remember_seen(headline):
    with open(SEEN_FILE, "a", encoding="utf-8") as file:
        file.write(headline + "\n")


def check_signal(text):
    normalized = text.lower()

    if any(word in normalized for word in IGNORE_WORDS):
        return False

    return any(word in normalized for word in KEYWORDS)


def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variable."
        )

    response = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        params={"chat_id": TELEGRAM_CHAT_ID, "text": message},
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
        f"TELEGRAM_BOT_TOKEN={token_status}, "
        f"TELEGRAM_CHAT_ID={chat_status}, "
        f"POLL_SECONDS={POLL_SECONDS}, "
        f"SEND_STARTUP_MESSAGE={SEND_STARTUP_MESSAGE}",
        flush=True,
    )


def fetch_announcements():
    response = requests.get(
        BSE_URL,
        headers=BSE_HEADERS,
        params=BSE_PARAMS,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("Table", [])


def run():
    describe_config()

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. "
            "Set them in Railway Variables.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    seen = load_seen()
    print(
        f"Running live alert system. Loaded {len(seen)} seen headlines.",
        flush=True,
    )

    if SEND_STARTUP_MESSAGE:
        try:
            started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            send_telegram_message(f"Alert bot started on Railway at {started_at}.")
            print("Startup Telegram message sent.", flush=True)
        except Exception as error:
            print(
                f"Startup Telegram message failed: {error}",
                file=sys.stderr,
                flush=True,
            )

    while True:
        try:
            announcements = fetch_announcements()
            new_count = 0
            signal_count = 0

            for item in announcements:
                raw_text = item.get("HEADLINE", "")
                company = item.get("SLONGNAME", "Unknown company")
                headline = BeautifulSoup(raw_text, "html.parser").get_text().strip()

                if not headline or headline in seen:
                    continue

                seen.add(headline)
                remember_seen(headline)
                new_count += 1

                if not check_signal(headline):
                    continue

                signal_count += 1
                message = (
                    "SIGNAL FOUND\n\n"
                    f"Company: {company}\n"
                    f"News: {headline}"
                )

                print(message, flush=True)
                send_telegram_message(message)

            print(
                "Poll complete: "
                f"{len(announcements)} announcements, "
                f"{new_count} new, "
                f"{signal_count} signals.",
                flush=True,
            )
            time.sleep(POLL_SECONDS)
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr, flush=True)
            time.sleep(10)


if __name__ == "__main__":
    run()
