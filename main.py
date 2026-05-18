import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from announcement_bot.config import (
    BOT_ENABLED,
    DEBUG_FILTERS,
    RUNNING_MODE,
    MAX_LOOKBACK_HOURS,
    MAX_NOTIFICATIONS_PER_RUN,
    POLL_SECONDS,
    SEND_STARTUP_MESSAGE,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)
from announcement_bot.extractors import (
    assess_materiality,
    classify_event,
    extract_amount,
    extract_client,
    is_hard_reject,
    parse_pdf_if_needed,
)
from announcement_bot.fetchers import extract_announcement_link, fetch_announcements
from announcement_bot.telegram import format_telegram_message
from announcement_bot.utils import clean_text, load_seen, normalize_text, remember_seen, similarity


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
    telegram_enabled = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
    print(
        f"Running Mode: {RUNNING_MODE}",
        flush=True,
    )
    print(
        "Config: "
        f"BOT_ENABLED={BOT_ENABLED}, "
        f"RUNNING_MODE={RUNNING_MODE}, "
        f"Telegram Enabled={telegram_enabled}, "
        f"DEBUG_FILTERS={DEBUG_FILTERS}, "
        f"POLL_SECONDS={POLL_SECONDS}, "
        f"SEND_STARTUP_MESSAGE={SEND_STARTUP_MESSAGE}, "
        f"MAX_LOOKBACK_HOURS={MAX_LOOKBACK_HOURS}, "
        f"MAX_NOTIFICATIONS_PER_RUN={MAX_NOTIFICATIONS_PER_RUN}",
        flush=True,
    )


def parse_broadcast_date(raw_date):
    if not raw_date:
        return None

    raw_date = clean_text(str(raw_date), default="").strip()
    if not raw_date:
        return None

    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_date, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def is_recent(broadcast_date):
    if broadcast_date is None:
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_LOOKBACK_HOURS)
    return broadcast_date >= cutoff


def build_seen_key(exchange, headline, source_url, broadcast_date):
    date_key = broadcast_date.isoformat() if broadcast_date else ""
    return f"{exchange}|{source_url or ''}|{date_key}|{headline}"


def parse_seen_key(seen_key):
    parts = seen_key.split("|", 3)
    if len(parts) < 4:
        return "", "", ""
    return parts[0], parts[1], parts[3]


def build_seen_state(seen_queue):
    seen_urls = set()
    seen_headlines = set()
    for key in seen_queue:
        _, source_url, headline = parse_seen_key(key)
        if source_url:
            seen_urls.add(source_url)
        if headline:
            seen_headlines.add(normalize_text(headline, default=""))
    return seen_urls, seen_headlines


def log_filter(tag, headline, source_url, reason, score=None, event_type=None):
    details = []
    if score is not None:
        details.append(f"score={score}")
    if event_type:
        details.append(f"event={event_type}")
    details.append(f"headline={headline}")
    details.append(f"url={source_url}")
    details.append(f"reason={reason}")
    print(f"{tag}: {' | '.join(details)}", flush=True)


def is_duplicate_announcement(headline, source_url, seen_urls, seen_headlines):
    normalized_headline = normalize_text(headline, default="")
    if source_url and source_url in seen_urls:
        return True, "duplicate source URL"
    if normalized_headline in seen_headlines:
        return True, "duplicate headline"
    for existing in seen_headlines:
        if similarity(normalized_headline, existing) >= 0.92:
            return True, "near-identical headline"
    return False, ""


def run_cycle(session, seen_queue, seen_lookup):
    announcements = fetch_announcements()
    accepted_count = 0
    error_count = 0

    skipped_old_count = 0
    skipped_hard_reject_count = 0
    skipped_duplicate_count = 0
    skipped_generic_count = 0

    seen_urls, seen_headlines = build_seen_state(seen_queue)

    for item in announcements:
        try:
            exchange = item.get("EXCHANGE", "BSE")
            company = clean_text(item.get("SLONGNAME"), default="Unknown company")
            headline = clean_text(item.get("HEADLINE"), default="")
            source_url = extract_announcement_link(item)
            broadcast_date = parse_broadcast_date(item.get("BROADCASTDATE"))
            seen_key = build_seen_key(exchange, headline, source_url, broadcast_date)

            if not headline or seen_key in seen_lookup:
                continue

            duplicate, duplicate_reason = is_duplicate_announcement(
                headline, source_url, seen_urls, seen_headlines
            )
            if duplicate:
                log_filter(
                    "FILTERED_DUPLICATE",
                    headline,
                    source_url,
                    duplicate_reason,
                )
                remember_seen(seen_key, seen_queue, seen_lookup)
                skipped_duplicate_count += 1
                continue

            if not is_recent(broadcast_date):
                remember_seen(seen_key, seen_queue, seen_lookup)
                skipped_old_count += 1
                continue

            if is_hard_reject(headline):
                log_filter(
                    "FILTERED_LOW_VALUE",
                    headline,
                    source_url,
                    "hard reject phrase matched",
                )
                remember_seen(seen_key, seen_queue, seen_lookup)
                skipped_hard_reject_count += 1
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

            confidence, strong_confidence, score, reason = assess_materiality(
                event_type=event_type,
                amount_text=amount,
                client=client,
                headline=enriched_text,
            )

            if confidence != "HIGH" and not (confidence == "MEDIUM" and strong_confidence):
                log_filter(
                    "FILTERED_GENERIC",
                    headline,
                    source_url,
                    reason,
                    score=score,
                    event_type=event_type,
                )
                remember_seen(seen_key, seen_queue, seen_lookup)
                skipped_generic_count += 1
                continue

            message = format_telegram_message(
                exchange=exchange,
                company=company,
                event_type=event_type,
                amount=amount,
                client=client,
                confidence=confidence,
                reason=reason,
                link=source_url,
            )

            log_filter(
                "ACCEPTED_HIGH_SIGNAL",
                headline,
                source_url,
                reason,
                score=score,
                event_type=event_type,
            )
            if DEBUG_FILTERS:
                print(
                    "DEBUG_FILTERS enabled; Telegram alert suppressed.",
                    flush=True,
                )
            else:
                send_telegram_message(message)

            remember_seen(seen_key, seen_queue, seen_lookup)
            accepted_count += 1

            if MAX_NOTIFICATIONS_PER_RUN > 0 and accepted_count >= MAX_NOTIFICATIONS_PER_RUN:
                print(
                    f"Notification limit reached ({MAX_NOTIFICATIONS_PER_RUN}); stopping early.",
                    flush=True,
                )
                break
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
        f"{accepted_count} accepted, "
        f"{skipped_duplicate_count} duplicate skipped, "
        f"{skipped_hard_reject_count} hard reject skipped, "
        f"{skipped_generic_count} generic skipped, "
        f"{skipped_old_count} old skipped, "
        f"{error_count} errors.",
        flush=True,
    )


def main():
    describe_config()

    if not BOT_ENABLED:
        print(
            "BOT_ENABLED=false, so the alert worker is exiting cleanly.",
            flush=True,
        )
        sys.exit(0)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID. ",
            "Telegram credentials missing.",
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
        if DEBUG_FILTERS:
            print(
                "DEBUG_FILTERS enabled; startup Telegram message suppressed.",
                flush=True,
            )
        else:
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

    session = requests.Session()
    while True:
        try:
            run_cycle(session, seen_queue, seen_lookup)
        except Exception as error:
            print(f"Error during run cycle: {error}", file=sys.stderr, flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
