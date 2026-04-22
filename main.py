import requests
from bs4 import BeautifulSoup
import time

# ================= TELEGRAM =================
TOKEN = "8289424285:AAEltFT3XRwAJcmqi72-XktYuX5wB-kL8IA"
CHAT_ID = "967350904"   # your chat id

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{8289424285:AAEltFT3XRwAJcmqi72-XktYuX5wB-kL8IA}/sendMessage"
    params = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.get(url, params=params)

# ================= BSE API =================
url = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json"
}

params = {
    "pageno": 1,
    "strCat": "-1",
    "strPrevDate": "",
    "strScrip": "",
    "strSearch": "P",
    "strToDate": "",
    "strType": "C",
    "subcategory": "-1"
}

# ================= FILTER =================
def check_signal(text):
    text = text.lower()

    ignore_words = [
        "disclosure", "regulation", "meeting",
        "results", "presentation", "shareholding", "board"
    ]

    for word in ignore_words:
        if word in text:
            return False

    keywords = [
        "order", "contract", "awarded",
        "bagged", "work order", "project", "secured"
    ]

    for word in keywords:
        if word in text:
            return True

    return False

# ================= MAIN LOOP =================
print("🚀 Running Live Alert System...\n")

seen = set()  # to avoid duplicate alerts

while True:
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        for item in data["Table"]:
            raw_text = item["HEADLINE"]
            company = item["SLONGNAME"]

            # clean html
            headline = BeautifulSoup(raw_text, "html.parser").get_text()

            # avoid duplicates
            if headline in seen:
                continue

            if check_signal(headline):
                message = f"""🔥 SIGNAL FOUND

🏢 Company: {company}
📰 News: {headline}
"""

                print(message)
                send_telegram_message(message)

                seen.add(headline)

        time.sleep(15)  # check every 15 seconds

    except Exception as e:
        print("Error:", e)
        time.sleep(10)