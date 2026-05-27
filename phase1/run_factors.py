"""
Phase 1 — factor computation.

Load the panel parquet (built by data_scripts/download_universe.py) plus the
benchmark CSV, compute the full factor catalog, and save the factor matrix to
Data/factors/<asset>.parquet — the input to run_ic.py and to Phase 2.

    python phase1/run_factors.py --asset crypto --start 2018-01-01 --end 2025-01-01
    python phase1/run_factors.py --asset stocks --start 2010-01-01 --end 2025-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_scripts"))

import panel as dpanel                       # noqa: E402  (data_scripts/panel.py)
from factors import build as b               # noqa: E402
from factors.catalog import catalog_for      # noqa: E402

FACTOR_DIR = ROOT / "Data" / "factors"


def load_bench(asset: str, bench_symbol: str | None, interval: str,
               start: str, end: str) -> pd.DataFrame:
    """Load the benchmark cleaned CSV (one symbol) into a bench dataframe."""
    sub = "Stocks" if asset == "stocks" else "Crypto"
    sym = bench_symbol or ("SPY" if asset == "stocks" else "BTCUSDT")
    p = ROOT / "Data" / "cleaned" / sub / f"{sym}_{interval}_{start}_{end}.csv"

    if not p.exists():
        raise FileNotFoundError(
            f"Benchmark file missing: {p}\n"
            f"Download it first, e.g.:\n"
            f"  python data_scripts/fetch.py --source {asset} --fetch --clean "
            f"--symbol {sym} --interval {interval} --start {start} --end {end}"
        )
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.normalize()
    return b.build_benchmark(df, asset)


def build_factor_matrix(panel: pd.DataFrame, asset: str,
                        bench: pd.DataFrame | None) -> pd.DataFrame:
    factors = catalog_for(asset)
    print(f"Computing {len(factors)} factors...")
    # Keep panel's (date, symbol) columns verbatim — including the tz-aware date
    # dtype — so the saved factor parquet stays row-aligned with the panel.
    out = panel[["date", "symbol"]].reset_index(drop=True).copy()
    for f in factors:
        try:
            vals = f.fn(panel, asset, bench)
            if isinstance(vals, np.ndarray):
                out[f.name] = vals
            elif isinstance(vals, pd.Series):
                out[f.name] = vals.values
            else:
                out[f.name] = np.asarray(vals)
            print(f"  {f.name}: ok ({out[f.name].notna().sum():,} non-null)")
        except Exception as e:
            print(f"  {f.name}: FAILED -- {e}")
            out[f.name] = np.nan
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p.add_argument("--interval", default="1d")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--bench", default=None,
                   help="Benchmark symbol (default: SPY for stocks, BTCUSDT for crypto)")
    args = p.parse_args()

    panel = dpanel.load_panel(args.asset)
    print(f"Loaded panel: rows={len(panel):,}  symbols={panel['symbol'].nunique()}  "
          f"dates={panel['date'].nunique()}")

    bench = load_bench(args.asset, args.bench, args.interval, args.start, args.end)

    fac = build_factor_matrix(panel, args.asset, bench)

    FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    out = FACTOR_DIR / f"{args.asset}.parquet"
    fac.to_parquet(out, index=False)
    print(f"Saved factors: {out}  shape={fac.shape}")


if __name__ == "__main__":
    main()
