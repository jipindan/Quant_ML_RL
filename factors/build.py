"""
Factor formulas. Each factor function:
  - Receives the long-format panel (sorted by symbol then date)
  - Returns a Series aligned to the panel index
  - Uses ONLY data available at time t (no look-ahead)

The orchestrator pairs factor(t) with forward_return(t -> t+5) for IC analysis.
Forward return is computed from the same close used by the factor, so there is
no leakage as long as rolling windows are causal (which pandas .rolling is).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Choose the price column once. For stocks we want adj_close (split/div aware);
# for crypto we use close (no adjustments needed).
def price_col(asset: str) -> str:
    return "adj_close" if asset == "stocks" else "close"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _g(panel: pd.DataFrame, col: str):
    return panel.groupby("symbol", sort=False)[col]


def _log_ret(panel: pd.DataFrame, asset: str, n: int = 1) -> pd.Series:
    p = price_col(asset)
    return np.log(_g(panel, p).shift(0) / _g(panel, p).shift(n))


# ── Momentum ──────────────────────────────────────────────────────────────────

def ret_n(panel, asset, n):
    return _log_ret(panel, asset, n)


def mom_accel(panel, asset):
    """Recent momentum minus distant momentum."""
    return ret_n(panel, asset, 20) - ret_n(panel, asset, 60) / 3.0


def mom_12_1(panel, asset):
    """12m return excluding most recent 1m (classic momentum minus reversal)."""
    p = price_col(asset)
    long_ret = np.log(_g(panel, p).shift(21) / _g(panel, p).shift(252))
    return long_ret


# ── Mean reversion ────────────────────────────────────────────────────────────

def dist_ma(panel, asset, n):
    p = price_col(asset)
    ma = _g(panel, p).transform(lambda s: s.rolling(n, min_periods=n).mean())
    return panel[p] / ma - 1.0


def bb_pos(panel, asset, n):
    p = price_col(asset)
    ma = _g(panel, p).transform(lambda s: s.rolling(n, min_periods=n).mean())
    sd = _g(panel, p).transform(lambda s: s.rolling(n, min_periods=n).std())
    return (panel[p] - ma) / (2.0 * sd)


def rsi(panel, asset, n=14):
    p = price_col(asset)
    delta = _g(panel, p).diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    # Wilder's smoothing approximated with rolling mean for simplicity/causality
    avg_up = up.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )
    avg_dn = dn.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )
    rs = avg_up / avg_dn.replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


# ── Volume ────────────────────────────────────────────────────────────────────

def vol_ratio(panel, n=20):
    avg = _g(panel, "volume").transform(lambda s: s.rolling(n, min_periods=n).mean())
    return panel["volume"] / avg.replace(0, np.nan)


def obv_slope(panel, asset, n=20):
    """Slope of On-Balance Volume over n days (units per day)."""
    p = price_col(asset)
    sgn = np.sign(_g(panel, p).diff())
    obv = (sgn * panel["volume"]).groupby(panel["symbol"], sort=False).cumsum()
    # rolling least-squares slope of OBV vs t over window n
    def slope(s):
        x = np.arange(len(s), dtype=float)
        x = x - x.mean()
        y = s.values - s.mean()
        denom = (x * x).sum()
        return (x * y).sum() / denom if denom > 0 else np.nan

    return obv.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).apply(slope, raw=False)
    )


def vol_price_corr(panel, asset, n=20):
    p = price_col(asset)
    ret = _g(panel, p).pct_change()
    dv = _g(panel, "volume").pct_change()
    df = pd.DataFrame({"r": ret, "v": dv, "symbol": panel["symbol"]})
    return df.groupby("symbol", sort=False).apply(
        lambda g: g["r"].rolling(n, min_periods=n).corr(g["v"])
    ).reset_index(level=0, drop=True)


def dollar_vol_zscore(panel, asset, n=60):
    p = price_col(asset)
    dv = panel[p] * panel["volume"]
    g = dv.groupby(panel["symbol"], sort=False)
    mean = g.transform(lambda s: s.rolling(n, min_periods=n).mean())
    std = g.transform(lambda s: s.rolling(n, min_periods=n).std())
    return (dv - mean) / std.replace(0, np.nan)


# ── Volatility ────────────────────────────────────────────────────────────────

def rvol(panel, asset, n=20):
    """Annualized realized vol of daily log returns."""
    r = _log_ret(panel, asset, 1)
    return r.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).std() * np.sqrt(252)
    )


def vol_of_vol(panel, asset, n=60, inner=20):
    rv = rvol(panel, asset, inner)
    return rv.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).std()
    )


def hl_range(panel, asset, n=20):
    p = price_col(asset)
    rng = (panel["high"] - panel["low"]) / panel[p]
    return rng.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )


def garman_klass(panel, n=20):
    """Garman-Klass volatility estimator, annualized."""
    o, h, l, c = panel["open"], panel["high"], panel["low"], panel["close"]
    rs = 0.5 * (np.log(h / l)) ** 2 - (2 * np.log(2) - 1) * (np.log(c / o)) ** 2
    return rs.groupby(panel["symbol"], sort=False).transform(
        lambda s: np.sqrt(s.rolling(n, min_periods=n).mean() * 252)
    )


# ── Microstructure ────────────────────────────────────────────────────────────

def amihud_illiq(panel, asset, n=20):
    """Mean of |daily return| / dollar volume over n days (x 1e6 for readability)."""
    p = price_col(asset)
    r = _log_ret(panel, asset, 1).abs()
    dv = panel[p] * panel["volume"]
    ratio = (r / dv.replace(0, np.nan)) * 1e6
    return ratio.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )


def hl_spread_proxy(panel, n=20):
    """Simple high-low spread proxy = mean log(H/L) over n days."""
    s = np.log(panel["high"] / panel["low"])
    return s.groupby(panel["symbol"], sort=False).transform(
        lambda x: x.rolling(n, min_periods=n).mean()
    )


# Crypto-only microstructure (uses Binance taker fields)

def taker_buy_ratio(panel, n=20):
    r = panel["taker_buy_volume"] / panel["volume"].replace(0, np.nan)
    return r.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )


def taker_imbalance(panel, n=20):
    """(taker buy - taker sell) / total, smoothed."""
    sell = panel["volume"] - panel["taker_buy_volume"]
    imb = (panel["taker_buy_volume"] - sell) / panel["volume"].replace(0, np.nan)
    return imb.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).mean()
    )


def quote_vol_per_trade(panel, n=20):
    r = panel["quote_volume"] / panel["num_trades"].replace(0, np.nan)
    g = r.groupby(panel["symbol"], sort=False)
    mean = g.transform(lambda s: s.rolling(n, min_periods=n).mean())
    std = g.transform(lambda s: s.rolling(n, min_periods=n).std())
    return (r - mean) / std.replace(0, np.nan)


def num_trades_zscore(panel, n=60):
    nt = panel["num_trades"]
    g = nt.groupby(panel["symbol"], sort=False)
    mean = g.transform(lambda s: s.rolling(n, min_periods=n).mean())
    std = g.transform(lambda s: s.rolling(n, min_periods=n).std())
    return (nt - mean) / std.replace(0, np.nan)


# ── Cross-sectional ───────────────────────────────────────────────────────────

def rank_in_sector(panel, base_factor: pd.Series) -> pd.Series:
    """Rank base_factor within sector each date. Returns NaN where sector missing."""
    tmp = pd.DataFrame({"f": base_factor, "date": panel["date"], "sector": panel["sector"]})
    return tmp.groupby(["date", "sector"])["f"].transform(
        lambda s: s.rank(pct=True) - 0.5
    )


def relative_strength(panel, asset, bench: pd.DataFrame, n: int):
    """ret_n minus benchmark ret_n on the same date."""
    own = ret_n(panel, asset, n)
    b = bench.set_index("date")["bench_ret_" + str(n)]
    aligned = panel["date"].map(b)
    return own - aligned.values


def rolling_beta(panel, asset, bench: pd.DataFrame, n: int = 60):
    """Rolling beta of symbol log returns vs benchmark log returns."""
    p = price_col(asset)
    r = np.log(panel[p] / _g(panel, p).shift(1))
    bench_r = bench.set_index("date")["bench_logret"]
    panel_bench = panel["date"].map(bench_r).values
    df = pd.DataFrame({"r": r.values, "b": panel_bench, "symbol": panel["symbol"].values})

    def beta(g):
        x = g["b"]
        y = g["r"]
        cov = y.rolling(n, min_periods=n).cov(x)
        var = x.rolling(n, min_periods=n).var()
        return cov / var.replace(0, np.nan)

    out = df.groupby("symbol", sort=False, group_keys=False).apply(beta)
    return out.values


def idio_vol(panel, asset, bench: pd.DataFrame, n: int = 60):
    """Std of (symbol return - beta * bench return), n-day window, annualized."""
    p = price_col(asset)
    r = np.log(panel[p] / _g(panel, p).shift(1))
    bench_r = bench.set_index("date")["bench_logret"]
    panel_bench = pd.Series(panel["date"].map(bench_r).values, index=panel.index)
    beta = pd.Series(rolling_beta(panel, asset, bench, n), index=panel.index)
    resid = r - beta * panel_bench
    return resid.groupby(panel["symbol"], sort=False).transform(
        lambda s: s.rolling(n, min_periods=n).std() * np.sqrt(252)
    )


# ── Benchmark series construction ─────────────────────────────────────────────

def build_benchmark(bench_panel: pd.DataFrame, asset: str) -> pd.DataFrame:
    """
    bench_panel: single-symbol panel for SPY (stocks) or BTCUSDT (crypto).
    Returns df with columns: date, bench_logret, bench_ret_5, bench_ret_20, bench_ret_60.
    """
    p = price_col(asset)
    b = bench_panel.sort_values("date").copy()
    b["bench_logret"] = np.log(b[p] / b[p].shift(1))
    for n in (5, 20, 60):
        b[f"bench_ret_{n}"] = np.log(b[p] / b[p].shift(n))
    return b[["date", "bench_logret", "bench_ret_5", "bench_ret_20", "bench_ret_60"]]
