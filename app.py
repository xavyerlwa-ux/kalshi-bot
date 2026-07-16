import time
from typing import Any

import requests


BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"

SEARCH_WORDS = (
    "btc",
    "bitcoin",
    "crypto",
    "cf benchmarks",
    "rti",
)

CHECK_EVERY_SECONDS = 300
MAX_PAGES = 20


def contains_search_word(market: dict[str, Any]) -> bool:
    searchable_text = " ".join(
        str(market.get(field, ""))
        for field in (
            "ticker",
            "event_ticker",
            "series_ticker",
            "title",
            "subtitle",
            "yes_sub_title",
            "no_sub_title",
            "rules_primary",
        )
    ).lower()

    return any(word in searchable_text for word in SEARCH_WORDS)


def find_btc_markets() -> None:
    cursor: str | None = None
    page_number = 0
    markets_checked = 0
    matches: list[dict[str, Any]] = []

    while page_number < MAX_PAGES:
        page_number += 1

        params: dict[str, Any] = {
            "status": "open",
            "limit": 1000,
        }

        if cursor:
            params["cursor"] = cursor

        response = requests.get(
            f"{BASE_URL}/markets",
            params=params,
            timeout=30,
        )

        print(
            f"Page {page_number} HTTP status: {response.status_code}",
            flush=True,
        )

        response.raise_for_status()

        data = response.json()
        markets = data.get("markets", [])
        markets_checked += len(markets)

        for market in markets:
            if contains_search_word(market):
                matches.append(market)

        cursor = data.get("cursor")

        if not cursor or not markets:
            break

    print("=" * 50, flush=True)
    print(f"Markets checked: {markets_checked}", flush=True)
    print(f"Possible BTC markets found: {len(matches)}", flush=True)

    if not matches:
        print(
            "No matching BTC markets exist in the demo environment right now.",
            flush=True,
        )
    else:
        for number, market in enumerate(matches, start=1):
            print("-" * 50, flush=True)
            print(f"Match #{number}", flush=True)
            print(f"Ticker: {market.get('ticker')}", flush=True)
            print(f"Series: {market.get('series_ticker')}", flush=True)
            print(f"Event: {market.get('event_ticker')}", flush=True)
            print(f"Title: {market.get('title')}", flush=True)
            print(f"Subtitle: {market.get('subtitle')}", flush=True)
            print(f"Yes bid: {market.get('yes_bid')}", flush=True)
            print(f"Yes ask: {market.get('yes_ask')}", flush=True)
            print(f"Close time: {market.get('close_time')}", flush=True)

    print("=" * 50, flush=True)


def main() -> None:
    print("BTC market search bot started.", flush=True)
    print("Safety mode: READ ONLY / ZERO ORDERS", flush=True)

    while True:
        try:
            find_btc_markets()
        except requests.HTTPError as error:
            response = error.response
            print(
                f"HTTP error {response.status_code}: "
                f"{response.text[:500]}",
                flush=True,
            )
        except Exception as error:
            print(
                f"Bot error: {type(error).__name__}: {error}",
                flush=True,
            )

        print("Searching again in 5 minutes.", flush=True)
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
