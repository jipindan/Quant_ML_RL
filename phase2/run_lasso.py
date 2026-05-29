"""
Phase 2 — two-layer Lasso stacking baseline (crypto, hourly).

Architecture:
    fast factors (momentum/reversion) -> Lasso_fast(y=h4)  -> alpha_fast ┐
                                                                          ├-> meta(Ridge, y=h8) -> combined
    slow factors (volatility/regime)  -> Lasso_slow(y=h24) -> alpha_slow ┘

Leakage discipline:
    - base models fit on TRAIN only (LassoCV picks alpha via TimeSeriesSplit within train)
    - meta fits on VAL only (base predictions on val are naturally out-of-sample)
    - TEST is touched once, for final evaluation

    python phase2/run_lasso.py --asset crypto --interval 1h

Outputs to reports/phase2/: IC summary (md+csv), model coefficients, test predictions.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_scripts"))

import groups                                  # noqa: E402  (phase2/groups.py)
import dataset                                 # noqa: E402  (phase2/dataset.py)
import panel as dpanel                         # noqa: E402  (data_scripts/panel.py)
from factors import ic as fic                  # noqa: E402

from sklearn.linear_model import LassoCV, Ridge          # noqa: E402
from sklearn.model_selection import TimeSeriesSplit      # noqa: E402

REPORTS = ROOT / "reports" / "phase2"

# horizon each model targets
H_FAST, H_SLOW, H_META = 4, 24, 8


def fit_lasso(X: np.ndarray, y: np.ndarray, n_splits: int = 5) -> LassoCV:
    """LassoCV with time-ordered CV (rows must already be sorted by date)."""
    model = LassoCV(cv=TimeSeriesSplit(n_splits=n_splits),
                    max_iter=10000, n_jobs=-1, random_state=0)
    model.fit(X, y)
    return model


def _predict_valid(model, X: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Predict only on rows free of NaN; NaN elsewhere (those rows are unused)."""
    out = np.full(X.shape[0], np.nan)
    out[valid] = model.predict(X[valid])
    return out


