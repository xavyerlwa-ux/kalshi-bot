import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests


# ============================================================
# SETTINGS
# ============================================================

# Kalshi demo market-data API.
# This program does NOT contain any order-placement code.
KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# Coinbase public market-data API.
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"

CHECK_EVERY_SECONDS = 30

# Momentum needed before producing a YES or NO signal.
THREE_MINUTE_THRESHOLD = 0.04
FIVE_MINUTE_THRESHOLD = 0.06

# Only paper-record contracts priced from 35¢ through 65¢.
MIN_CONTRACT_PRICE = 0.35
MAX_CONTRACT_PRICE = 0.65

# Apply the stricter trade filter from 3–12 minutes remaining.
MIN_FILTER_TIME_LEFT = 2 * 60
MAX_FILTER_TIME_LEFT = 15 * 60

# General recording window.
MIN_ENTRY_SECONDS = 2 * 60
MAX_ENTRY_SECONDS = 15 * 60

# Local storage.
# This can reset whenever Railway redeploys or restarts.
TRACKER_FILE = "paper_trades.json"

REQUEST_TIMEOUT = 30


# ============================================================
# GENERAL HELPERS
# ============================================================

def default_tracker() -> dict[str, Any]:
    return {"predictions": {}}


def load_tracker() -> dict[str, Any]:
    if not os.path.exists(TRACKER_FILE):
        return default_tracker()

    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as file:
            tracker = json.load(file)

        if not isinstance(tracker, dict):
            return default_tracker()

        predictions = tracker.get("predictions")

        if not isinstance(predictions, dict):
            tracker["predictions"] = {}

        return tracker

    except (json.JSONDecodeError, OSError):
        return default_tracker()


def save_tracker(tracker: dict[str, Any]) -> None:
    temporary_file = f"{TRACKER_FILE}.tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(tracker, file, indent=2)

    os.replace(temporary_file, TRACKER_FILE)


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/json",
            "User-Agent": "Xavyer-Kalshi-Paper-Bot/1.0",
        },
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object from {url}"
        )

    return data


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value is None or value == "":
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def market_price_dollars(
    market: dict[str, Any],
    dollar_field: str,
    cent_field: str,
) -> float:
    dollar_value = market.get(dollar_field)

    if dollar_value not in (None, ""):
        return safe_float(dollar_value)

    cent_value = market.get(cent_field)

    if cent_value not in (None, ""):
        return safe_float(cent_value) / 100

    return 0.0


def percent_change(
    old_price: float,
    new_price: float,
) -> float:
    if old_price == 0:
        return 0.0

    return (
        (new_price - old_price)
        / old_price
        * 100
    )


def seconds_until_close(close_time: str) -> int:
    close_datetime = datetime.fromisoformat(
        close_time.replace("Z", "+00:00")
    )

    difference = (
        close_datetime
        - datetime.now(timezone.utc)
    )

    return int(difference.total_seconds())


def format_time_left(seconds: int) -> str:
    seconds = max(seconds, 0)

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    return f"{minutes}:{remaining_seconds:02d}"


# ============================================================
# COINBASE BTC DATA
# ============================================================

def get_live_btc_price() -> float:
    data = get_json(
        f"{COINBASE_BASE_URL}/products/BTC-USD/ticker"
    )

    price = safe_float(data.get("price"))

    if price <= 0:
        raise ValueError(
            "Coinbase returned an invalid BTC price."
        )

    return price


def get_one_minute_closes() -> list[float]:
    response = requests.get(
        f"{COINBASE_BASE_URL}/products/BTC-USD/candles",
        params={"granularity": 60},
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/json",
            "User-Agent": "Xavyer-Kalshi-Paper-Bot/1.0",
        },
    )

    response.raise_for_status()

    candles = response.json()

    if not isinstance(candles, list):
        raise ValueError(
            "Coinbase returned invalid candle data."
        )

    valid_candles = [
        candle
        for candle in candles
        if (
            isinstance(candle, list)
            and len(candle) >= 5
        )
    ]

    # Coinbase normally returns newest first.
    # Sort by timestamp so oldest is first.
    valid_candles.sort(
        key=lambda candle: candle[0]
    )

    closes = [
        safe_float(candle[4])
        for candle in valid_candles[-30:]
    ]

    closes = [
        close
        for close in closes
        if close > 0
    ]

    if len(closes) < 6:
        raise ValueError(
            "Not enough valid Coinbase candles."
        )

    return closes


# ============================================================
# KALSHI MARKET DATA
# ============================================================

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

    if not isinstance(markets, list):
        return None

    matches: list[dict[str, Any]] = []

    for market in markets:
        if not isinstance(market, dict):
            continue

        event_ticker = str(
            market.get("event_ticker", "")
        )

        ticker = str(
            market.get("ticker", "")
        )

        is_btc_15m = (
            event_ticker.startswith("KXBTC15M")
            or ticker.startswith("KXBTC15M")
        )

        if not is_btc_15m:
            continue

        close_time = market.get("close_time")

        if not close_time:
            continue

        try:
            remaining = seconds_until_close(
                str(close_time)
            )
        except (TypeError, ValueError):
            continue

        if remaining <= 0:
            continue

        matches.append(market)

    if not matches:
        return None

    matches.sort(
        key=lambda market: str(
            market.get("close_time", "")
        )
    )

    return matches[0]


