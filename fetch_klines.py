import argparse
import csv
import requests
from datetime import datetime
from pathlib import Path

BASE = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000
COLUMNS = [
    "timestamp", "open", "high", "low", "close",
    "volume", "quote_volume", "num_trades",
    "taker_buy_volume", "taker_buy_quote_volume",
]

DEFAULT_DATA_DIR = Path(__file__).parent / "Data" / "Crypto"


# ── Clean helpers ──────────────────────────────────────────────────────────────

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
                float(r[5]), float(r[6]),                             # volume, quote_volume
                int(r[7]),                                            # num_trades
                float(r[8]), float(r[9]),                            # taker buy volume/quote
            ])
        except (ValueError, IndexError):
            cast_error_rows.append(r)

    valid, invalid_rows = [], []
    for r in casted:
        bad = (
            r[2] < r[3]                      # high < low
            or any(r[i] <= 0 for i in range(1, 5))  # OHLC <= 0
            or r[5] < 0 or r[6] < 0          # volume / quote_volume < 0
            or r[7] < 0                      # num_trades < 0
            or r[8] < 0 or r[8] > r[5]       # taker_buy_volume out of range
            or r[9] < 0 or r[9] > r[6]       # taker_buy_quote_volume out of range
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


def print_report(report):
    for label, key in [("duplicates", "dup_rows"), ("cast errors", "cast_error_rows"), ("invalid rows", "invalid_rows"), ("zero volume", "zero_volume_rows")]:
        rows = report[key]
        print(f"  {label:<14}: {len(rows)}")
        for r in rows:
            print(f"    {r}")
    print(f"  {'original rows':<14}: {report['original']}")
    print(f"  {'final rows':<14}: {report['final']}")
    gaps = report["gaps"]
    if gaps:
        print(f"  {'gaps detected':<14}: {len(gaps)} (total missing: {sum(g[2] for g in gaps)})")
        for start, end, missing in gaps[:5]:
            print(f"    {start} → {end}  ({missing} candles missing)")
        if len(gaps) > 5:
            print(f"    ... and {len(gaps) - 5} more")
    else:
        print(f"  {'gaps detected':<14}: none")


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
            # k[6]=close_time k[11]=ignore → skip both
            rows.append([k[0], k[1], k[2], k[3], k[4], k[5], k[7], k[8], k[9], k[10]])
        cur = batch[-1][0] + 1
        print(f"  fetched up to {datetime.fromtimestamp(cur/1000).strftime('%Y-%m-%d')} ({len(rows)} rows)", end="\r")
    return rows


def to_ms(date_str):
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)


# ── Actions ────────────────────────────────────────────────────────────────────

def do_fetch(args):
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else DEFAULT_DATA_DIR / f"{args.symbol}_{args.interval}_{args.start}_{args.end}.csv"

    print(f"Fetching {args.symbol} {args.interval}  {args.start} → {args.end}")
    rows = fetch_all(args.symbol, args.interval, to_ms(args.start), to_ms(args.end))
    print(f"\nFetched: {len(rows)} rows")

    write_csv(out, rows)
    print(f"Saved:   {out}")
    return out


def do_clean(files):
    for path in map(Path, files):
        print(f"\nCleaning {path} ...")
        cleaned, report = clean(read_csv(path))
        out = path.with_stem(path.stem + "_cleaned")
        write_csv(out, cleaned)
        print(f"Saved:   {out}")
        print_report(report)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch and/or clean Binance K-line data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_klines.py --fetch --symbol BTCUSDT --interval 1h --start 2020-01-01 --end 2026-01-01
  python fetch_klines.py --fetch --clean --symbol ETHUSDT --interval 4h --start 2020-01-01 --end 2026-01-01
  python fetch_klines.py --clean Data/Crypto/BTCUSDT_1h_2020-01-01_2026-01-01.csv
        """,
    )

    parser.add_argument("--fetch", action="store_true", help="Fetch K-line data from Binance")
    parser.add_argument("--clean", nargs="*", metavar="FILE",
                        help="Clean CSV file(s). With --fetch: cleans the fetched file. Alone: requires file path(s).")
    parser.add_argument("--symbol",   help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--interval", help="Interval: 1m 5m 15m 1h 4h 1d 1w")
    parser.add_argument("--start",    help="Start date YYYY-MM-DD")
    parser.add_argument("--end",      help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--output",   help="Output CSV path (default: Data/Crypto/<SYMBOL>_<INTERVAL>_<START>_<END>.csv)")

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
