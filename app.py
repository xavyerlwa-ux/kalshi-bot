import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests


KALSHI_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"

CHECK_EVERY_SECONDS = 30

# Only record predictions during this window.
MIN_ENTRY_SECONDS = 7 * 60
MAX_ENTRY_SECONDS = 12 * 60

# Current test thresholds. We will adjust these using results.
THREE_MINUTE_THRESHOLD = 0.04
FIVE_MINUTE_THRESHOLD = 0.06

TRACKER_FILE = "paper_trades.json"


def load_tracker() -> dict[str, Any]:
    if not os.path.exists(TRACKER_FILE):
        return {"predictions": {}}

    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {"predictions": {}}


def save_tracker(tracker: dict[str, Any]) -> None:
    with open(TRACKER_FILE, "w", encoding="utf-8") as file:
        json.dump(tracker, file, indent=2)


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_live_btc_price() -> float:
    data = get_json(
        f"{COINBASE_BASE_URL}/products/BTC-USD/ticker"
    )
    return float(data["price"])


def get_one_minute_closes() -> list[float]:
    response = requests.get(
        f"{COINBASE_BASE_URL}/products/BTC-USD/candles",
        params={"granularity": 60},
        timeout=30,
    )
    response.raise_for_status()

    candles = response.json()

    # Coinbase returns newest first, so sort oldest to newest.
    candles.sort(key=lambda candle: candle[0])

    return [float(candle[4]) for candle in candles[-15:]]


def percent_change(old_price: float, new_price: float) -> float:
    if old_price == 0:
        return 0.0

    return ((new_price - old_price) / old_price) * 100


def seconds_until_close(close_time: str) -> int:
    close_datetime = datetime.fromisoformat(
        close_time.replace("Z", "+00:00")
    )

    difference = (
        close_datetime - datetime.now(timezone.utc)
    )

    return int(difference.total_seconds())


def get_current_btc_market() -> dict[str, Any] | None:
    now_timestamp = int(time.time())
    future_timestamp = now_timestamp + (20 * 60)

    data = get_json(
        f"{KALSHI_BASE_URL}/markets",
        params={
            "limit": 1000,
            "min_close_ts": now_timestamp,
            "max_close_ts": future_timestamp,
            "mve_filter": "exclude",
        },
    )

    markets = data.get("markets", [])

    matches = [
        market
        for market in markets
        if str(
            market.get("event_ticker", "")
        ).startswith("KXBTC15M")
    ]

    if not matches:
        return None

    matches.sort(
        key=lambda market: market.get("close_time", "")
    )

    return matches[0]


def get_market(ticker: str) -> dict[str, Any]:
    data = get_json(
        f"{KALSHI_BASE_URL}/markets/{ticker}"
    )
    return data["market"]


def create_signal(
    current_price: float,
    closes: list[float],
) -> tuple[str, float, float]:
    if len(closes) < 6:
        return "SKIP", 0.0, 0.0

    move_3m = percent_change(
        closes[-4],
        current_price,
    )
    move_5m = percent_change(
        closes[-6],
        current_price,
    )

    if (
        move_3m > THREE_MINUTE_THRESHOLD
        and move_5m > FIVE_MINUTE_THRESHOLD
    ):
        signal = "YES"

    elif (
        move_3m < -THREE_MINUTE_THRESHOLD
        and move_5m < -FIVE_MINUTE_THRESHOLD
    ):
        signal = "NO"

    else:
        signal = "SKIP"

    return signal, move_3m, move_5m


def record_prediction(
    tracker: dict[str, Any],
    market: dict[str, Any],
    signal: str,
    btc_price: float,
    move_3m: float,
    move_5m: float,
    seconds_remaining: int,
) -> None:
    ticker = market["ticker"]

    if ticker in tracker["predictions"]:
        return

    if signal == "SKIP":
        return

    tracker["predictions"][ticker] = {
        "ticker": ticker,
        "event_ticker": market.get("event_ticker"),
        "signal": signal,
        "btc_price": btc_price,
        "move_3m": move_3m,
        "move_5m": move_5m,
        "seconds_remaining": seconds_remaining,
        "yes_bid": market.get("yes_bid_dollars"),
        "yes_ask": market.get("yes_ask_dollars"),
        "no_bid": market.get("no_bid_dollars"),
        "no_ask": market.get("no_ask_dollars"),
        "close_time": market.get("close_time"),
        "recorded_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "pending",
        "result": None,
        "correct": None,
    }

    save_tracker(tracker)

    print("PAPER PREDICTION RECORDED", flush=True)
    print(f"Ticker: {ticker}", flush=True)
    print(f"Prediction: {signal}", flush=True)
    print(
        f"BTC at prediction: ${btc_price:,.2f}",
        flush=True,
    )
    print(
        f"Time remaining: "
        f"{seconds_remaining // 60}:"
        f"{seconds_remaining % 60:02d}",
        flush=True,
    )


