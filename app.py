import time
from datetime import datetime, timezone
from typing import Any

import requests


KALSHI_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"

CHECK_EVERY_SECONDS = 30
LOOKAHEAD_MINUTES = 20


def get_live_btc_price() -> float:
    response = requests.get(
        f"{COINBASE_BASE_URL}/products/BTC-USD/ticker",
        timeout=15,
    )
    response.raise_for_status()

    return float(response.json()["price"])


def get_one_minute_closes() -> list[float]:
    response = requests.get(
        f"{COINBASE_BASE_URL}/products/BTC-USD/candles",
        params={"granularity": 60},
        timeout=20,
    )
    response.raise_for_status()

    candles = response.json()

    # Coinbase returns newest candle first.
    candles.sort(key=lambda candle: candle[0])

    return [float(candle[4]) for candle in candles[-15:]]


def percent_change(old_price: float, new_price: float) -> float:
    if old_price == 0:
        return 0.0

    return ((new_price - old_price) / old_price) * 100


def get_current_btc_15m_market() -> dict[str, Any] | None:
    now_ts = int(time.time())
    future_ts = now_ts + LOOKAHEAD_MINUTES * 60

    response = requests.get(
        f"{KALSHI_BASE_URL}/markets",
        params={
            "limit": 1000,
            "min_close_ts": now_ts,
            "max_close_ts": future_ts,
            "mve_filter": "exclude",
        },
        timeout=30,
    )
    response.raise_for_status()

    markets = response.json().get("markets", [])

    btc_markets = [
        market
        for market in markets
        if str(market.get("event_ticker", "")).startswith("KXBTC15M")
    ]

    if not btc_markets:
        return None

    btc_markets.sort(key=lambda market: market.get("close_time", ""))

    return btc_markets[0]


def seconds_until_close(close_time: str) -> int:
    close_dt = datetime.fromisoformat(
        close_time.replace("Z", "+00:00")
    )

    return int(
        (close_dt - datetime.now(timezone.utc)).total_seconds()
    )


def build_signal(
    current_price: float,
    closes: list[float],
) -> tuple[str, float, float]:
    if len(closes) < 6:
        return "SKIP", 0.0, 0.0

    change_3m = percent_change(closes[-4], current_price)
    change_5m = percent_change(closes[-6], current_price)

    if change_3m > 0.04 and change_5m > 0.06:
        signal = "LEAN YES"
    elif change_3m < -0.04 and change_5m < -0.06:
        signal = "LEAN NO"
    else:
        signal = "SKIP"

    return signal, change_3m, change_5m


def scan() -> None:
    market = get_current_btc_15m_market()
    current_price = get_live_btc_price()
    closes = get_one_minute_closes()

    signal, change_3m, change_5m = build_signal(
        current_price,
        closes,
    )

    print("=" * 55, flush=True)
    print(f"Live BTC price: ${current_price:,.2f}", flush=True)
    print(f"3-minute move: {change_3m:+.4f}%", flush=True)
    print(f"5-minute move: {change_5m:+.4f}%", flush=True)

    if market is None:
        print(
            "No active KXBTC15M demo market found.",
            flush=True,
        )
    else:
        remaining = seconds_until_close(market["close_time"])
        minutes = max(remaining, 0) // 60
        seconds = max(remaining, 0) % 60

        print(f"Ticker: {market.get('ticker')}", flush=True)
        print(f"Title: {market.get('title')}", flush=True)
        print(f"Closes in: {minutes}:{seconds:02d}", flush=True)

        print(
            "YES bid/ask: "
            f"{market.get('yes_bid_dollars')} / "
            f"{market.get('yes_ask_dollars')}",
            flush=True,
        )

        print(
            "NO bid/ask: "
            f"{market.get('no_bid_dollars')} / "
            f"{market.get('no_ask_dollars')}",
            flush=True,
        )

    print(f"Signal: {signal}", flush=True)
    print("Mode: READ ONLY / ZERO ORDERS", flush=True)
    print("=" * 55, flush=True)


def main() -> None:
    print("Phase 3 BTC signal bot started.", flush=True)
    print("This is not a probability model.", flush=True)

    while True:
        try:
            scan()
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
