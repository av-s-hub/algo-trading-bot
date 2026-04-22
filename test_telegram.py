import requests

TOKEN = "8289424285:AAEltFT3XRwAJcmqi72-XktYuX5wB-kL8IA"
CHAT_ID = "967350904"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

response = requests.get(url, params={
    "chat_id": CHAT_ID,
    "text": "✅ Bot working"
})

print(response.text)