def get_market(ticker: str) -> dict[str, Any]:
    try:
        data = get_json(
            f"{KALSHI_BASE_URL}/markets/{ticker}"
        )

    except requests.HTTPError as error:
        response = error.response

        if response is None or response.status_code != 404:
            raise

        # Settled markets can eventually move to the
        # historical endpoint.
        data = get_json(
            f"{KALSHI_BASE_URL}/historical/markets/{ticker}"
        )

    market = data.get("market")

    if not isinstance(market, dict):
        raise ValueError(
            f"No market object returned for {ticker}"
        )

    return market


# ============================================================
# SIGNAL ENGINE
# ============================================================

def create_signal(
    current_price: float,
    closes: list[float],
) -> tuple[str, float, float]:
    if len(closes) < 6:
        return "SKIP", 0.0, 0.0

    # Replace the newest completed candle with the
    # current live BTC price for a fresher estimate.
    updated_closes = closes.copy()
    updated_closes[-1] = current_price

    move_3m = percent_change(
        updated_closes[-4],
        current_price,
    )

    move_5m = percent_change(
        updated_closes[-6],
        current_price,
    )

    if (
        move_3m >= THREE_MINUTE_THRESHOLD
        and move_5m >= FIVE_MINUTE_THRESHOLD
    ):
        signal = "YES"

    elif (
        move_3m <= -THREE_MINUTE_THRESHOLD
        and move_5m <= -FIVE_MINUTE_THRESHOLD
    ):
        signal = "NO"

    else:
        signal = "SKIP"

    return signal, move_3m, move_5m


# ============================================================
# PAPER PREDICTION TRACKING
# ============================================================

def record_prediction(
    tracker: dict[str, Any],
    market: dict[str, Any],
    signal: str,
    btc_price: float,
    move_3m: float,
    move_5m: float,
    seconds_remaining: int,
    yes_ask: float,
    no_ask: float,
) -> None:
    if signal == "SKIP":
        return

    ticker = str(market.get("ticker", ""))

    if not ticker:
        return

    predictions = tracker.setdefault(
        "predictions",
        {},
    )

    if ticker in predictions:
        return

    selected_price = (
        yes_ask
        if signal == "YES"
        else no_ask
    )

    predictions[ticker] = {
        "ticker": ticker,
        "event_ticker": market.get(
            "event_ticker"
        ),
        "signal": signal,
        "btc_price": btc_price,
        "move_3m": move_3m,
        "move_5m": move_5m,
        "selected_contract_price": selected_price,
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "seconds_remaining": seconds_remaining,
        "close_time": market.get(
            "close_time"
        ),
        "recorded_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "pending",
        "result": None,
        "correct": None,
    }

    save_tracker(tracker)

    print(
        "PAPER PREDICTION RECORDED",
        flush=True,
    )
    print(
        f"Ticker: {ticker}",
        flush=True,
    )
    print(
        f"Prediction: {signal}",
        flush=True,
    )
    print(
        f"Paper entry price: "
        f"{selected_price:.2f}",
        flush=True,
    )


