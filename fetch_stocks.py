import argparse
import csv
import pandas as pd
import yfinance as yf
from pathlib import Path

COLUMNS = ["timestamp", "open", "high", "low", "close", "adj_close", "volume"]

DEFAULT_RAW_DIR = Path(__file__).parent / "Data" / "raw" / "Stocks"


# ── Clean helpers ──────────────────────────────────────────────────────────────

def clean(rows):
    original = len(rows)

    seen = set()
    deduped, dup_rows = [], []
    for r in rows:
        (deduped if r[0] not in seen else dup_rows).append(r)
        seen.add(r[0])

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
            r[2] < r[3]                             # high < low
            or any(r[i] <= 0 for i in range(1, 6))  # OHLC + adj_close <= 0
            or r[6] < 0                             # volume < 0
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
    }


def print_report(report):
    for label, key in [("duplicates", "dup_rows"), ("cast errors", "cast_error_rows"), ("invalid rows", "invalid_rows"), ("zero volume", "zero_volume_rows")]:
        rows = report[key]
        print(f"  {label:<14}: {len(rows)}")
        for r in rows:
            print(f"    {r}")
    print(f"  {'original rows':<14}: {report['original']}")
    print(f"  {'final rows':<14}: {report['final']}")
    # Note: gap detection is omitted for stocks — weekends/holidays create
    # natural gaps that are not data errors.


def read_csv(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        return list(reader)


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def fetch_stock(symbol, interval, start, end):
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


# ── Actions ────────────────────────────────────────────────────────────────────

def to_cleaned_path(path):
    """Map Data/raw/.../file.csv → Data/cleaned/.../file.csv"""
    parts = list(path.parts)
    try:
        parts[parts.index("raw")] = "cleaned"
        return Path(*parts)
    except ValueError:
        return path.parent / path.name  # fallback: same dir, same name


def do_fetch(args):
    DEFAULT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else DEFAULT_RAW_DIR / f"{args.symbol}_{args.interval}_{args.start}_{args.end}.csv"

    print(f"Fetching {args.symbol} {args.interval}  {args.start} → {args.end}")
    rows = fetch_stock(args.symbol, args.interval, args.start, args.end)
    print(f"Fetched: {len(rows)} rows")

    write_csv(out, rows)
    print(f"Saved:   {out}")
    return out


def do_clean(files):
    for path in map(Path, files):
        print(f"\nCleaning {path} ...")
        cleaned, report = clean(read_csv(path))
        out = to_cleaned_path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_csv(out, cleaned)
        print(f"Saved:   {out}")
        print_report(report)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch and/or clean stock price data via yfinance (US, HK)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_stocks.py --fetch --symbol AAPL --interval 1d --start 2020-01-01 --end 2026-01-01
  python fetch_stocks.py --fetch --symbol 0700.HK --interval 1d --start 2020-01-01 --end 2026-01-01
  python fetch_stocks.py --fetch --clean --symbol TSLA --interval 1d --start 2020-01-01 --end 2026-01-01
  python fetch_stocks.py --clean Data/Stocks/AAPL_1d_2020-01-01_2026-01-01.csv

Intervals: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo
  Note: intraday intervals (< 1d) only available for the last 60 days.

HK stocks use .HK suffix:  0700.HK (Tencent)  9988.HK (Alibaba)
        """,
    )

    parser.add_argument("--fetch", action="store_true", help="Fetch stock data via yfinance")
    parser.add_argument("--clean", nargs="*", metavar="FILE",
                        help="Clean CSV file(s). With --fetch: cleans the fetched file. Alone: requires file path(s).")
    parser.add_argument("--symbol",   help="Ticker symbol, e.g. AAPL or 0700.HK")
    parser.add_argument("--interval", help="Interval: 1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo")
    parser.add_argument("--start",    help="Start date YYYY-MM-DD")
    parser.add_argument("--end",      help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--output",   help="Output CSV path (default: Data/raw/Stocks/<SYMBOL>_<INTERVAL>_<START>_<END>.csv)")

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
        do_clean([fetched_path] if args.fetch else args.clean)


if __name__ == "__main__":
    main()
