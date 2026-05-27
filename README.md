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

## `data_scripts/fetch.py` — fetch + clean (Binance crypto / yfinance stocks)

One script for both sources, selected with `--source`.

```
python data_scripts/fetch.py --source {crypto|stocks} (--fetch | --clean FILE [...] | --fetch --clean) [options]
```

| Argument | Default | Description |
|---|---|---|
| `--source` | required | `crypto` (Binance) or `stocks` (yfinance) |
| `--fetch` | — | Fetch data from the source |
| `--clean [FILE ...]` | — | Clean CSV file(s). With `--fetch`: cleans the fetched file |
| `--symbol` | required with `--fetch` | `BTCUSDT` (crypto) / `AAPL`, `0700.HK` (stocks) |
| `--interval` | required with `--fetch` | crypto: `1m 5m 15m 1h 4h 1d 1w`; stocks: `1m 2m 5m 15m 30m 60m 90m 1h 1d 5d 1wk 1mo 3mo` |
| `--start` | required with `--fetch` | Start date `YYYY-MM-DD` |
| `--end` | required with `--fetch` | End date `YYYY-MM-DD` (exclusive) |
| `--output` | `Data/raw/<Type>/<SYMBOL>_<INTERVAL>_<START>_<END>.csv` | Output path |

```bash
python data_scripts/fetch.py --source crypto --fetch --clean --symbol BTCUSDT --interval 1d --start 2018-01-01 --end 2025-01-01
python data_scripts/fetch.py --source stocks --fetch --clean --symbol SPY --interval 1d --start 2010-01-01 --end 2025-01-01
python data_scripts/fetch.py --source crypto --clean Data/raw/Crypto/BTCUSDT_1d_2018-01-01_2025-01-01.csv
```

> Stock intraday intervals (`< 1d`) are only available for the last 60 days. HK tickers use the `.HK` suffix.

---

## Output Format

### Crypto (`--source crypto`)

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

### Equities (`--source stocks`)

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

`fetch.py` applies this pipeline (gap reporting is crypto-only):

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
factors/                     factor library (importable, no I/O)
  build.py     factor formulas (causal rolling ops, groupby symbol)
  catalog.py   registry mapping name → (callable, category, hypothesis)
  ic.py        cross-sectional Spearman IC per date, ICIR, rolling sign-stability
  screen.py    |ICIR_ann|≥0.5 ∧ sign_stability≥0.70  then  |ρ|>0.8 corr pruning
phase1/                      factor-engineering pipeline
  run_factors.py             panel + benchmark → factor matrix parquet
  run_ic.py                  factor matrix → IC → screen → plots → report
```

Phase 1 reads the panel parquet produced by `data_scripts/` (see Phase 0). The
two phases talk only through on-disk parquet files, not Python imports.

## End-to-end run

### Stocks (S&P 500 top 200, 2010-2025)

```bash
# 1. Universe (~5 min: 503 yfinance calls for market caps)
python data_scripts/build_universe_stocks.py

# 2. Download + clean all symbols, then build the panel (~2 min)
python data_scripts/download_universe.py --asset stocks --start 2010-01-01 --end 2025-01-01

# 3. Benchmark (used for rs_vs_spy / beta_60 / idio_vol_60)
python data_scripts/fetch.py --source stocks --fetch --clean --symbol SPY --interval 1d --start 2010-01-01 --end 2025-01-01

# 4. Factors, then IC / screening / report
python phase1/run_factors.py --asset stocks --start 2010-01-01 --end 2025-01-01
python phase1/run_ic.py      --asset stocks --start 2010-01-01 --end 2025-01-01
```

### Crypto (Binance top 30 by 24h vol, 2018-2025)

```bash
python data_scripts/build_universe_crypto.py
python data_scripts/download_universe.py --asset crypto --start 2018-01-01 --end 2025-01-01
# BTCUSDT downloads as part of the universe → also serves as benchmark
python phase1/run_factors.py --asset crypto --start 2018-01-01 --end 2025-01-01
python phase1/run_ic.py      --asset crypto --start 2018-01-01 --end 2025-01-01
```

`download_universe.py` builds `Data/panels/<asset>.parquet` as its last step
(pass `--no-panel` to skip). To rebuild only the panel from existing cleaned
CSVs: `python data_scripts/panel.py --asset crypto --start 2018-01-01 --end 2025-01-01`.

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
| `reports/{stocks,crypto}_factor_report.md` | Markdown report: IC/ICIR table, survivors, plots. |
| `reports/{stocks,crypto}_factor_summary.csv` | Same table in CSV form. |
| `reports/{stocks,crypto}_corr.png` | Correlation heatmap of survivors. |
| `reports/{stocks,crypto}_rolling_ic.png` | 3-month rolling mean IC for top factors. |

## Results snapshot

**Stocks** (199 symbols, 2010–2024): 9 survivors. Strongest: `amihud_illiq_20` (+, ICIR_ann ≈ 2.05), `ret_5` (-, 1-week reversal), `dist_ma_20` (-), `hl_spread_proxy_20` (+), `vol_of_vol_60` (+).

**Crypto** (16 symbols after coverage filter, 2018–2024): 7 survivors. Strongest: `idio_vol_btc_60` (-, low-vol anomaly, ICIR_ann ≈ -3.46), `amihud_illiq_20` (- — **sign-flipped vs equities**), `garman_klass_20` (-), `vol_of_vol_60` (-), `taker_buy_ratio_20` (+, order-flow), `num_trades_z_60` (-), `ret_5` (-).

## Caveats

- **Survivorship bias (stocks):** the universe is the *current* S&P 500 top-200 by market cap. Companies that dropped out are not included. Documented in the stocks report; needs the same call-out in any cross-asset comparison.
- **Coverage filter (crypto):** symbols with row count below 0.8× median are dropped. Recent listings (CHIP / ONDO / SPK / SAHARA / SUI / TAO / TON / PENDLE / ENA / PEPE / LUNC / PENGU / RAD / SAGA) drop out at the panel-build step, leaving 16 of the 30 top-volume pairs.
- **Walk-forward / out-of-sample:** Phase 1 uses the full date range for factor screening. The Phase 2 ML stacking step is responsible for purged walk-forward validation; do not re-tune screening criteria on test data.

---

# Directory structure (full)

```
data_scripts/                             everything that produces data
  fetch.py                                fetch + clean one symbol (--source crypto|stocks)
  build_universe_{stocks,crypto}.py       build the universe CSVs
  download_universe.py                    download + clean universe, then build the panel
  panel.py                                cleaned CSVs → long-format panel parquet
factors/                                  factor library (importable, no I/O)
  build.py, catalog.py, ic.py, screen.py
phase1/                                   factor-engineering pipeline
  run_factors.py                          panel + benchmark → factor matrix
  run_ic.py                               factor matrix → IC → screen → report
reports/                                  Phase 1 reports (tracked in git)
  *_factor_report.md, *_summary.csv, *.png
Data/                                     (gitignored)
  raw/{Stocks,Crypto}/<sym>_<ivl>_<start>_<end>.csv
  cleaned/{Stocks,Crypto}/...             same shape, post-cleaning
  universe/                               sp500_top200.csv, crypto_top30.csv
  panels/                                 stocks.parquet, crypto.parquet
  factors/                                stocks.parquet, crypto.parquet  ← Phase 2 input
```
