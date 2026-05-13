import sys
from datetime import datetime, timezone

import requests

from announcement_bot.config import (
    BOT_ENABLED,
    POLL_SECONDS,
    SEND_STARTUP_MESSAGE,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)
from announcement_bot.extractors import (
    classify_event,
    classify_signal,
    extract_amount,
    extract_client,
    is_low_value_filing,
    parse_pdf_if_needed,
)
from announcement_bot.fetchers import extract_announcement_link, fetch_announcements
from announcement_bot.telegram import format_telegram_message
from announcement_bot.utils import clean_text, load_seen, remember_seen


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
        session = requests.Session()
        announcements = fetch_announcements()
        new_count = 0
        signal_count = 0
        error_count = 0

        for item in announcements:
            try:
                exchange = item.get("EXCHANGE", "BSE")
                company = clean_text(item.get("SLONGNAME"), default="Unknown company")
                headline = clean_text(item.get("HEADLINE"), default="")
                source_url = extract_announcement_link(item)
                seen_key = f"{exchange}|{company}|{headline}"

                if not headline or seen_key in seen_lookup:
                    continue

                if is_low_value_filing(headline):
                    remember_seen(seen_key, seen_queue, seen_lookup)
                    new_count += 1
                    continue

                event_type = classify_event(headline)
                amount = extract_amount(headline)
                client = extract_client(headline)

                pdf_text = parse_pdf_if_needed(
                    headline=headline,
                    link=source_url,
                    event_type=event_type,
                    amount=amount,
                    session=session,
                )
                enriched_text = headline if not pdf_text else f"{headline}\n{pdf_text}"

                if amount == "Not Mentioned":
                    amount = extract_amount(enriched_text)
                if client == "Unknown":
                    client = extract_client(enriched_text)

                signal = classify_signal(enriched_text, event_type=event_type)
                message = format_telegram_message(
                    exchange=exchange,
                    company=company,
                    event_type=event_type,
                    amount=amount,
                    client=client,
                    signal=signal,
                    link=source_url,
                )

                print(message, flush=True)
                send_telegram_message(message)
                remember_seen(seen_key, seen_queue, seen_lookup)
                new_count += 1
                signal_count += 1
            except Exception as error:
                error_count += 1
                print(
                    f"Failed to process announcement: {error}",
                    file=sys.stderr,
                    flush=True,
                )

        print(
            "Run complete: "
            f"{len(announcements)} announcements, "
            f"{new_count} new, "
            f"{signal_count} signals, "
            f"{error_count} errors.",
            flush=True,
        )
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
