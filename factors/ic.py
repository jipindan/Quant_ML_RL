"""
Information Coefficient (IC) and Information Coefficient Information Ratio (ICIR).

Convention: per date t, compute cross-sectional Spearman rank correlation
between factor(t) and forward_return(t -> t+H). Aggregate across dates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_return(panel: pd.DataFrame, price_col: str, horizon: int = 5) -> pd.Series:
    """Forward log return over `horizon` periods, by symbol."""
    g = panel.groupby("symbol", sort=False)[price_col]
    return np.log(g.shift(-horizon) / panel[price_col])


def daily_ic(factor: pd.Series, fwd: pd.Series, dates: pd.Series,
             min_assets: int = 10) -> pd.Series:
    """
    Cross-sectional Spearman IC per date.
    Returns a Series indexed by date.
    """
    df = pd.DataFrame({"f": factor.values, "y": fwd.values, "date": dates.values})
    df = df.dropna()

    def _ic(g):
        if len(g) < min_assets:
            return np.nan
        return g["f"].rank().corr(g["y"].rank())

    return df.groupby("date").apply(_ic).rename("ic")


def summarize_ic(ic: pd.Series, periods_per_year: int = 252) -> dict:
    """Aggregate metrics on a daily-IC time series."""
    ic = ic.dropna()
    if len(ic) == 0:
        return {"ic_mean": np.nan, "ic_std": np.nan, "icir": np.nan,
                "icir_ann": np.nan, "t_stat": np.nan, "hit_rate": np.nan, "n_obs": 0}
    mean = ic.mean()
    std = ic.std()
    icir = mean / std if std > 0 else np.nan
    return {
        "ic_mean": mean,
        "ic_std": std,
        "icir": icir,                                # daily ICIR
        "icir_ann": icir * np.sqrt(periods_per_year) if not np.isnan(icir) else np.nan,
        "t_stat": mean / (std / np.sqrt(len(ic))) if std > 0 else np.nan,
        "hit_rate": (np.sign(ic) == np.sign(mean)).mean(),
        "n_obs": int(len(ic)),
    }


def rolling_ic_sign_stability(ic: pd.Series, window: int = 252,
                              min_periods: int = 126) -> float:
    """
    Fraction of rolling 12-month windows where mean(IC) has the same sign as
    the overall mean(IC). Used as the 'consistent sign' screening criterion.
    """
    ic = ic.dropna()
    if len(ic) < window:
        return np.nan
    rolling_mean = ic.rolling(window, min_periods=min_periods).mean().dropna()
    overall_sign = np.sign(ic.mean())
    return float((np.sign(rolling_mean) == overall_sign).mean())
