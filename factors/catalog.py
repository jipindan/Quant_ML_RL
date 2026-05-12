"""
Factor catalog: maps factor name -> (callable, category, hypothesis).

The orchestrator iterates this catalog to build the factor matrix.
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


# Closures so we can parametrize windows uniformly.
def _ret(n):     return lambda panel, asset, bench=None: b.ret_n(panel, asset, n)
def _dma(n):     return lambda panel, asset, bench=None: b.dist_ma(panel, asset, n)
def _bb(n):      return lambda panel, asset, bench=None: b.bb_pos(panel, asset, n)
def _rsi(n):     return lambda panel, asset, bench=None: b.rsi(panel, asset, n)
def _vrat(n):    return lambda panel, asset, bench=None: b.vol_ratio(panel, n)
def _obv(n):     return lambda panel, asset, bench=None: b.obv_slope(panel, asset, n)
def _vpc(n):     return lambda panel, asset, bench=None: b.vol_price_corr(panel, asset, n)
def _dvz(n):     return lambda panel, asset, bench=None: b.dollar_vol_zscore(panel, asset, n)
def _rvol(n):    return lambda panel, asset, bench=None: b.rvol(panel, asset, n)
def _vov(n):     return lambda panel, asset, bench=None: b.vol_of_vol(panel, asset, n)
def _hlr(n):     return lambda panel, asset, bench=None: b.hl_range(panel, asset, n)
def _gk(n):      return lambda panel, asset, bench=None: b.garman_klass(panel, n)
def _amh(n):     return lambda panel, asset, bench=None: b.amihud_illiq(panel, asset, n)
def _hls(n):     return lambda panel, asset, bench=None: b.hl_spread_proxy(panel, n)


COMMON = [
    # Momentum
    Factor("ret_5",        "momentum",       _ret(5),   "short-term momentum"),
    Factor("ret_10",       "momentum",       _ret(10),  "short-term momentum"),
    Factor("ret_20",       "momentum",       _ret(20),  "monthly momentum"),
    Factor("ret_60",       "momentum",       _ret(60),  "quarterly momentum"),
    Factor("mom_accel",    "momentum",       lambda p,a,bench=None: b.mom_accel(p,a),
           "acceleration: recent vs distant momentum"),
    # Mean reversion
    Factor("dist_ma_20",   "mean_reversion", _dma(20),  "distance from 20d MA (>0 overbought)"),
    Factor("dist_ma_50",   "mean_reversion", _dma(50),  "distance from 50d MA"),
    Factor("bb_pos_20",    "mean_reversion", _bb(20),   "Bollinger band position (z-score)"),
    Factor("rsi_14",       "mean_reversion", _rsi(14),  "classic RSI; high = overbought"),
    # Volume
    Factor("vol_ratio_20", "volume",         _vrat(20), "today vs 20d avg volume"),
    Factor("obv_slope_20", "volume",         _obv(20),  "OBV trend; positive = accumulation"),
    Factor("vol_price_corr_20", "volume",    _vpc(20),  "volume-price correlation"),
    Factor("dollar_vol_z_60",   "volume",    _dvz(60),  "dollar volume z-score"),
    # Volatility
    Factor("rvol_20",      "volatility",     _rvol(20), "20d realized vol (annualized)"),
    Factor("rvol_60",      "volatility",     _rvol(60), "60d realized vol"),
    Factor("vol_of_vol_60", "volatility",    _vov(60),  "vol of 20d-vol over 60d"),
    Factor("hl_range_20",  "volatility",     _hlr(20),  "mean (H-L)/close over 20d"),
    Factor("garman_klass_20", "volatility",  _gk(20),   "Garman-Klass OHLC vol"),
    # Microstructure
    Factor("amihud_illiq_20", "microstructure", _amh(20), "Amihud illiquidity (|r|/dv)"),
    Factor("hl_spread_proxy_20", "microstructure", _hls(20), "log(H/L) spread proxy"),
]

# Stocks-only cross-sectional factors (need sector / market benchmark)
STOCKS_EXTRA = [
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

# Crypto-only (uses Binance taker / num_trades fields)
CRYPTO_EXTRA = [
    Factor("taker_buy_ratio_20", "microstructure",
           lambda p, a, bench=None: b.taker_buy_ratio(p, 20),
           "taker buy / total volume, 20d mean"),
    Factor("taker_imbalance_20", "microstructure",
           lambda p, a, bench=None: b.taker_imbalance(p, 20),
           "(taker buy - sell) / total, 20d mean"),
    Factor("quote_vol_per_trade_z_20", "microstructure",
           lambda p, a, bench=None: b.quote_vol_per_trade(p, 20),
           "z-score of avg trade size"),
    Factor("num_trades_z_60", "volume",
           lambda p, a, bench=None: b.num_trades_zscore(p, 60),
           "z-score of trade count"),
    Factor("rs_vs_btc_60", "cross_sectional",
           lambda p, a, bench: b.relative_strength(p, a, bench, 60),
           "60d return minus BTC 60d return"),
    Factor("beta_btc_60", "cross_sectional",
           lambda p, a, bench: b.rolling_beta(p, a, bench, 60),
           "60d rolling beta vs BTC"),
    Factor("idio_vol_btc_60", "cross_sectional",
           lambda p, a, bench: b.idio_vol(p, a, bench, 60),
           "60d idiosyncratic vol vs BTC"),
]


def catalog_for(asset: str) -> list[Factor]:
    if asset == "stocks":
        return COMMON + STOCKS_EXTRA
    if asset == "crypto":
        return COMMON + CRYPTO_EXTRA
    raise ValueError(asset)
