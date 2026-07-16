import os
import time
import requests

BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

API_KEY = os.environ["KALSHI_API_KEY_ID"]

def get_markets():
    headers = {
        "KALSHI-ACCESS-KEY": API_KEY
    }

    try:
        r = requests.get(
            f"{BASE_URL}/markets",
            headers=headers,
            timeout=15
        )

        print(f"HTTP Status: {r.status_code}")

        if r.status_code == 200:
            data = r.json()

            print("========== BTC MARKETS ==========")

            for market in data.get("markets", []):
                text = str(market)

                if "BTC" in text or "Bitcoin" in text:
                    print(text)

            print("================================")

        else:
            print(r.text)

    except Exception as e:
        print(e)


print("Watching BTC markets...")

while True:
    get_markets()
    time.sleep(60)
