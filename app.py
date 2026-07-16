import time
import requests

BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"


def inspect_markets() -> None:
    try:
        response = requests.get(
            f"{BASE_URL}/markets",
            params={
                "status": "open",
                "limit": 20,
            },
            timeout=20,
        )

        print(f"HTTP status: {response.status_code}", flush=True)
        response.raise_for_status()

        data = response.json()
        markets = data.get("markets", [])

        print(f"Markets returned: {len(markets)}", flush=True)
        print("========== MARKET NAMES ==========", flush=True)

        for number, market in enumerate(markets, start=1):
            ticker = market.get("ticker", "No ticker")
            title = market.get("title", "No title")
            subtitle = market.get("subtitle", "")
            status = market.get("status", "unknown")

            print(
                f"{number}. {ticker} | {title} | {subtitle} | {status}",
                flush=True,
            )

        print("==================================", flush=True)

        cursor = data.get("cursor")
        print(f"Next-page cursor exists: {bool(cursor)}", flush=True)

    except requests.HTTPError as error:
        print(
            f"HTTP error: {error.response.status_code} "
            f"{error.response.text[:500]}",
            flush=True,
        )
    except Exception as error:
        print(
            f"Bot error: {type(error).__name__}: {error}",
            flush=True,
        )


print("Kalshi market inspector started.", flush=True)
print("Safety mode: READ ONLY / NO ORDERS", flush=True)

while True:
    inspect_markets()
    print("Checking again in 5 minutes.", flush=True)
    time.sleep(300)
