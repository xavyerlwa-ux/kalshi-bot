import base64
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


API_KEY_ID = os.environ["KALSHI_API_KEY_ID"]
PRIVATE_KEY_TEXT = os.environ["KALSHI_PRIVATE_KEY"]
KALSHI_ENV = os.getenv("KALSHI_ENV", "demo").lower()

if KALSHI_ENV == "demo":
    BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
else:
    raise RuntimeError(
        "Safety lock: KALSHI_ENV must be set to 'demo'."
    )


def load_private_key():
    # Fixes Railway values that may store line breaks as \n characters.
    cleaned_key = PRIVATE_KEY_TEXT.strip().replace("\\n", "\n")

    return serialization.load_pem_private_key(
        cleaned_key.encode("utf-8"),
        password=None,
    )


PRIVATE_KEY = load_private_key()


def create_signature(timestamp: str, method: str, path: str) -> str:
    """Create the RSA-PSS signature Kalshi requires."""
    path_without_query = path.split("?")[0]
    message = f"{timestamp}{method.upper()}{path_without_query}".encode("utf-8")

    signature = PRIVATE_KEY.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )

    return base64.b64encode(signature).decode("utf-8")


def authenticated_get(endpoint: str) -> requests.Response:
    url = f"{BASE_URL}{endpoint}"

    # Kalshi requires the complete URL path, including /trade-api/v2.
    signing_path = urlparse(url).path
    timestamp = str(int(time.time() * 1000))
    signature = create_signature(timestamp, "GET", signing_path)

    headers = {
        "KALSHI-ACCESS-KEY": API_KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response


def show_demo_balance() -> None:
    response = authenticated_get("/portfolio/balance")
    data = response.json()

    balance = data["balance"] / 100
    portfolio_value = data.get("portfolio_value", 0) / 100

    print("Kalshi demo connection successful!", flush=True)
    print(f"Available demo balance: ${balance:,.2f}", flush=True)
    print(f"Demo portfolio value: ${portfolio_value:,.2f}", flush=True)


def main() -> None:
    print("Xavyer Kalshi Bot started.", flush=True)
    print("Safety mode: DEMO / BALANCE CHECK ONLY", flush=True)

    while True:
        try:
            show_demo_balance()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            body = exc.response.text[:300] if exc.response else str(exc)
            print(f"Kalshi HTTP error {status}: {body}", flush=True)
        except Exception as exc:
            print(
                f"Bot error: {type(exc).__name__}: {exc}",
                flush=True,
            )

        now = datetime.now(timezone.utc).isoformat()
        print(f"Next check in 5 minutes. UTC time: {now}", flush=True)
        time.sleep(300)


if __name__ == "__main__":
    main()
