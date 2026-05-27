"""
Build the crypto universe: top 30 USDT spot pairs by 24h quote volume.

Output: Data/universe/crypto_top30.csv with columns (symbol, quote_volume).

Source: Binance ticker/24hr REST endpoint.
"""
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "Data" / "universe"
OUT_FILE = OUT_DIR / "crypto_top30.csv"
URL = "https://api.binance.com/api/v3/ticker/24hr"

# Exclude leveraged tokens, stablecoin-on-stablecoin pairs, and other noise.
EXCLUDE_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")
EXCLUDE_BASES = {"USDC", "BUSD", "TUSD", "USDP", "DAI", "FDUSD", "USDS",
                 "USD1", "RLUSD", "EUR", "PAXG", "XUSD"}  # stablecoins + fiat/commodity-pegged


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    resp = requests.get(URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for d in data:
        sym = d["symbol"]
        if not sym.endswith("USDT"):
            continue
        if sym.endswith(EXCLUDE_SUFFIXES):
            continue
        base = sym[:-4]
        if base in EXCLUDE_BASES:
            continue
        rows.append({"symbol": sym, "quote_volume": float(d["quoteVolume"])})

    df = pd.DataFrame(rows).sort_values("quote_volume", ascending=False)
    top = df.head(30).reset_index(drop=True)
    top.to_csv(OUT_FILE, index=False)
    print(f"Saved {len(top)} symbols -> {OUT_FILE}")
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
