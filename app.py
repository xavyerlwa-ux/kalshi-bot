import time
from datetime import datetime, timezone


def main() -> None:
    print("Xavyer Kalshi Bot started.")
    print("Mode: DEMO / NO TRADING")
    
    while True:
        now = datetime.now(timezone.utc).isoformat()
        print(f"Bot alive: {now}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
