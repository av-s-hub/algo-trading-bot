import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from announcement_bot.config import (
    BSE_ANNOUNCEMENTS_PAGE_URL,
    BSE_API_URL,
    BSE_ATTACHMENT_BASE_URL,
    BSE_HEADERS,
    BSE_PARAMS,
    NSE_HEADERS,
    NSE_URL,
)
from announcement_bot.utils import clean_text


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


def parse_nse_announcements(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        values = [clean_text(cell.get_text(" "), default="") for cell in cells]
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

        if not saw_header or index + 2 >= len(lines):
            index += 1
            continue

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


def fetch_bse_announcements(session):
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


def fetch_nse_announcements(session):
    session.get("https://www.nseindia.com/", headers=NSE_HEADERS, timeout=20)
    response = session.get(NSE_URL, headers=NSE_HEADERS, timeout=20)
    response.raise_for_status()
    return parse_nse_announcements(response.text)


def fetch_announcements():
    session = requests.Session()
    announcements = []

    for fetcher in (fetch_bse_announcements, fetch_nse_announcements):
        try:
            announcements.extend(fetcher(session))
        except Exception as error:
            print(
                f"Failed to fetch announcements from {fetcher.__name__}: {error}",
                file=sys.stderr,
                flush=True,
            )

    return announcements
