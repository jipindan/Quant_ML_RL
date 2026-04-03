import argparse
import csv
from collections import Counter

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def clean(rows):
    """
    Input/output: list of lists [timestamp, open, high, low, close, volume]
    Steps: deduplicate → cast types → drop invalid rows
    Returns (cleaned_rows, report_dict)
    """
    original = len(rows)

    # 1. Deduplicate by timestamp
    seen = set()
    deduped = []
    dup_rows = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            deduped.append(r)
        else:
            dup_rows.append(r)

    # 2. Cast types
    casted = []
    cast_error_rows = []
    for r in deduped:
        try:
            casted.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        except (ValueError, IndexError):
            cast_error_rows.append(r)

    # 3. Drop invalid rows (high < low, or any price <= 0)
    valid = []
    invalid_rows = []
    for r in casted:
        if r[2] < r[3] or any(r[i] <= 0 for i in range(1, 5)) or r[5] < 0:
            invalid_rows.append(r)
        else:
            valid.append(r)

    # 4. Detect gaps (missing candles)
    gaps = detect_gaps(valid)

    report = {
        "original": original,
        "dup_rows": dup_rows,
        "cast_error_rows": cast_error_rows,
        "invalid_rows": invalid_rows,
        "final": len(valid),
        "gaps": gaps,
    }
    return valid, report


def detect_gaps(rows):
    """Infer expected interval from first two rows and find missing candles."""
    if len(rows) < 2:
        return []
    interval_ms = rows[1][0] - rows[0][0]
    gaps = []
    for i in range(1, len(rows)):
        diff = rows[i][0] - rows[i - 1][0]
        if diff > interval_ms:
            missing = diff // interval_ms - 1
            gaps.append((rows[i - 1][0], rows[i][0], int(missing)))
    return gaps


def print_report(report):
    print(f"  original rows : {report['original']}")
    print(f"  duplicates    : {len(report['dup_rows'])}")
    for r in report["dup_rows"]:
        print(f"    {r}")
    print(f"  cast errors   : {len(report['cast_error_rows'])}")
    for r in report["cast_error_rows"]:
        print(f"    {r}")
    print(f"  invalid rows  : {len(report['invalid_rows'])}")
    for r in report["invalid_rows"]:
        print(f"    {r}")
    print(f"  final rows    : {report['final']}")
    if report["gaps"]:
        print(f"  gaps detected : {len(report['gaps'])} (total missing: {sum(g[2] for g in report['gaps'])})")
        for start, end, missing in report["gaps"][:5]:
            print(f"    {start} → {end}  ({missing} candles missing)")
        if len(report["gaps"]) > 5:
            print(f"    ... and {len(report['gaps']) - 5} more")
    else:
        print("  gaps detected : none")


def read_csv(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        return [row for row in reader]


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Clean Binance K-line CSV")
    parser.add_argument("--input",  required=True, help="Input CSV path")
    parser.add_argument("--output",               help="Output CSV path (default: <input>_cleaned.csv)")
    args = parser.parse_args()

    output = args.output or args.input.replace(".csv", "_cleaned.csv")

    rows = read_csv(args.input)
    cleaned, report = clean(rows)
    write_csv(output, cleaned)
    print(f"Saved: {output}")
    print_report(report)


if __name__ == "__main__":
    main()
