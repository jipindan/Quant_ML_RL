"""
Factor catalog: maps factor name -> (callable, category, hypothesis).

The orchestrator iterates this catalog to build the factor matrix. Windows are
expressed in BARS, so their calendar meaning depends on the bar frequency. Each
frequency gets its own window profile (`WINDOWS`); factor names embed the actual
window (e.g. `ret_5` on daily, `ret_6` on hourly) so downstream code reads them
dynamically. Add a new frequency = add a profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from . import build as b


@dataclass(frozen=True)
class Factor:
    name: str
    category: str
    fn: Callable
    hypothesis: str


# ── Window profiles (units = bars) ────────────────────────────────────────────
# "daily" reproduces the original hard-coded windows verbatim (stocks + daily
# crypto unchanged). "hourly" is week-centric for fast signals, with the
# volatility / idiosyncratic family stretched to 1–2 weeks (slow, persistent
# regime signals lose their edge at very short windows).
WINDOWS = {
    "daily": {
        "mom": [5, 10, 20, 60], "mom_accel": (20, 60),
        "dma": [20, 50], "bb": 20, "rsi": 14,
        "vol_ratio": 20, "obv": 20, "vpc": 20, "dvz": 60,
        "rvol": [20, 60], "vov": (60, 20), "hlr": 20, "gk": 20,
        "amh": 20, "hls": 20,
        "taker": 20, "num_trades_z": 60, "qvpt": 20,
        "rs": 60, "beta": 60, "idio": [60],
    },
    "hourly": {
        "mom": [6, 12, 24, 72], "mom_accel": (24, 72),
        "dma": [24, 72], "bb": 24, "rsi": 24,
        "vol_ratio": 24, "obv": 72, "vpc": 72, "dvz": 168,
        "rvol": [24, 72, 168], "vov": (168, 24), "hlr": 24, "gk": 24,
        "amh": 24, "hls": 24,
        "taker": 24, "num_trades_z": 72, "qvpt": 24,
        "rs": 72, "beta": 168, "idio": [168, 336],
    },
}


# ── Factor builders parametrized by a window profile W ─────────────────────────

def _common(W: dict) -> list[Factor]:
    out: list[Factor] = []

    # Momentum
    for n in W["mom"]:
        out.append(Factor(f"ret_{n}", "momentum",
                          (lambda n: lambda p, a, bench=None: b.ret_n(p, a, n))(n),
                          f"{n}-bar log return (momentum)"))
    fast, slow = W["mom_accel"]
    out.append(Factor("mom_accel", "momentum",
                      lambda p, a, bench=None: b.mom_accel(p, a, fast, slow),
                      "acceleration: recent vs distant momentum"))

    # Mean reversion
    for n in W["dma"]:
        out.append(Factor(f"dist_ma_{n}", "mean_reversion",
                          (lambda n: lambda p, a, bench=None: b.dist_ma(p, a, n))(n),
                          f"distance from {n}-bar MA (>0 overbought)"))
    out.append(Factor(f"bb_pos_{W['bb']}", "mean_reversion",
                      lambda p, a, bench=None: b.bb_pos(p, a, W["bb"]),
                      "Bollinger band position (z-score)"))
    out.append(Factor(f"rsi_{W['rsi']}", "mean_reversion",
                      lambda p, a, bench=None: b.rsi(p, a, W["rsi"]),
                      "classic RSI; high = overbought"))

    # Volume
    out.append(Factor(f"vol_ratio_{W['vol_ratio']}", "volume",
                      lambda p, a, bench=None: b.vol_ratio(p, W["vol_ratio"]),
                      "current vs avg volume"))
    out.append(Factor(f"obv_slope_{W['obv']}", "volume",
                      lambda p, a, bench=None: b.obv_slope(p, a, W["obv"]),
                      "OBV trend; positive = accumulation"))
    out.append(Factor(f"vol_price_corr_{W['vpc']}", "volume",
                      lambda p, a, bench=None: b.vol_price_corr(p, a, W["vpc"]),
                      "volume-price correlation"))
    out.append(Factor(f"dollar_vol_z_{W['dvz']}", "volume",
                      lambda p, a, bench=None: b.dollar_vol_zscore(p, a, W["dvz"]),
                      "dollar volume z-score"))

    # Volatility
    for n in W["rvol"]:
        out.append(Factor(f"rvol_{n}", "volatility",
                          (lambda n: lambda p, a, bench=None: b.rvol(p, a, n))(n),
                          f"{n}-bar realized vol (annualized)"))
    vov_n, vov_inner = W["vov"]
    out.append(Factor(f"vol_of_vol_{vov_n}", "volatility",
                      lambda p, a, bench=None: b.vol_of_vol(p, a, vov_n, vov_inner),
                      "vol of realized-vol"))
    out.append(Factor(f"hl_range_{W['hlr']}", "volatility",
                      lambda p, a, bench=None: b.hl_range(p, a, W["hlr"]),
                      "mean (H-L)/close"))
    out.append(Factor(f"garman_klass_{W['gk']}", "volatility",
                      lambda p, a, bench=None: b.garman_klass(p, W["gk"]),
                      "Garman-Klass OHLC vol"))

    # Microstructure
    out.append(Factor(f"amihud_illiq_{W['amh']}", "microstructure",
                      lambda p, a, bench=None: b.amihud_illiq(p, a, W["amh"]),
                      "Amihud illiquidity (|r|/dv)"))
    out.append(Factor(f"hl_spread_proxy_{W['hls']}", "microstructure",
                      lambda p, a, bench=None: b.hl_spread_proxy(p, W["hls"]),
                      "log(H/L) spread proxy"))
    return out


def _stocks_extra() -> list[Factor]:
    """Stocks-only cross-sectional factors. Stocks run daily-only, so windows
    stay literal (matches the original catalog exactly)."""
    return [
        Factor("rs_vs_spy_60", "cross_sectional",
               lambda p, a, bench: b.relative_strength(p, a, bench, 60),
               "60d return minus SPY 60d return"),
        Factor("rs_vs_spy_20", "cross_sectional",
               lambda p, a, bench: b.relative_strength(p, a, bench, 20),
               "20d return minus SPY 20d return"),
        Factor("beta_60", "cross_sectional",
               lambda p, a, bench: b.rolling_beta(p, a, bench, 60),
               "60d rolling beta vs SPY"),
        Factor("idio_vol_60", "cross_sectional",
               lambda p, a, bench: b.idio_vol(p, a, bench, 60),
               "60d idiosyncratic vol after beta-adjustment"),
        Factor("rank_sector_mom20", "cross_sectional",
               lambda p, a, bench: b.rank_in_sector(p, b.ret_n(p, a, 20)),
               "rank of 20d return within GICS sector"),
    ]


def _crypto_extra(W: dict) -> list[Factor]:
    """Crypto-only factors (Binance taker / num_trades fields + BTC benchmark)."""
    n_tk, n_nt, n_qv = W["taker"], W["num_trades_z"], W["qvpt"]
    n_rs, n_beta = W["rs"], W["beta"]
    out = [
        Factor(f"taker_buy_ratio_{n_tk}", "microstructure",
               lambda p, a, bench=None: b.taker_buy_ratio(p, n_tk),
               "taker buy / total volume, smoothed"),
        Factor(f"taker_imbalance_{n_tk}", "microstructure",
               lambda p, a, bench=None: b.taker_imbalance(p, n_tk),
               "(taker buy - sell) / total, smoothed"),
        Factor(f"quote_vol_per_trade_z_{n_qv}", "microstructure",
               lambda p, a, bench=None: b.quote_vol_per_trade(p, n_qv),
               "z-score of avg trade size"),
        Factor(f"num_trades_z_{n_nt}", "volume",
               lambda p, a, bench=None: b.num_trades_zscore(p, n_nt),
               "z-score of trade count"),
        Factor(f"rs_vs_btc_{n_rs}", "cross_sectional",
               lambda p, a, bench: b.relative_strength(p, a, bench, n_rs),
               "return minus BTC return"),
        Factor(f"beta_btc_{n_beta}", "cross_sectional",
               lambda p, a, bench: b.rolling_beta(p, a, bench, n_beta),
               "rolling beta vs BTC"),
    ]
    for n in W["idio"]:
        out.append(Factor(f"idio_vol_btc_{n}", "cross_sectional",
                          (lambda n: lambda p, a, bench: b.idio_vol(p, a, bench, n))(n),
                          "idiosyncratic vol vs BTC"))
    return out


def catalog_for(asset: str, profile: str = "daily") -> list[Factor]:
    if profile not in WINDOWS:
        raise ValueError(f"unknown window profile: {profile}")
    W = WINDOWS[profile]
    common = _common(W)
    if asset == "stocks":
        return common + _stocks_extra()
    if asset == "crypto":
        return common + _crypto_extra(W)
    raise ValueError(asset)
