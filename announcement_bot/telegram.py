from html import escape


def format_telegram_message(
    exchange,
    company,
    event_type,
    amount,
    client,
    confidence,
    reason,
    link,
):
    safe_exchange = escape(exchange or "Unknown")
    safe_company = escape(company or "Unknown")
    safe_event_type = escape(event_type or "GENERAL")
    safe_amount = escape(amount or "Not Mentioned")
    safe_client = escape(client or "Unknown")
    safe_confidence = escape(confidence or "LOW")
    safe_reason = escape(reason or "Material market development.")
    safe_link = escape(link or "")

    return (
        "🔥 <b>HIGH VALUE SIGNAL</b>\n\n"
        f"🏛 Exchange: <b>{safe_exchange}</b>\n"
        f"🏢 Company: <b>{safe_company}</b>\n"
        f"📌 Event: <b>{safe_event_type}</b>\n"
        f"💰 Amount: <b>{safe_amount}</b>\n"
        f"🤝 Client: <b>{safe_client}</b>\n"
        f"📈 Confidence: <b>{safe_confidence}</b>\n\n"
        "🧾 Why It Matters:\n"
        f"{safe_reason}\n\n"
        "🔗 Source:\n"
        f"{safe_link}"
    )
