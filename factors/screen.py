"""
Factor screening:
  1. |ic_mean| >= 0.02  AND  sign-stability >= 0.70
  2. Pairwise Spearman corr pruning: if |rho| > 0.8, drop the lower-|ICIR| one.

NOTE on the IC-filter metric: we screen on |ic_mean| rather than |ICIR_ann|
because ICIR_ann = ICIR x sqrt(periods_per_year) is inflated ~6x at hourly
(sqrt(8760) vs sqrt(252)), making a fixed threshold frequency-dependent.
ic_mean is the average cross-sectional rank correlation and is frequency-neutral,
so one threshold (0.02) applies to both daily and hourly.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def apply_ic_filter(summary: pd.DataFrame, min_ic_mean: float = 0.02,
                    min_stability: float = 0.70) -> pd.DataFrame:
    keep = (summary["ic_mean"].abs() >= min_ic_mean) & \
           (summary["sign_stability"] >= min_stability)
    summary = summary.copy()
    summary["passes_ic"] = keep
    return summary


def prune_correlated(factor_matrix: pd.DataFrame, summary: pd.DataFrame,
                     threshold: float = 0.8) -> pd.DataFrame:
    """
    factor_matrix: rows are (date, symbol), columns are factor names.
    summary: must include 'icir_ann' indexed by factor name.
    """
    candidates = summary.index[summary["passes_ic"]].tolist()
    if len(candidates) <= 1:
        summary = summary.copy()
        summary["passes_corr"] = summary["passes_ic"]
        return summary

    sub = factor_matrix[candidates]
    corr = sub.corr(method="spearman").abs()

    dropped = set()
    ranked = summary.loc[candidates].assign(score=lambda d: d["icir_ann"].abs()) \
                                    .sort_values("score", ascending=False).index.tolist()

    for i, fi in enumerate(ranked):
        if fi in dropped:
            continue
        for fj in ranked[i + 1:]:
            if fj in dropped:
                continue
            if corr.loc[fi, fj] > threshold:
                dropped.add(fj)

    summary = summary.copy()
    summary["passes_corr"] = summary.index.map(
        lambda f: (f in candidates) and (f not in dropped)
    )
    summary.loc[~summary["passes_ic"], "passes_corr"] = False
    return summary