def update_results(
    tracker: dict[str, Any],
) -> None:
    predictions = tracker.get(
        "predictions",
        {},
    )

    if not isinstance(predictions, dict):
        return

    changed = False

    for ticker, prediction in predictions.items():
        if not isinstance(prediction, dict):
            continue

        if prediction.get("status") != "pending":
            continue

        try:
            market = get_market(ticker)

        except requests.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else "unknown"
            )

            print(
                f"Could not grade {ticker}: "
                f"HTTP {status_code}",
                flush=True,
            )
            continue

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            print(
                f"Could not grade {ticker}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            continue

        result = str(
            market.get("result", "")
        ).strip().lower()

        if result not in ("yes", "no"):
            continue

        predicted_side = str(
            prediction.get("signal", "")
        ).lower()

        correct = predicted_side == result

        prediction["status"] = "graded"
        prediction["result"] = result.upper()
        prediction["correct"] = correct
        prediction["settlement_value"] = (
            market.get(
                "settlement_value_dollars"
            )
        )
        prediction["graded_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        changed = True

        print(
            "PREDICTION GRADED",
            flush=True,
        )
        print(
            f"Ticker: {ticker}",
            flush=True,
        )
        print(
            f"Predicted: "
            f"{prediction.get('signal')}",
            flush=True,
        )
        print(
            f"Result: {result.upper()}",
            flush=True,
        )
        print(
            "Outcome: "
            f"{'WIN' if correct else 'LOSS'}",
            flush=True,
        )

    if changed:
        save_tracker(tracker)


def print_scoreboard(
    tracker: dict[str, Any],
) -> None:
    predictions_dict = tracker.get(
        "predictions",
        {},
    )

    if not isinstance(predictions_dict, dict):
        predictions_dict = {}

    predictions = [
        prediction
        for prediction in predictions_dict.values()
        if isinstance(prediction, dict)
    ]

    graded = [
        prediction
        for prediction in predictions
        if prediction.get("status") == "graded"
    ]

    pending = [
        prediction
        for prediction in predictions
        if prediction.get("status") == "pending"
    ]

    wins = sum(
        1
        for prediction in graded
        if prediction.get("correct") is True
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
        f"Predictions recorded: "
        f"{len(predictions)}",
        flush=True,
    )
    print(
        f"Pending: {len(pending)}",
        flush=True,
    )
    print(
        f"Wins: {wins}",
        flush=True,
    )
    print(
        f"Losses: {losses}",
        flush=True,
    )
    print(
        f"Accuracy: {accuracy:.1f}%",
        flush=True,
    )
    print("-" * 55, flush=True)


# ============================================================
# MAIN SCAN
# ============================================================

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

    close_time = str(
        market.get("close_time", "")
    )

    if not close_time:
        raise ValueError(
            "The active Kalshi market has no close_time."
        )

    remaining = seconds_until_close(
        close_time
    )

    yes_ask = market_price_dollars(
        market,
        "yes_ask_dollars",
        "yes_ask",
    )

    no_ask = market_price_dollars(
        market,
        "no_ask_dollars",
        "no_ask",
    )

    selected_ask = 0.0

    if signal == "YES":
        selected_ask = yes_ask

    elif signal == "NO":
        selected_ask = no_ask

    price_is_valid = (
        MIN_CONTRACT_PRICE
        <= selected_ask
        <= MAX_CONTRACT_PRICE
    )

    filter_time_is_valid = (
        MIN_FILTER_TIME_LEFT
        <= remaining
        <= MAX_FILTER_TIME_LEFT
    )

    original_signal = signal
    rejection_reason: str | None = None

    if signal != "SKIP" and not price_is_valid:
        rejection_reason = (
            "selected contract price is "
            "outside 35¢–65¢"
        )
        signal = "SKIP"

    elif (
        signal != "SKIP"
        and not filter_time_is_valid
    ):
        rejection_reason = (
            "market is outside the "
            "3–12 minute filter window"
        )
        signal = "SKIP"

    print("=" * 55, flush=True)
    print(
        f"BTC: ${current_price:,.2f}",
        flush=True,
    )
    print(
        f"Ticker: {market.get('ticker')}",
        flush=True,
    )
    print(
        f"Time left: "
        f"{format_time_left(remaining)}",
        flush=True,
    )
    print(
        f"3-minute move: {move_3m:+.4f}%",
        flush=True,
    )
    print(
        f"5-minute move: {move_5m:+.4f}%",
        flush=True,
    )
    print(
        f"YES ask: {yes_ask:.2f}",
        flush=True,
    )
    print(
        f"NO ask: {no_ask:.2f}",
        flush=True,
    )
    print(
        f"Raw momentum signal: {original_signal}",
        flush=True,
    )

    if rejection_reason is not None:
        print(
            f"Signal rejected: "
            f"{rejection_reason}.",
            flush=True,
        )

    print(
        f"Final signal: {signal}",
        flush=True,
    )
    print("=" * 55, flush=True)

    entry_window_is_valid = (
        MIN_ENTRY_SECONDS
        <= remaining
        <= MAX_ENTRY_SECONDS
    )

    if not entry_window_is_valid:
        print(
            "Outside the 2–14 minute "
            "recording window.",
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
            yes_ask=yes_ask,
            no_ask=no_ask,
        )

    print_scoreboard(tracker)

    print(
        "Mode: PAPER TRACKING / ZERO ORDERS",
        flush=True,
    )


# ============================================================
# PROGRAM LOOP
# ============================================================

def main() -> None:
    tracker = load_tracker()

    print(
        "Xavyer BTC paper-performance tracker started.",
        flush=True,
    )
    print(
        "Safety mode: PAPER ONLY / ZERO ORDERS",
        flush=True,
    )
    print(
        f"Scanning every "
        f"{CHECK_EVERY_SECONDS} seconds.",
        flush=True,
    )

    while True:
        try:
            scan(tracker)

        except requests.HTTPError as error:
            response = error.response

            status_code = (
                response.status_code
                if response is not None
                else "unknown"
            )

            response_text = (
                response.text[:300]
                if response is not None
                else ""
            )

            print(
                f"HTTP error {status_code}: "
                f"{response_text}",
                flush=True,
            )

        except requests.RequestException as error:
            print(
                "Network error: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        except Exception as error:
            # Keep the bot running after unexpected
            # individual-scan errors.
            print(
                "Bot scan error: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        print(
            f"Next scan in "
            f"{CHECK_EVERY_SECONDS} seconds.",
            flush=True,
        )

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
