import time
from datetime import datetime, timezone
from typing import Any

import requests


BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"

CHECK_EVERY_SECONDS = 30
LOOKAHEAD_MINUTES = 20

BTC_WORDS = (
    "btc",
    "bitcoin",
    "cf benchmarks",
)


def is_bitcoin_market(market: dict[str, Any]) -> bool:
    text = " ".join(
        str(market.get(field, ""))
        for field in (
            "ticker",
            "event_ticker",
            "title",
            "subtitle",
            "yes_sub_title",
            "no_sub_title",
            "rules_primary",
        )
    ).lower()

    return any(word in text for word in BTC_WORDS)


def seconds_until_close(close_time: str) -> int:
    close_dt = datetime.fromisoformat(
        close_time.replace("Z", "+00:00")
    )
    now = datetime.now(timezone.utc)
    return int((close_dt - now).total_seconds())


def get_nearby_bitcoin_markets() -> None:
    now_ts = int(time.time())
    future_ts = now_ts + LOOKAHEAD_MINUTES * 60

    response = requests.get(
        f"{BASE_URL}/markets",
        params={
            "limit": 1000,
            "min_close_ts": now_ts,
            "max_close_ts": future_ts,
            "mve_filter": "exclude",
        },
        timeout=30,
    )

    print(f"HTTP status: {response.status_code}", flush=True)
    response.raise_for_status()

    markets = response.json().get("markets", [])

    matches = [
        market
        for market in markets
        if is_bitcoin_market(market)
    ]

    matches.sort(
        key=lambda market: market.get("close_time", "")
    )

    print("=" * 55, flush=True)
    print(
        f"BTC markets closing within {LOOKAHEAD_MINUTES} minutes: "
        f"{len(matches)}",
        flush=True,
    )

    if not matches:
        print(
            "No short-term BTC markets found in demo right now.",
            flush=True,
        )

    for market in matches[:20]:
        close_time = market.get("close_time")
        remaining = (
            seconds_until_close(close_time)
            if close_time
            else -1
        )

        minutes = max(remaining, 0) // 60
        seconds = max(remaining, 0) % 60

        print("-" * 55, flush=True)
        print(f"Ticker: {market.get('ticker')}", flush=True)
        print(f"Event: {market.get('event_ticker')}", flush=True)
        print(f"Title: {market.get('title')}", flush=True)
        print(f"Subtitle: {market.get('subtitle')}", flush=True)
        print(f"Closes in: {minutes}:{seconds:02d}", flush=True)
        print(
            f"YES bid/ask: "
            f"{market.get('yes_bid_dollars')} / "
            f"{market.get('yes_ask_dollars')}",
            flush=True,
        )
        print(
            f"NO bid/ask: "
            f"{market.get('no_bid_dollars')} / "
            f"{market.get('no_ask_dollars')}",
            flush=True,
        )
        print(
            f"Last price: {market.get('last_price_dollars')}",
            flush=True,
        )

    print("=" * 55, flush=True)


def main() -> None:
    print("Phase 2 BTC short-market scanner started.", flush=True)
    print("Safety mode: READ ONLY / ZERO ORDERS", flush=True)

    while True:
        try:
            get_nearby_bitcoin_markets()
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

        print("Next scan in 30 seconds.", flush=True)
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
