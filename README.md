# Quant / ML+RL

End-to-end pipeline for an ML + RL trading research project.

- **Phase 0** — data ingestion: fetch & clean OHLCV for US equities (yfinance) and crypto (Binance).
- **Phase 1** — factor engineering: build cross-sectional factor library, screen by IC/ICIR + correlation pruning, output a panel of surviving factors per asset class.
- Phases 2–5 (ML stacking, backtester, RL agents, comparative analysis) live in the project plan but are not yet implemented.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Windows: set `PYTHONIOENCODING=utf-8` before running any script (the fetchers print `→` which fails on cp1252 consoles).

---

# Phase 0 — Data ingestion

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

## Notes
- Binance BTCUSDT data starts from **2017-08-17**.
- Gaps in early crypto data (2017–2018) are expected due to Binance instability at launch.
- HK tickers use `.HK` suffix: `0700.HK` (Tencent), `9988.HK` (Alibaba), `1299.HK` (AIA).
- `adj_close` should be used for equity return calculation and backtesting; `close` is kept for reference.

---

# Phase 1 — Factor engineering

Build candidate factors → screen by Information Coefficient (IC) / ICIR with sign stability → prune correlated survivors → write a markdown report.

## Modules

```
factors/
  build.py     factor formulas (causal rolling ops, groupby symbol)
  catalog.py   registry mapping name → (callable, category, hypothesis)
  ic.py        cross-sectional Spearman IC per date, ICIR, rolling sign-stability
  screen.py    |ICIR_ann|≥0.5 ∧ sign_stability≥0.70  then  |ρ|>0.8 corr pruning
  io.py        cleaned CSVs → long-format parquet panel (date, symbol, OHLCV [+sector])
scripts/
  build_universe_stocks.py   top 200 S&P 500 by market cap (yfinance fast_info)
  build_universe_crypto.py   top 30 Binance USDT pairs by 24h quote volume
  download_universe.py       batch wrapper around fetch_stocks/fetch_klines
  run_phase1.py              orchestrator: panel → factors → IC → screen → report
```

## End-to-end run

### Stocks (S&P 500 top 200, 2010-2025)

```bash
# 1. Universe (~5 min: 503 yfinance calls for market caps)
python scripts/build_universe_stocks.py

# 2. Download all symbols (~2 min)
python scripts/download_universe.py --asset stocks --start 2010-01-01 --end 2025-01-01

# 3. Benchmark (used for rs_vs_spy / beta_60 / idio_vol_60)
python fetch_stocks.py --fetch --clean --symbol SPY --interval 1d --start 2010-01-01 --end 2025-01-01

# 4. Phase 1 pipeline
python scripts/run_phase1.py --asset stocks --start 2010-01-01 --end 2025-01-01
```

### Crypto (Binance top 30 by 24h vol, 2018-2025)

```bash
python scripts/build_universe_crypto.py
python scripts/download_universe.py --asset crypto --start 2018-01-01 --end 2025-01-01
# BTCUSDT downloads as part of the universe → also serves as benchmark
python scripts/run_phase1.py --asset crypto --start 2018-01-01 --end 2025-01-01
```

## Factor categories

| Category | Stocks | Crypto-only extras |
|---|---|---|
| Momentum | `ret_{5,10,20,60}`, `mom_accel` | — |
| Mean reversion | `dist_ma_{20,50}`, `bb_pos_20`, `rsi_14` | — |
| Volume | `vol_ratio_20`, `obv_slope_20`, `vol_price_corr_20`, `dollar_vol_z_60` | `num_trades_z_60` |
| Volatility | `rvol_{20,60}`, `vol_of_vol_60`, `hl_range_20`, `garman_klass_20` | — |
| Microstructure | `amihud_illiq_20`, `hl_spread_proxy_20` | `taker_buy_ratio_20`, `taker_imbalance_20`, `quote_vol_per_trade_z_20` |
| Cross-sectional | `rs_vs_spy_{20,60}`, `beta_60`, `idio_vol_60`, `rank_sector_mom20` | `rs_vs_btc_60`, `beta_btc_60`, `idio_vol_btc_60` |

