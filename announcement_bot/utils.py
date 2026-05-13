from collections import deque

from bs4 import BeautifulSoup

from announcement_bot.config import MAX_SEEN_HEADLINES, SEEN_FILE


def clean_text(value, default="Unknown"):
    text = BeautifulSoup(value or "", "html.parser").get_text(" ").strip()
    return " ".join(text.split()) or default


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