def evaluate(score: np.ndarray, fwd: np.ndarray, dates: pd.Series,
             ppy: int) -> dict:
    """Cross-sectional IC of a signal vs a forward return over the test window."""
    ic_series = fic.daily_ic(pd.Series(score), pd.Series(fwd), dates)
    stats = fic.summarize_ic(ic_series, periods_per_year=ppy)
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", default="crypto", choices=["crypto", "stocks"])
    p.add_argument("--interval", default="1h")
    # accepted for CLI symmetry with phase1; data is read from parquet
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    args = p.parse_args()

    ppy = dpanel.bars_per_year(args.asset, args.interval)

    # ── 1. Load + groups ──────────────────────────────────────────────────────
    panel, fac = dataset.load_aligned(args.asset)
    summary = pd.read_csv(REPORTS.parent / f"{args.asset}_factor_summary.csv",
                          index_col="factor")
    fast, slow = groups.resolve_groups(summary, fac)
    print(f"FAST ({len(fast)}): {fast}")
    print(f"SLOW ({len(slow)}): {slow}")
    if not fast or not slow:
        raise SystemExit("A group is empty — cannot build the two-layer stack.")

    # ── 2. Features + splits ──────────────────────────────────────────────────
    df = dataset.build_features(panel, fac, args.asset,
                                horizons=(H_FAST, H_SLOW, H_META))
    train_m, val_m, test_m = dataset.split_masks(df)

    used = fast + slow + [f"fwd_{H_FAST}", f"fwd_{H_SLOW}", f"fwd_{H_META}"]
    valid = df[used].notna().all(axis=1)        # common non-NaN rows for alignment
    train_m &= valid; val_m &= valid; test_m &= valid
    print(f"rows  train={train_m.sum():,}  val={val_m.sum():,}  test={test_m.sum():,}")
    for name, m in [("train", train_m), ("val", val_m), ("test", test_m)]:
        d = df.loc[m, "date"]
        print(f"  {name}: {d.min()} → {d.max()}")

    Xf = df[fast].to_numpy(); Xs = df[slow].to_numpy()
    vmask = valid.to_numpy()

    # ── 3. Base models on TRAIN ───────────────────────────────────────────────
    m_fast = fit_lasso(Xf[train_m.to_numpy()], df.loc[train_m, f"fwd_{H_FAST}"].to_numpy())
    m_slow = fit_lasso(Xs[train_m.to_numpy()], df.loc[train_m, f"fwd_{H_SLOW}"].to_numpy())

    af = _predict_valid(m_fast, Xf, vmask)      # alpha_fast (NaN on warmup/tail rows)
    as_ = _predict_valid(m_slow, Xs, vmask)     # alpha_slow

    nz_fast = int((m_fast.coef_ != 0).sum())
    nz_slow = int((m_slow.coef_ != 0).sum())
    print(f"Lasso_fast: alpha={m_fast.alpha_:.2e}  nonzero={nz_fast}/{len(fast)}")
    print(f"Lasso_slow: alpha={m_slow.alpha_:.2e}  nonzero={nz_slow}/{len(slow)}")

    # ── 4. Meta on VAL (base preds on val are OOS) ────────────────────────────
    Xmeta = np.column_stack([af, as_])
    meta = Ridge(alpha=1.0)
    meta.fit(Xmeta[val_m.to_numpy()], df.loc[val_m, f"fwd_{H_META}"].to_numpy())
    combined = np.full(len(df), np.nan)
    combined[vmask] = meta.predict(Xmeta[vmask])
    print(f"meta Ridge weights: fast={meta.coef_[0]:+.4f}  slow={meta.coef_[1]:+.4f}  "
          f"intercept={meta.intercept_:+.4f}")

    # ── 5. Evaluate on TEST ───────────────────────────────────────────────────
    tm = test_m.to_numpy()
    dates_t = df.loc[test_m, "date"].reset_index(drop=True)
    signals = {"alpha_fast": af[tm], "alpha_slow": as_[tm], "combined": combined[tm]}
    fwds = {h: df.loc[test_m, f"fwd_{h}"].to_numpy() for h in (H_FAST, H_SLOW, H_META)}

    # native horizon per signal + common horizon (h8) for the "does combining help" test
    evals = [("alpha_fast", H_FAST), ("alpha_slow", H_SLOW), ("combined", H_META),
             ("alpha_fast", H_META), ("alpha_slow", H_META)]
    rows = []
    for sig, h in evals:
        st = evaluate(signals[sig], fwds[h], dates_t, ppy)
        rows.append({"signal": sig, "eval_h": h, "ic_mean": st["ic_mean"],
                     "icir": st["icir"], "icir_ann": st["icir_ann"],
                     "t_stat": st["t_stat"], "hit_rate": st["hit_rate"],
                     "n_obs": st["n_obs"]})
    res = pd.DataFrame(rows)

    # ── 6. Write outputs ──────────────────────────────────────────────────────
    REPORTS.mkdir(parents=True, exist_ok=True)
    res.to_csv(REPORTS / "ic_summary.csv", index=False)

    coef = pd.concat([
        pd.DataFrame({"group": "fast", "factor": fast, "coef": m_fast.coef_}),
        pd.DataFrame({"group": "slow", "factor": slow, "coef": m_slow.coef_}),
    ], ignore_index=True)
    coef.to_csv(REPORTS / "coefficients.csv", index=False)

    preds = df.loc[test_m, ["date", "symbol"]].copy()
    preds["alpha_fast"] = af[tm]; preds["alpha_slow"] = as_[tm]; preds["combined"] = combined[tm]
    preds.to_parquet(REPORTS / "test_predictions.parquet", index=False)

    _write_report(args, fast, slow, m_fast, m_slow, meta, res)
    print("\n=== Test-set IC ===")
    print(res.to_string(index=False))
    print(f"\nOutputs → {REPORTS}")


def _write_report(args, fast, slow, m_fast, m_slow, meta, res):
    lines = [f"# Phase 2 — Lasso Stacking ({args.asset.upper()}, {args.interval})\n"]
    lines.append(f"- Horizons: fast=h{H_FAST}, slow=h{H_SLOW}, meta=h{H_META}")
    lines.append(f"- FAST factors ({len(fast)}): {', '.join(fast)}")
    lines.append(f"- SLOW factors ({len(slow)}): {', '.join(slow)}")
    lines.append(f"- Lasso_fast alpha={m_fast.alpha_:.2e}, nonzero={(m_fast.coef_!=0).sum()}/{len(fast)}")
    lines.append(f"- Lasso_slow alpha={m_slow.alpha_:.2e}, nonzero={(m_slow.coef_!=0).sum()}/{len(slow)}")
    lines.append(f"- Meta Ridge weights: fast={meta.coef_[0]:+.4f}, slow={meta.coef_[1]:+.4f}\n")
    lines.append("## Test-set IC\n")
    lines.append(res.round(4).to_markdown(index=False))
    lines.append("\n> Native horizon: alpha_fast@h4, alpha_slow@h24, combined@h8.")
    lines.append("> Common horizon (h8) rows let you compare whether combining beats each base alone.")
    (REPORTS / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