Every factor is a causal rolling transform `groupby('symbol')`. There is no look-ahead: factor(t) sees data up to and including `t`, and the IC pairs it with the forward 5-day log return `ln(close[t+5]/close[t])`.

## Methodology

- **Forward return target**: 5-day log return of `adj_close` (stocks) / `close` (crypto).
- **Daily IC**: per date, Spearman rank correlation between factor and forward return across the cross-section (min 10 valid assets).
- **ICIR** = mean(IC) / std(IC). `icir_ann = icir × √252`.
- **Screening criteria** (configurable in `factors/screen.py`):
  - IC filter: `|ICIR_ann| ≥ 0.5` AND `sign_stability ≥ 0.70` (fraction of rolling 12-month windows where mean(IC) shares the overall sign).
  - Correlation pruning: greedy — within survivors, if `|Spearman ρ| > 0.8`, drop the factor with lower `|ICIR_ann|`.

## Outputs

Each pipeline run writes:

| Path | Contents |
|---|---|
| `Data/panels/{stocks,crypto}.parquet` | Long-format OHLCV panel `(date, symbol, …)` with sector merged for stocks. |
| `Data/factors/{stocks,crypto}.parquet` | Factor matrix `(date, symbol, f1, f2, …)`. **This is the Phase 2 input.** |
| `Data/reports/{stocks,crypto}_factor_report.md` | Markdown report: IC/ICIR table, survivors, plots. |
| `Data/reports/{stocks,crypto}_factor_summary.csv` | Same table in CSV form. |
| `Data/reports/{stocks,crypto}_corr.png` | Correlation heatmap of survivors. |
| `Data/reports/{stocks,crypto}_rolling_ic.png` | 3-month rolling mean IC for top factors. |

## Results snapshot

**Stocks** (199 symbols, 2010–2024): 9 survivors. Strongest: `amihud_illiq_20` (+, ICIR_ann ≈ 2.05), `ret_5` (-, 1-week reversal), `dist_ma_20` (-), `hl_spread_proxy_20` (+), `vol_of_vol_60` (+).

**Crypto** (16 symbols after coverage filter, 2018–2024): 9 survivors. Strongest: `idio_vol_btc_60` (-, low-vol anomaly, ICIR_ann ≈ -3.23), `garman_klass_20` (-), `taker_buy_ratio_20` (+, order-flow), `amihud_illiq_20` (- — **sign-flipped vs equities**).

## Caveats

- **Survivorship bias (stocks):** the universe is the *current* S&P 500 top-200 by market cap. Companies that dropped out are not included. Documented in the stocks report; needs the same call-out in any cross-asset comparison.
- **Coverage filter (crypto):** symbols with row count below 0.8× median are dropped. Recent listings (CHIP / ONDO / SPK / SAHARA / SUI / TAO / TON / PENDLE / ENA / PEPE / LUNC / PENGU / RAD / SAGA) drop out at the panel-build step, leaving 16 of the 30 top-volume pairs.
- **Walk-forward / out-of-sample:** Phase 1 uses the full date range for factor screening. The Phase 2 ML stacking step is responsible for purged walk-forward validation; do not re-tune screening criteria on test data.

---

# Directory structure (full)

```
fetch_stocks.py, fetch_klines.py         data ingestion
factors/                                  factor library
scripts/                                  orchestrators / batch wrappers
Data/                                     (gitignored)
  raw/{Stocks,Crypto}/<sym>_<ivl>_<start>_<end>.csv
  cleaned/{Stocks,Crypto}/...             same shape, post-cleaning
  universe/                                sp500_top200.csv, crypto_top30.csv
  panels/                                  stocks.parquet, crypto.parquet
  factors/                                 stocks.parquet, crypto.parquet  ← Phase 2 input
  reports/                                 *_factor_report.md, *_summary.csv, *.png
```
