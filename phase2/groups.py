"""
Split the IC-surviving factors into two economic-role groups, then corr-prune
within each group.

- FAST (alpha):   momentum / mean-reversion / directional price-volume signals.
                  Decay fast, predict near-term return best.
- SLOW (regime):  volatility / idiosyncratic-vol / liquidity / beta signals.
                  Slow, persistent; describe the current market regime.

Grouping is by factor *family* (the name with its trailing window stripped), so
it is window-agnostic and works for any frequency profile. Within each group we
reuse `factors.screen.prune_correlated` (|rho| > 0.8 keeps the stronger one), so
the highly collinear volatility cluster collapses to a few representatives.
"""
from __future__ import annotations

import re

import pandas as pd

from factors import screen as fscr

# Factor family -> group. Family = factor name with trailing "_<window>" removed
# (e.g. ret_6 -> ret, idio_vol_btc_168 -> idio_vol_btc, mom_accel -> mom_accel).
FAST_FAMILIES = {
    "ret", "mom_accel", "dist_ma", "bb_pos", "rsi",
    "rs_vs_btc", "rs_vs_spy", "vol_price_corr",
    "taker_buy_ratio", "taker_imbalance", "obv_slope",
}
SLOW_FAMILIES = {
    "rvol", "vol_of_vol", "garman_klass", "hl_range", "hl_spread_proxy",
    "amihud_illiq", "idio_vol_btc", "idio_vol", "beta_btc", "beta",
    "vol_ratio", "dollar_vol_z", "num_trades_z", "quote_vol_per_trade_z",
}


def family(name: str) -> str:
    """Strip a trailing _<digits> window suffix: 'rs_vs_btc_72' -> 'rs_vs_btc'."""
    return re.sub(r"_\d+$", "", name)


def _group_of(name: str) -> str:
    fam = family(name)
    if fam in FAST_FAMILIES:
        return "fast"
    if fam in SLOW_FAMILIES:
        return "slow"
    raise KeyError(
        f"factor '{name}' (family '{fam}') is not assigned to fast/slow; "
        f"add it to FAST_FAMILIES or SLOW_FAMILIES in phase2/groups.py"
    )


def _prune_within(group_factors: list[str], summary: pd.DataFrame,
                  fac: pd.DataFrame) -> list[str]:
    """Run screen.prune_correlated scoped to one group (mark only its members as
    passing the IC filter, then prune among them)."""
    if len(group_factors) <= 1:
        return group_factors
    sub = summary.copy()
    sub["passes_ic"] = False
    sub.loc[group_factors, "passes_ic"] = True
    sub = fscr.prune_correlated(fac, sub)
    # Preserve the group's |ic_mean| ordering for readability.
    kept = sub.index[sub["passes_corr"]].tolist()
    return sorted(kept, key=lambda f: abs(summary.loc[f, "ic_mean"]), reverse=True)


def resolve_groups(summary: pd.DataFrame, fac: pd.DataFrame
                   ) -> tuple[list[str], list[str]]:
    """
    summary: IC summary indexed by factor (must have ic_mean, sign_stability,
             icir_ann). fac: wide factor matrix (columns include factor names).
    Returns (fast_factors, slow_factors) after IC filter + within-group pruning.
    """
    screened = fscr.apply_ic_filter(summary)
    survivors = screened.index[screened["passes_ic"]].tolist()

    fast = [f for f in survivors if _group_of(f) == "fast"]
    slow = [f for f in survivors if _group_of(f) == "slow"]

    fast = _prune_within(fast, screened, fac)
    slow = _prune_within(slow, screened, fac)
    return fast, slow
