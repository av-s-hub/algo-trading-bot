import os

import requests


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before running.")

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

response = requests.get(
    url,
    params={
        "chat_id": CHAT_ID,
        "text": "Bot working",
    },
    timeout=20,
)

print(response.text)
