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

Unified entry point for fetching and cleaning K-line data.

```
python fetch_klines.py (--fetch | --clean FILE [FILE ...] | --fetch --clean) [options]
```

| Argument | Default | Description |
|---|---|---|
| `--fetch` | — | Fetch K-line data from Binance |
| `--clean [FILE ...]` | — | Clean CSV file(s). Omit files when combined with `--fetch` |
| `--symbol` | required | Trading pair, e.g. `BTCUSDT` `ETHUSDT` |
| `--interval` | required | Candle interval: `1m` `5m` `15m` `1h` `4h` `1d` `1w` |
| `--start` | required | Start date `YYYY-MM-DD` |
| `--end` | required | End date `YYYY-MM-DD` (exclusive) |
| `--output` | `Data/Crypto/<SYMBOL>_<INTERVAL>_<START>_<END>.csv` | Output CSV path |

**Examples:**
```bash
# Fetch BTC 1h, full history → saved to Data/Crypto/
python fetch_klines.py --fetch --symbol BTCUSDT --interval 1h --start 2017-08-17 --end 2026-01-01

# Fetch ETH 4h, custom range
python fetch_klines.py --fetch --symbol ETHUSDT --interval 4h --start 2020-01-01 --end 2026-01-01

# Fetch and clean in one step (--clean cleans the fetched file, no file args needed)
python fetch_klines.py --fetch --clean --symbol BTCUSDT --interval 1h --start 2020-01-01 --end 2026-01-01

# Clean an existing file
python fetch_klines.py --clean Data/Crypto/BTCUSDT_1h_2017-08-17_2026-01-01.csv

# Clean multiple files
python fetch_klines.py --clean file1.csv file2.csv
```

Cleaned files are saved as `<original_name>_cleaned.csv` in the same directory.

**Cleaning steps:**
1. **Deduplicate** — remove rows with duplicate timestamps
2. **Cast types** — timestamp → `int`, OHLCV → `float`
3. **Drop invalid rows** — `high < low`, any price `<= 0`, or `volume < 0`
4. **Report gaps** — detect missing candles and print a summary

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
| `quote_volume` | float | Trade volume in quote asset (USDT) |
| `num_trades` | int | Number of trades in the candle |
| `taker_buy_volume` | float | Taker buy volume in base asset |
| `taker_buy_quote_volume` | float | Taker buy volume in quote asset (USDT) |

## Notes
- Binance BTCUSDT data starts from **2017-08-17**; earlier dates return no data.
- Gaps in early data (2017–2018) are expected due to Binance platform instability at launch.
- Zero-volume candles are kept; they represent periods with no trades but a valid price.
- Fetched data is stored under `Data/Crypto/` by default.
