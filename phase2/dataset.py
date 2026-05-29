"""
Phase 2 dataset prep: load the panel + factor matrix, attach multi-horizon
forward returns, cross-sectionally standardize, and split by time.

Cross-sectional RANK transform (per-timestamp percentile rank of features AND
target, centered to [-0.5, 0.5]) is:
  - leak-free by construction: each timestamp is normalized using only its own
    cross-section, never other dates — needs no train/test separation;
  - robust to crypto's fat tails: a z-score / raw-return target lets extreme
    returns dominate Lasso's MSE and shrink real coefficients to ~0, even when the
    rank-IC is strong. Ranking both sides makes Lasso fit the rank→rank relation
    that Spearman IC measures.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import panel as dpanel                 # data_scripts/panel.py
from factors import build as b
from factors import ic as fic

ROOT = Path(__file__).resolve().parent.parent
FACTOR_DIR = ROOT / "Data" / "factors"

HORIZONS = (4, 8, 24)


def load_aligned(asset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load panel and factor matrix, asserting they share (date, symbol) order."""
    panel = dpanel.load_panel(asset)
    fac = pd.read_parquet(FACTOR_DIR / f"{asset}.parquet")
    if not fac[["date", "symbol"]].reset_index(drop=True).equals(
            panel[["date", "symbol"]].reset_index(drop=True)):
        raise ValueError(
            "Factor matrix and panel are misaligned. Re-run phase1/run_factors.py."
        )
    return panel, fac


def _xs_rank(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Per-date cross-sectional percentile rank of `cols`, centered to [-0.5, 0.5]."""
    return df.groupby("date")[cols].rank(pct=True) - 0.5


def _xs_rank_series(s: pd.Series, dates: pd.Series) -> np.ndarray:
    """Per-date cross-sectional percentile rank of a series, centered."""
    tmp = pd.DataFrame({"v": np.asarray(s), "date": dates.values})
    return (tmp.groupby("date")["v"].rank(pct=True) - 0.5).values


def build_features(panel: pd.DataFrame, fac: pd.DataFrame, asset: str,
                   horizons=HORIZONS) -> pd.DataFrame:
    """
    Build the modeling frame from an already-loaded (panel, fac) pair:
      date, symbol, <rank factor columns>, fwd_<h> (rank) for each horizon.

    Sorted by date (then symbol) so pooled rows are in chronological order — a
    requirement for TimeSeriesSplit CV to produce time-ordered folds.
    """
    price = b.price_col(asset)
    factor_cols = [c for c in fac.columns if c not in ("date", "symbol")]

    out = fac[["date", "symbol"]].copy()
    out[factor_cols] = _xs_rank(fac, factor_cols)
    for h in horizons:
        fwd = fic.forward_return(panel, price, horizon=h)        # aligned to fac rows
        out[f"fwd_{h}"] = _xs_rank_series(fwd, out["date"])

    return out.sort_values(["date", "symbol"]).reset_index(drop=True)


def split_masks(df: pd.DataFrame, fracs=(0.6, 0.2, 0.2)
                ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Time-ordered split by unique timestamp. Returns boolean masks aligned to df."""
    uniq = np.sort(df["date"].unique())
    n = len(uniq)
    i1 = int(n * fracs[0])
    i2 = int(n * (fracs[0] + fracs[1]))
    train_cut, val_cut = uniq[i1], uniq[i2]
    train = df["date"] < train_cut
    val = (df["date"] >= train_cut) & (df["date"] < val_cut)
    test = df["date"] >= val_cut
    return train, val, test