def update_results(tracker: dict[str, Any]) -> None:
    changed = False

    for ticker, prediction in tracker[
        "predictions"
    ].items():
        if prediction["status"] != "pending":
            continue

        try:
            market = get_market(ticker)
        except requests.HTTPError as error:
            print(
                f"Could not check {ticker}: "
                f"HTTP {error.response.status_code}",
                flush=True,
            )
            continue

        result = str(
            market.get("result", "")
        ).lower()

        if result not in ("yes", "no"):
            continue

        predicted_side = prediction["signal"].lower()
        correct = predicted_side == result

        prediction["status"] = "graded"
        prediction["result"] = result.upper()
        prediction["correct"] = correct
        prediction["settlement_value"] = market.get(
            "settlement_value_dollars"
        )
        prediction["graded_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        changed = True

        print("PREDICTION GRADED", flush=True)
        print(f"Ticker: {ticker}", flush=True)
        print(
            f"Predicted: {prediction['signal']}",
            flush=True,
        )
        print(f"Result: {result.upper()}", flush=True)
        print(
            f"Outcome: "
            f"{'WIN' if correct else 'LOSS'}",
            flush=True,
        )

    if changed:
        save_tracker(tracker)


def print_scoreboard(
    tracker: dict[str, Any],
) -> None:
    predictions = list(
        tracker["predictions"].values()
    )

    graded = [
        prediction
        for prediction in predictions
        if prediction["status"] == "graded"
    ]

    pending = [
        prediction
        for prediction in predictions
        if prediction["status"] == "pending"
    ]

    wins = sum(
        1
        for prediction in graded
        if prediction["correct"] is True
    )

    losses = len(graded) - wins

    accuracy = (
        wins / len(graded) * 100
        if graded
        else 0.0
    )

    print("-" * 55, flush=True)
    print("PAPER SCOREBOARD", flush=True)
    print(
        f"Predictions recorded: {len(predictions)}",
        flush=True,
    )
    print(f"Pending: {len(pending)}", flush=True)
    print(f"Wins: {wins}", flush=True)
    print(f"Losses: {losses}", flush=True)
    print(f"Accuracy: {accuracy:.1f}%", flush=True)
    print("-" * 55, flush=True)


def scan(
    tracker: dict[str, Any],
) -> None:
    update_results(tracker)

    market = get_current_btc_market()

    if market is None:
        print(
            "No active BTC 15-minute market found.",
            flush=True,
        )
        print_scoreboard(tracker)
        return

    current_price = get_live_btc_price()
    closes = get_one_minute_closes()

    signal, move_3m, move_5m = create_signal(
        current_price,
        closes,
    )

    remaining = seconds_until_close(
        market["close_time"]
    )

    print("=" * 55, flush=True)
    print(
        f"BTC: ${current_price:,.2f}",
        flush=True,
    )
    print(f"Ticker: {market['ticker']}", flush=True)
    print(
        f"Time left: "
        f"{max(remaining, 0) // 60}:"
        f"{max(remaining, 0) % 60:02d}",
        flush=True,
    )
    print(f"3-minute move: {move_3m:+.4f}%", flush=True)
    print(f"5-minute move: {move_5m:+.4f}%", flush=True)
    print(f"Current signal: {signal}", flush=True)

    if not (
        MIN_ENTRY_SECONDS
        <= remaining
        <= MAX_ENTRY_SECONDS
    ):
        print(
            "Outside the 7-12 minute recording window.",
            flush=True,
        )
    else:
        record_prediction(
            tracker=tracker,
            market=market,
            signal=signal,
            btc_price=current_price,
            move_3m=move_3m,
            move_5m=move_5m,
            seconds_remaining=remaining,
        )

    print_scoreboard(tracker)
    print("Mode: PAPER TRACKING / ZERO ORDERS", flush=True)
    print("=" * 55, flush=True)


def main() -> None:
    tracker = load_tracker()

    print(
        "Phase 4 BTC paper-performance tracker started.",
        flush=True,
    )
    print(
        "No orders will be placed.",
        flush=True,
    )

    while True:
        try:
            scan(tracker)
        except requests.HTTPError as error:
            response = error.response
            print(
                f"HTTP error {response.status_code}: "
                f"{response.text[:300]}",
                flush=True,
            )
        except Exception as error:
            print(
                f"Bot error: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        print("Next scan in 30 seconds.", flush=True)
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
