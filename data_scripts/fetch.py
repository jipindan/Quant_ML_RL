"""
Unified fetch + clean for crypto (Binance) and stocks (yfinance).

CLI:
    python data_scripts/fetch.py --source crypto --fetch --symbol BTCUSDT --interval 1d --start 2018-01-01 --end 2025-01-01
    python data_scripts/fetch.py --source stocks --fetch --clean --symbol SPY --interval 1d --start 2010-01-01 --end 2025-01-01
    python data_scripts/fetch.py --source crypto --clean Data/raw/Crypto/BTCUSDT_1d_2018-01-01_2025-01-01.csv

Importable API (used by download_universe.py):
    fetch_symbol(source, symbol, interval, start, end) -> rows
    clean_rows(source, rows)                            -> (cleaned_rows, report)
    read_csv(path) / write_csv(path, source, rows)
    raw_path(source, symbol, interval, start, end) / to_cleaned_path(path)
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

COLUMNS = {
    "crypto": ["timestamp", "open", "high", "low", "close", "volume",
               "quote_volume", "num_trades", "taker_buy_volume", "taker_buy_quote_volume"],
    "stocks": ["timestamp", "open", "high", "low", "close", "adj_close", "volume"],
}
RAW_SUBDIR = {"crypto": "Crypto", "stocks": "Stocks"}

BINANCE = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000


# ── CSV io ───────────────────────────────────────────────────────────────────

def read_csv(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        return list(reader)


def write_csv(path, source, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS[source])
        writer.writerows(rows)


def raw_path(source, symbol, interval, start, end):
    return ROOT / "Data" / "raw" / RAW_SUBDIR[source] / f"{symbol}_{interval}_{start}_{end}.csv"


def to_cleaned_path(path):
    """Map Data/raw/.../file.csv -> Data/cleaned/.../file.csv"""
    parts = list(path.parts)
    try:
        parts[parts.index("raw")] = "cleaned"
        return Path(*parts)
    except ValueError:
        return path.parent / path.name  # fallback: same dir, same name


# ── Fetch ──────────────────────────────────────────────────────────────────

def to_ms(date_str):
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)


def _fetch_crypto(symbol, interval, start, end):
    start_ms, end_ms = to_ms(start), to_ms(end)
    rows, cur = [], start_ms
    while cur < end_ms:
        resp = requests.get(BINANCE, params={
            "symbol": symbol, "interval": interval,
            "startTime": cur, "limit": MAX_LIMIT,
        }, timeout=10)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for k in batch:
            if k[0] >= end_ms:
                return rows
            # k[6]=close_time k[11]=ignore -> skip both
            rows.append([k[0], k[1], k[2], k[3], k[4], k[5], k[7], k[8], k[9], k[10]])
        cur = batch[-1][0] + 1
        print(f"  fetched up to {datetime.fromtimestamp(cur/1000).strftime('%Y-%m-%d')} "
              f"({len(rows)} rows)", end="\r")
    return rows


def _fetch_stocks(symbol, interval, start, end):
    import pandas as pd
    import yfinance as yf

    df = yf.download(
        symbol, start=start, end=end, interval=interval,
        auto_adjust=False, progress=False, actions=False,
    )
    if df.empty:
        raise ValueError(f"No data returned for {symbol}. Check symbol and date range.")

    # Flatten MultiIndex columns (yfinance >= 0.2.x with single ticker)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    rows = []
    for ts, row in df.iterrows():
        rows.append([
            int(ts.timestamp() * 1000),
            row["Open"], row["High"], row["Low"], row["Close"],
            row["Adj Close"],
            int(row["Volume"]),
        ])
    return rows


def fetch_symbol(source, symbol, interval, start, end):
    if source == "crypto":
        return _fetch_crypto(symbol, interval, start, end)
    if source == "stocks":
        return _fetch_stocks(symbol, interval, start, end)
    raise ValueError(source)


# ── Clean ──────────────────────────────────────────────────────────────────

def detect_gaps(rows):
    if len(rows) < 2:
        return []
    interval_ms = rows[1][0] - rows[0][0]
    gaps = []
    for i in range(1, len(rows)):
        diff = rows[i][0] - rows[i - 1][0]
        if diff > interval_ms:
            gaps.append((rows[i - 1][0], rows[i][0], int(diff // interval_ms - 1)))
    return gaps


def _dedup(rows):
    seen = set()
    deduped, dup_rows = [], []
    for r in rows:
        (deduped if r[0] not in seen else dup_rows).append(r)
        seen.add(r[0])
    return deduped, dup_rows


def _clean_crypto(rows):
    original = len(rows)
    deduped, dup_rows = _dedup(rows)

    casted, cast_error_rows = [], []
    for r in deduped:
        try:
            casted.append([
                int(r[0]),
                float(r[1]), float(r[2]), float(r[3]), float(r[4]),  # OHLC
                float(r[5]), float(r[6]),                             # volume, quote_volume
                int(r[7]),                                            # num_trades
                float(r[8]), float(r[9]),                            # taker buy volume/quote
            ])
        except (ValueError, IndexError):
            cast_error_rows.append(r)

    valid, invalid_rows = [], []
    for r in casted:
        bad = (
            r[2] < r[3]                              # high < low
            or any(r[i] <= 0 for i in range(1, 5))   # OHLC <= 0
            or r[5] < 0 or r[6] < 0                   # volume / quote_volume < 0
            or r[7] < 0                               # num_trades < 0
            or r[8] < 0 or r[8] > r[5]                # taker_buy_volume out of range
            or r[9] < 0 or r[9] > r[6]                # taker_buy_quote_volume out of range
        )
        (invalid_rows if bad else valid).append(r)

    zero_volume_rows = [r for r in valid if r[5] == 0]

    return valid, {
        "original": original,
        "dup_rows": dup_rows,
        "cast_error_rows": cast_error_rows,
        "invalid_rows": invalid_rows,
        "zero_volume_rows": zero_volume_rows,
        "final": len(valid),
        "gaps": detect_gaps(valid),
    }


def _clean_stocks(rows):
    original = len(rows)
    deduped, dup_rows = _dedup(rows)

    casted, cast_error_rows = [], []
    for r in deduped:
        try:
            casted.append([
                int(r[0]),
                float(r[1]), float(r[2]), float(r[3]), float(r[4]),  # OHLC
                float(r[5]),                                           # adj_close
                int(r[6]),                                             # volume (shares)
            ])
        except (ValueError, IndexError):
            cast_error_rows.append(r)

    valid, invalid_rows = [], []
    for r in casted:
        bad = (
            r[2] < r[3]                              # high < low
            or any(r[i] <= 0 for i in range(1, 6))   # OHLC + adj_close <= 0
            or r[6] < 0                               # volume < 0
        )
        (invalid_rows if bad else valid).append(r)

    zero_volume_rows = [r for r in valid if r[6] == 0]

    return valid, {
        "original": original,
        "dup_rows": dup_rows,
        "cast_error_rows": cast_error_rows,
        "invalid_rows": invalid_rows,
        "zero_volume_rows": zero_volume_rows,
        "final": len(valid),
        # no gap detection for stocks: weekends/holidays are expected gaps
    }


def clean_rows(source, rows):
    if source == "crypto":
        return _clean_crypto(rows)
    if source == "stocks":
        return _clean_stocks(rows)
    raise ValueError(source)


def print_report(report):
    for label, key in [("duplicates", "dup_rows"), ("cast errors", "cast_error_rows"),
                       ("invalid rows", "invalid_rows"), ("zero volume", "zero_volume_rows")]:
        rows = report[key]
        print(f"  {label:<14}: {len(rows)}")
        for r in rows:
            print(f"    {r}")
    print(f"  {'original rows':<14}: {report['original']}")
    print(f"  {'final rows':<14}: {report['final']}")
    if "gaps" in report:
        gaps = report["gaps"]
        if gaps:
            print(f"  {'gaps detected':<14}: {len(gaps)} (total missing: {sum(g[2] for g in gaps)})")
            for start, end, missing in gaps[:5]:
                print(f"    {start} → {end}  ({missing} candles missing)")
            if len(gaps) > 5:
                print(f"    ... and {len(gaps) - 5} more")
        else:
            print(f"  {'gaps detected':<14}: none")


# ── CLI actions ──────────────────────────────────────────────────────────────

def do_fetch(args):
    out = Path(args.output) if args.output else raw_path(
        args.source, args.symbol, args.interval, args.start, args.end)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {args.symbol} {args.interval}  {args.start} → {args.end}")
    rows = fetch_symbol(args.source, args.symbol, args.interval, args.start, args.end)
    print(f"\nFetched: {len(rows)} rows")

    write_csv(out, args.source, rows)
    print(f"Saved:   {out}")
    return out


def do_clean(source, files):
    for path in map(Path, files):
        print(f"\nCleaning {path} ...")
        cleaned, report = clean_rows(source, read_csv(path))
        out = to_cleaned_path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(out, source, cleaned)
        print(f"Saved:   {out}")
        print_report(report)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch and/or clean price data for crypto (Binance) or stocks (yfinance)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python data_scripts/fetch.py --source crypto --fetch --symbol BTCUSDT --interval 1d --start 2018-01-01 --end 2025-01-01
  python data_scripts/fetch.py --source crypto --fetch --clean --symbol ETHUSDT --interval 1h --start 2020-01-01 --end 2026-01-01
  python data_scripts/fetch.py --source stocks --fetch --clean --symbol AAPL --interval 1d --start 2020-01-01 --end 2026-01-01
  python data_scripts/fetch.py --source stocks --clean Data/raw/Stocks/AAPL_1d_2020-01-01_2026-01-01.csv

Crypto intervals: 1m 5m 15m 1h 4h 1d 1w
Stock intervals:  1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo  (intraday < 1d: last 60 days only)
HK stocks use .HK suffix:  0700.HK (Tencent)  9988.HK (Alibaba)
        """,
    )

    parser.add_argument("--source", choices=["crypto", "stocks"], required=True,
                        help="Data source")
    parser.add_argument("--fetch", action="store_true", help="Fetch data from source")
    parser.add_argument("--clean", nargs="*", metavar="FILE",
                        help="Clean CSV file(s). With --fetch: cleans the fetched file. Alone: requires file path(s).")
    parser.add_argument("--symbol",   help="Symbol, e.g. BTCUSDT (crypto) or AAPL / 0700.HK (stocks)")
    parser.add_argument("--interval", help="Bar interval")
    parser.add_argument("--start",    help="Start date YYYY-MM-DD")
    parser.add_argument("--end",      help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--output",   help="Output CSV path (default: Data/raw/<Type>/<SYMBOL>_<INTERVAL>_<START>_<END>.csv)")

    args = parser.parse_args()

    if not args.fetch and args.clean is None:
        parser.error("At least one of --fetch or --clean is required.")
    if args.clean is not None and not args.fetch and not args.clean:
        parser.error("--clean requires file path(s) when used without --fetch.")
    if args.fetch:
        for arg in ("symbol", "interval", "start", "end"):
            if not getattr(args, arg):
                parser.error(f"--fetch requires --{arg}")

    fetched_path = do_fetch(args) if args.fetch else None

    if args.clean is not None:
        do_clean(args.source, [fetched_path] if args.fetch else args.clean)


if __name__ == "__main__":
    main()
