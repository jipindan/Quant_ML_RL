"""
Factor screening:
  1. |ICIR_ann| >= 0.5  AND  sign-stability >= 0.70
  2. Pairwise Spearman corr pruning: if |rho| > 0.8, drop the lower-|ICIR| one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def apply_ic_filter(summary: pd.DataFrame, min_icir_ann: float = 0.5,
                    min_stability: float = 0.70) -> pd.DataFrame:
    keep = (summary["icir_ann"].abs() >= min_icir_ann) & \
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
