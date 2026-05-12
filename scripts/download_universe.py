"""
Batch-download price data for the entire universe using the existing
fetch_stocks.py / fetch_klines.py helpers.

Usage:
    python scripts/download_universe.py --asset stocks --start 2010-01-01 --end 2025-01-01
    python scripts/download_universe.py --asset crypto --start 2018-01-01 --end 2025-01-01
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fetch_stocks  # noqa: E402
import fetch_klines  # noqa: E402


def universe_path(asset: str) -> Path:
    if asset == "stocks":
        return ROOT / "Data" / "universe" / "sp500_top200.csv"
    if asset == "crypto":
        return ROOT / "Data" / "universe" / "crypto_top30.csv"
    raise ValueError(asset)


def raw_path(asset: str, symbol: str, interval: str, start: str, end: str) -> Path:
    sub = "Stocks" if asset == "stocks" else "Crypto"
    return ROOT / "Data" / "raw" / sub / f"{symbol}_{interval}_{start}_{end}.csv"


def cleaned_path(asset: str, symbol: str, interval: str, start: str, end: str) -> Path:
    sub = "Stocks" if asset == "stocks" else "Crypto"
    return ROOT / "Data" / "cleaned" / sub / f"{symbol}_{interval}_{start}_{end}.csv"


def fetch_one_stock(symbol: str, interval: str, start: str, end: str, raw: Path) -> bool:
    try:
        rows = fetch_stocks.fetch_stock(symbol, interval, start, end)
    except Exception as e:
        print(f"  [{symbol}] fetch failed: {e}")
        return False
    raw.parent.mkdir(parents=True, exist_ok=True)
    fetch_stocks.write_csv(raw, rows)
    return True


def fetch_one_crypto(symbol: str, interval: str, start: str, end: str, raw: Path) -> bool:
    try:
        rows = fetch_klines.fetch_all(
            symbol, interval, fetch_klines.to_ms(start), fetch_klines.to_ms(end)
        )
    except Exception as e:
        print(f"  [{symbol}] fetch failed: {e}")
        return False
    if not rows:
        print(f"  [{symbol}] no data returned")
        return False
    raw.parent.mkdir(parents=True, exist_ok=True)
    fetch_klines.write_csv(raw, rows)
    return True


def clean_stock(raw: Path, cleaned: Path) -> int:
    rows = fetch_stocks.read_csv(raw)
    cleaned_rows, _report = fetch_stocks.clean(rows)
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    fetch_stocks.write_csv(cleaned, cleaned_rows)
    return len(cleaned_rows)


def clean_crypto(raw: Path, cleaned: Path) -> int:
    rows = fetch_klines.read_csv(raw)
    cleaned_rows, _report = fetch_klines.clean(rows)
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    fetch_klines.write_csv(cleaned, cleaned_rows)
    return len(cleaned_rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p.add_argument("--interval", default="1d")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--skip-existing", action="store_true", default=True)
    p.add_argument("--sleep", type=float, default=0.3, help="seconds between symbols")
    args = p.parse_args()

    uni = pd.read_csv(universe_path(args.asset))
    symbols = uni["symbol"].tolist()
    print(f"Downloading {len(symbols)} {args.asset} symbols  {args.start} -> {args.end}")

    ok, fail = [], []
    for sym in tqdm(symbols):
        raw = raw_path(args.asset, sym, args.interval, args.start, args.end)
        cln = cleaned_path(args.asset, sym, args.interval, args.start, args.end)

        if args.skip_existing and cln.exists():
            ok.append(sym)
            continue

        if not raw.exists():
            fetcher = fetch_one_stock if args.asset == "stocks" else fetch_one_crypto
            if not fetcher(sym, args.interval, args.start, args.end, raw):
                fail.append(sym)
                continue
            time.sleep(args.sleep)

        cleaner = clean_stock if args.asset == "stocks" else clean_crypto
        try:
            cleaner(raw, cln)
            ok.append(sym)
        except Exception as e:
            print(f"  [{sym}] clean failed: {e}")
            fail.append(sym)

    print(f"\nDone. ok={len(ok)} fail={len(fail)}")
    if fail:
        print("Failed symbols:", fail)


if __name__ == "__main__":
    main()
