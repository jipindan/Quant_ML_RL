# Quant / ML+RL

Utilities for fetching and cleaning Binance K-line (candlestick) data.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Scripts

### `fetch_klines.py`
Fetches K-line data from the Binance public API and saves to CSV.

```
python fetch_klines.py [--symbol] [--interval] [--start] [--end] [--output] [--clean]
```

| Argument | Default | Description |
|---|---|---|
| `--symbol` | `BTCUSDT` | Trading pair |
| `--interval` | `1h` | Candle interval: `1m` `5m` `15m` `1h` `4h` `1d` `1w` |
| `--start` | `2017-08-17` | Start date `YYYY-MM-DD` (Binance earliest) |
| `--end` | `2026-01-01` | End date `YYYY-MM-DD` (exclusive) |
| `--output` | `<SYMBOL>_<INTERVAL>_<START>_<END>.csv` | Output CSV path |
| `--clean` | `false` | Also run cleaning and save `<output>_cleaned.csv` |

**Examples:**
```bash
# Fetch BTC 1h, full history
python fetch_klines.py

# Fetch ETH 4h, custom range
python fetch_klines.py --symbol ETHUSDT --interval 4h --start 2020-01-01 --end 2026-01-01

# Fetch and clean in one step
python fetch_klines.py --symbol BTCUSDT --interval 1d --clean
```

---

### `clean_klines.py`
Cleans an existing K-line CSV. Can also be imported as a module by `fetch_klines.py`.

```
python clean_klines.py --input <file> [--output]
```

| Argument | Default | Description |
|---|---|---|
| `--input` | required | Input CSV path |
| `--output` | `<input>_cleaned.csv` | Output CSV path |

**Cleaning steps:**
1. **Deduplicate** — remove rows with duplicate timestamps
2. **Cast types** — timestamp → `int`, OHLCV → `float`
3. **Drop invalid rows** — `high < low`, any price `<= 0`, or `volume < 0`
4. **Report gaps** — detect missing candles and print a summary

**Example:**
```bash
python clean_klines.py --input ../BTCUSDT_1h_2017-08-17_2026-01-01.csv
```

---

## Output Format

| Column | Type | Description |
|---|---|---|
| `timestamp` | int | Unix milliseconds (UTC) |
| `open` | float | Opening price |
| `high` | float | Highest price |
| `low` | float | Lowest price |
| `close` | float | Closing price |
| `volume` | float | Trade volume in base asset |

## Notes
- Binance BTCUSDT data starts from **2017-08-17**; earlier dates return no data.
- Gaps in early data (2017–2018) are expected due to Binance platform instability at launch.
- Zero-volume candles are kept; they represent periods with no trades but a valid price.
