# Quant / ML+RL

Utilities for fetching and cleaning market data (crypto via Binance, equities via yfinance).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Scripts

### `fetch_klines.py` — Crypto (Binance)

```
python fetch_klines.py (--fetch | --clean FILE [FILE ...] | --fetch --clean) [options]
```

| Argument | Default | Description |
|---|---|---|
| `--fetch` | — | Fetch K-line data from Binance |
| `--clean [FILE ...]` | — | Clean CSV file(s). With `--fetch`: cleans the fetched file |
| `--symbol` | required | Trading pair, e.g. `BTCUSDT` `ETHUSDT` |
| `--interval` | required | `1m` `5m` `15m` `1h` `4h` `1d` `1w` |
| `--start` | required | Start date `YYYY-MM-DD` |
| `--end` | required | End date `YYYY-MM-DD` (exclusive) |
| `--output` | `Data/Crypto/<SYMBOL>_<INTERVAL>_<START>_<END>.csv` | Output path |

```bash
python fetch_klines.py --fetch --symbol BTCUSDT --interval 1d --start 2020-01-01 --end 2026-01-01
python fetch_klines.py --fetch --clean --symbol ETHUSDT --interval 1h --start 2020-01-01 --end 2026-01-01
python fetch_klines.py --clean Data/Crypto/BTCUSDT_1d_2020-01-01_2026-01-01.csv
```

---

### `fetch_stocks.py` — Equities (US / HK)

```
python fetch_stocks.py (--fetch | --clean FILE [FILE ...] | --fetch --clean) [options]
```

| Argument | Default | Description |
|---|---|---|
| `--fetch` | — | Fetch stock data via yfinance |
| `--clean [FILE ...]` | — | Clean CSV file(s). With `--fetch`: cleans the fetched file |
| `--symbol` | required | Ticker, e.g. `AAPL` (US) or `0700.HK` (HK) |
| `--interval` | required | `1m` `2m` `5m` `15m` `30m` `60m` `90m` `1h` `1d` `5d` `1wk` `1mo` `3mo` |
| `--start` | required | Start date `YYYY-MM-DD` |
| `--end` | required | End date `YYYY-MM-DD` (exclusive) |
| `--output` | `Data/Stocks/<SYMBOL>_<INTERVAL>_<START>_<END>.csv` | Output path |

```bash
python fetch_stocks.py --fetch --symbol AAPL --interval 1d --start 2020-01-01 --end 2026-01-01
python fetch_stocks.py --fetch --clean --symbol 0700.HK --interval 1d --start 2020-01-01 --end 2026-01-01
python fetch_stocks.py --clean Data/raw/Stocks/AAPL_1d_2020-01-01_2026-01-01.csv
```

> Intraday intervals (`< 1d`) are only available for the last 60 days.

---

## Output Format

### Crypto (`fetch_klines.py`)

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

### Equities (`fetch_stocks.py`)

| Column | Type | Description |
|---|---|---|
| `timestamp` | int | Unix milliseconds (UTC) |
| `open` | float | Opening price |
| `high` | float | Highest price |
| `low` | float | Lowest price |
| `close` | float | Unadjusted closing price |
| `adj_close` | float | Split/dividend-adjusted closing price |
| `volume` | int | Trade volume in shares |

---

## Cleaning Steps

Both scripts apply the same pipeline:

1. **Deduplicate** — remove rows with duplicate timestamps
2. **Cast types** — `timestamp` → `int`, `num_trades` / `volume` (stocks) → `int`, others → `float`
3. **Drop invalid rows** — `high < low`, any OHLC `<= 0`, out-of-range values
4. **Track zero-volume rows** — kept in output, reported separately
5. **Report gaps** — crypto only; stocks omit this (weekends/holidays are expected gaps)

Raw files are saved under `Data/raw/<type>/`, cleaned files under `Data/cleaned/<type>/` with the same filename.

---

## Directory Structure

```
Data/
  raw/
    Crypto/    ← fetch_klines.py --fetch
    Stocks/    ← fetch_stocks.py --fetch
  cleaned/
    Crypto/    ← fetch_klines.py --clean
    Stocks/    ← fetch_stocks.py --clean
```

## Notes
- Binance BTCUSDT data starts from **2017-08-17**.
- Gaps in early crypto data (2017–2018) are expected due to Binance instability at launch.
- HK tickers use `.HK` suffix: `0700.HK` (Tencent), `9988.HK` (Alibaba), `1299.HK` (AIA).
- `adj_close` should be used for equity return calculation and backtesting; `close` is kept for reference.
