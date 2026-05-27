"""
Download + clean the entire universe, then build the panel parquet — one command.

    python data_scripts/download_universe.py --asset crypto --start 2018-01-01 --end 2025-01-01
    python data_scripts/download_universe.py --asset stocks --start 2010-01-01 --end 2025-01-01

Per symbol: fetch raw CSV (skipped if raw already on disk) -> clean -> write cleaned CSV.
Then: build Data/panels/<asset>.parquet from the cleaned CSVs (use --no-panel to skip).
"""
import argparse
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

import fetch
import panel

ROOT = Path(__file__).resolve().parent.parent


def universe_path(asset: str) -> Path:
    name = "sp500_top200.csv" if asset == "stocks" else "crypto_top30.csv"
    return ROOT / "Data" / "universe" / name


def download_one(asset: str, symbol: str, interval: str,
                 start: str, end: str, sleep: float = 0.0) -> bool:
    """Fetch raw (if missing) and write the cleaned CSV. Returns True on success."""
    raw = fetch.raw_path(asset, symbol, interval, start, end)
    cleaned = fetch.to_cleaned_path(raw)

    if not raw.exists():
        try:
            rows = fetch.fetch_symbol(asset, symbol, interval, start, end)
        except Exception as e:
            print(f"  [{symbol}] fetch failed: {e}")
            return False
        if not rows:
            print(f"  [{symbol}] no data returned")
            return False
        raw.parent.mkdir(parents=True, exist_ok=True)
        fetch.write_csv(raw, asset, rows)
        if sleep:
            time.sleep(sleep)  # be polite to the API only when we actually hit it

    try:
        cleaned_rows, _report = fetch.clean_rows(asset, fetch.read_csv(raw))
    except Exception as e:
        print(f"  [{symbol}] clean failed: {e}")
        return False
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    fetch.write_csv(cleaned, asset, cleaned_rows)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p.add_argument("--interval", default="1d")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--skip-existing", action="store_true", default=True,
                   help="skip symbols whose cleaned CSV already exists")
    p.add_argument("--sleep", type=float, default=0.3, help="seconds between API fetches")
    p.add_argument("--no-panel", action="store_true",
                   help="skip building the panel parquet after downloading")
    args = p.parse_args()

    symbols = pd.read_csv(universe_path(args.asset))["symbol"].tolist()
    print(f"Downloading {len(symbols)} {args.asset} symbols  {args.start} -> {args.end}")

    ok, fail = [], []
    for sym in tqdm(symbols):
        cleaned = fetch.to_cleaned_path(
            fetch.raw_path(args.asset, sym, args.interval, args.start, args.end))
        if args.skip_existing and cleaned.exists():
            ok.append(sym)
            continue
        target = ok if download_one(
            args.asset, sym, args.interval, args.start, args.end, args.sleep) else fail
        target.append(sym)

    print(f"\nDownload done. ok={len(ok)} fail={len(fail)}")
    if fail:
        print("Failed symbols:", fail)

    if not args.no_panel:
        print("\nBuilding panel...")
        panel.build_panel(args.asset, args.interval, args.start, args.end)


if __name__ == "__main__":
    main()
