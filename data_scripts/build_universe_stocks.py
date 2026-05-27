"""
Build the US equities universe: top 200 of the current S&P 500 by market cap.

Output: Data/universe/sp500_top200.csv with columns (symbol, sector, market_cap).

Notes:
- Uses current S&P 500 constituents from Wikipedia. This induces survivorship
  bias (we never include companies that dropped out of the index). Documented
  in the Phase 1 report.
- Market caps are fetched via yfinance fast_info; missing values are dropped.
"""
import io
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "Data" / "universe"
OUT_FILE = OUT_DIR / "sp500_top200.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = "Mozilla/5.0 (compatible; QuantMLRL/1.0; +https://github.com/)"


def fetch_sp500_constituents() -> pd.DataFrame:
    resp = requests.get(WIKI_URL, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0][["Symbol", "GICS Sector"]].rename(
        columns={"Symbol": "symbol", "GICS Sector": "sector"}
    )
    # yfinance uses '-' instead of '.' for class shares (e.g. BRK.B -> BRK-B)
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)
    return df


def fetch_market_cap(symbol: str) -> float | None:
    try:
        t = yf.Ticker(symbol)
        mc = t.fast_info.get("marketCap")
        if mc is None or mc <= 0:
            return None
        return float(mc)
    except Exception:
        return None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching S&P 500 constituent list...")
    df = fetch_sp500_constituents()
    print(f"  {len(df)} tickers")

    print("Fetching market caps (this takes a few minutes)...")
    caps = []
    for sym in tqdm(df["symbol"]):
        caps.append(fetch_market_cap(sym))
        time.sleep(0.05)
    df["market_cap"] = caps

    df = df.dropna(subset=["market_cap"]).sort_values("market_cap", ascending=False)
    top = df.head(200).reset_index(drop=True)

    top.to_csv(OUT_FILE, index=False)
    print(f"Saved {len(top)} symbols -> {OUT_FILE}")
    print(top.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
