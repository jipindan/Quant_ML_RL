import argparse
import csv
import requests
from datetime import datetime

from clean_klines import clean, print_report

BASE = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def fetch_batch(symbol, interval, start_ms):
    resp = requests.get(BASE, params={
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "limit": MAX_LIMIT,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_all(symbol, interval, start_ms, end_ms):
    rows, cur = [], start_ms
    while cur < end_ms:
        batch = fetch_batch(symbol, interval, cur)
        if not batch:
            break
        for k in batch:
            if k[0] >= end_ms:
                return rows
            rows.append([k[0], k[1], k[2], k[3], k[4], k[5]])
        cur = batch[-1][0] + 1
        print(f"  fetched up to {datetime.fromtimestamp(cur/1000).strftime('%Y-%m-%d')} ({len(rows)} rows)", end="\r")
    return rows


def to_ms(date_str):
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)


def main():
    parser = argparse.ArgumentParser(description="Fetch Binance K-line data to CSV")
    parser.add_argument("--symbol",   default="BTCUSDT",    help="Trading pair (default: BTCUSDT)")
    parser.add_argument("--interval", default="1h",         help="Interval: 1m 5m 15m 1h 4h 1d 1w (default: 1h)")
    parser.add_argument("--start",    default="2017-08-17", help="Start date YYYY-MM-DD (default: 2017-08-17)")
    parser.add_argument("--end",      default="2026-01-01", help="End date YYYY-MM-DD exclusive (default: 2026-01-01)")
    parser.add_argument("--output",                         help="Output CSV path (default: <SYMBOL>_<INTERVAL>.csv)")
    parser.add_argument("--clean",    action="store_true",  help="Run cleaning after fetch (default: false)")
    args = parser.parse_args()

    base = args.output or f"{args.symbol}_{args.interval}_{args.start}_{args.end}.csv"
    print(f"Fetching {args.symbol} {args.interval}  {args.start} → {args.end}")

    rows = fetch_all(args.symbol, args.interval, to_ms(args.start), to_ms(args.end))
    print(f"\nFetched: {len(rows)} rows")

    with open(base, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"Saved: {base}")

    if args.clean:
        print("Cleaning...")
        cleaned, report = clean(rows)
        print_report(report)
        output = base.replace(".csv", "_cleaned.csv")
        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            writer.writerows(cleaned)
        print(f"Saved: {output}")


if __name__ == "__main__":
    main()
