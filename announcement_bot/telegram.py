from html import escape


def format_telegram_message(exchange, company, event_type, amount, client, signal, link):
    safe_exchange = escape(exchange or "Unknown")
    safe_company = escape(company or "Unknown")
    safe_event_type = escape(event_type or "General")
    safe_amount = escape(amount or "Not Mentioned")
    safe_client = escape(client or "Unknown")
    safe_signal = escape(signal or "NEUTRAL")
    safe_link = escape(link or "")
    return (
        "\U0001f525 <b>SIGNAL FOUND</b>\n\n"
        f"\U0001f3e6 Exchange: <b>{safe_exchange}</b>\n"
        f"\U0001f3e2 Company: <b>{safe_company}</b>\n"
        f"\U0001f4ca Event: <b>{safe_event_type}</b>\n"
        f"\U0001f4b0 Amount: <b>{safe_amount}</b>\n"
        f"\U0001f91d Client: <b>{safe_client}</b>\n"
        f"\U0001f4c8 Signal: <b>{safe_signal}</b>\n\n"
        "\U0001f517 Announcement:\n"
        f"{safe_link}"
    )
