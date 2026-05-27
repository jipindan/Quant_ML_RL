"""
Load cleaned per-symbol CSVs into a single long-format panel parquet:
    (date, symbol, open, high, low, close, [adj_close,] volume, [crypto extras])

Date is a normalized UTC date (no time) for daily data.

NOTE: _read_one uses .dt.normalize(), which truncates intraday times. This is
correct for daily bars but would collapse all 24 hourly rows of a day onto one
date for 1h data — handle before building intraday panels (tracked in Plan.md).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
CLEAN_STOCKS = ROOT / "Data" / "cleaned" / "Stocks"
CLEAN_CRYPTO = ROOT / "Data" / "cleaned" / "Crypto"
UNIVERSE_DIR = ROOT / "Data" / "universe"
PANEL_DIR = ROOT / "Data" / "panels"


def _read_one(path: Path, symbol: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["symbol"] = symbol
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.normalize()
    return df.drop(columns=["timestamp"])


def _files_for(universe: pd.DataFrame, root: Path, interval: str,
               start: str, end: str) -> list[tuple[Path, str]]:
    out = []
    for sym in universe["symbol"]:
        p = root / f"{sym}_{interval}_{start}_{end}.csv"
        if p.exists():
            out.append((p, sym))
    return out


def build_panel(asset: str, interval: str, start: str, end: str,
                min_coverage: float = 0.8) -> pd.DataFrame:
    """
    asset: 'stocks' | 'crypto'
    min_coverage: drop symbols whose row count is < min_coverage * median row count.
    """
    if asset == "stocks":
        uni = pd.read_csv(UNIVERSE_DIR / "sp500_top200.csv")
        root = CLEAN_STOCKS
    elif asset == "crypto":
        uni = pd.read_csv(UNIVERSE_DIR / "crypto_top30.csv")
        root = CLEAN_CRYPTO
    else:
        raise ValueError(asset)

    files = _files_for(uni, root, interval, start, end)
    if not files:
        raise FileNotFoundError(f"No cleaned files found in {root} for {start}-{end}")

    print(f"Loading {len(files)} {asset} files...")
    frames = [_read_one(p, s) for p, s in tqdm(files)]
    panel = pd.concat(frames, ignore_index=True)

    counts = panel.groupby("symbol").size()
    keep = counts[counts >= min_coverage * counts.median()].index
    dropped = sorted(set(panel["symbol"]) - set(keep))
    if dropped:
        print(f"Dropping {len(dropped)} low-coverage symbols: {dropped[:10]}{'...' if len(dropped)>10 else ''}")
    panel = panel[panel["symbol"].isin(keep)].copy()

    # Merge sector for stocks
    if asset == "stocks":
        panel = panel.merge(uni[["symbol", "sector"]], on="symbol", how="left")

    panel = panel.sort_values(["symbol", "date"]).reset_index(drop=True)

    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    out = PANEL_DIR / f"{asset}.parquet"
    panel.to_parquet(out, index=False)
    print(f"Saved panel: {out}  rows={len(panel):,}  symbols={panel['symbol'].nunique()}  "
          f"dates={panel['date'].nunique()}")
    return panel


def load_panel(asset: str) -> pd.DataFrame:
    return pd.read_parquet(PANEL_DIR / f"{asset}.parquet")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Build a long-format panel parquet from cleaned CSVs")
    p.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p.add_argument("--interval", default="1d")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--min-coverage", type=float, default=0.8)
    args = p.parse_args()

    build_panel(args.asset, args.interval, args.start, args.end, args.min_coverage)
