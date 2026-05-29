"""
Phase 1 — IC analysis, screening, and report.

Load the factor matrix (run_factors.py) + the panel, compute IC/ICIR with sign
stability, screen (IC filter then correlation pruning), and write the markdown
report + plots to reports/.

    python phase1/run_ic.py --asset crypto --start 2018-01-01 --end 2025-01-01
    python phase1/run_ic.py --asset stocks --start 2010-01-01 --end 2025-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data_scripts"))

import panel as dpanel                       # noqa: E402  (data_scripts/panel.py)
from factors import build as b               # noqa: E402
from factors import ic as fic                # noqa: E402
from factors import screen as fscr           # noqa: E402

import matplotlib                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt              # noqa: E402

REPORTS = ROOT / "reports"
FACTOR_DIR = ROOT / "Data" / "factors"


def run_ic(fac: pd.DataFrame, panel: pd.DataFrame, asset: str,
           horizon: int, periods_per_year: int
           ) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    price = b.price_col(asset)
    fwd = fic.forward_return(panel, price, horizon=horizon)
    factor_names = [c for c in fac.columns if c not in ("date", "symbol")]

    rows = []
    daily_ics = {}
    for name in factor_names:
        ic_series = fic.daily_ic(fac[name], fwd, panel["date"])
        daily_ics[name] = ic_series
        stats = fic.summarize_ic(ic_series, periods_per_year=periods_per_year)
        stats["sign_stability"] = fic.rolling_ic_sign_stability(
            ic_series, window=periods_per_year, min_periods=periods_per_year // 2)
        stats["factor"] = name
        rows.append(stats)
    summary = pd.DataFrame(rows).set_index("factor")
    return summary, daily_ics


def make_corr_heatmap(corr: pd.DataFrame, out_path: Path):
    fig, ax = plt.subplots(figsize=(max(8, 0.4 * len(corr)), max(7, 0.4 * len(corr))))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90, fontsize=8)
    ax.set_yticks(range(len(corr)), corr.index, fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.7)
    ax.set_title("Factor Spearman correlation (survivors)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def make_rolling_ic_plot(daily_ics: dict, summary: pd.DataFrame,
                         top_k: int, out_path: Path, window: int):
    # `window` is one quarter of IC observations (bars), so the smoothing spans
    # ~3 months at any frequency: 63 on daily (252//4), 2190 on hourly (8760//4).
    # A fixed 63-bar window would only smooth 2.6 days of hourly IC -> hairy plot.
    top = summary.assign(score=lambda d: d["icir_ann"].abs()) \
                 .sort_values("score", ascending=False).head(top_k).index.tolist()
    fig, ax = plt.subplots(figsize=(12, 5))
    for name in top:
        s = daily_ics[name].dropna()
        if len(s) == 0:
            continue
        ax.plot(s.index, s.rolling(window, min_periods=window // 3).mean(),
                label=name, lw=1.2)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"Rolling 3-month mean IC — top {top_k} factors by |ICIR|")
    ax.set_ylabel("IC")
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def write_report(asset: str, summary: pd.DataFrame, panel: pd.DataFrame,
                 horizon: int, out_md: Path, heatmap_png: Path,
                 ic_png: Path, n_candidates: int):
    survivors = summary[summary["passes_corr"]].sort_values("icir_ann", key=abs, ascending=False)
    ic_passed = summary[summary["passes_ic"]]

    lines = []
    lines.append(f"# Phase 1 Factor Report — {asset.upper()}\n")
    lines.append(f"- Universe: {panel['symbol'].nunique()} symbols")
    lines.append(f"- Date range: {panel['date'].min().date()} → {panel['date'].max().date()}")
    lines.append(f"- Forward return horizon: {horizon} bars (log)")
    lines.append(f"- Candidates evaluated: **{n_candidates}**")
    lines.append(f"- Passed IC filter (|ic_mean|≥0.02 & sign stability≥0.70): **{len(ic_passed)}**")
    lines.append(f"- Survivors after corr-pruning (|ρ|>0.8): **{len(survivors)}**\n")

    if asset == "stocks":
        lines.append("> **Survivorship bias caveat:** the universe uses the *current* "
                     "S&P 500 top-200 by market cap. Companies that dropped out of the "
                     "index are not included. This biases results upward versus a true "
                     "point-in-time universe and should be acknowledged in Phase 5.\n")

    lines.append("## All candidates — IC/ICIR\n")
    cols = ["ic_mean", "icir", "icir_ann", "sign_stability", "t_stat", "hit_rate", "n_obs",
            "passes_ic", "passes_corr"]
    full = summary[cols].copy()
    full["ic_mean"] = full["ic_mean"].round(4)
    full["icir"] = full["icir"].round(4)
    full["icir_ann"] = full["icir_ann"].round(3)
    full["sign_stability"] = full["sign_stability"].round(3)
    full["t_stat"] = full["t_stat"].round(2)
    full["hit_rate"] = full["hit_rate"].round(3)
    lines.append(full.sort_values("icir_ann", key=abs, ascending=False).to_markdown())
    lines.append("")

    lines.append("## Survivors\n")
    if len(survivors) == 0:
        lines.append("_No factors passed both screens._\n")
    else:
        s = survivors[["ic_mean", "icir_ann", "sign_stability", "t_stat", "n_obs"]].copy()
        s["ic_mean"] = s["ic_mean"].round(4)
        s["icir_ann"] = s["icir_ann"].round(3)
        s["sign_stability"] = s["sign_stability"].round(3)
        s["t_stat"] = s["t_stat"].round(2)
        lines.append(s.to_markdown())
        lines.append("")

    lines.append("## Plots\n")
    lines.append(f"![Correlation heatmap]({heatmap_png.name})\n")
    lines.append(f"![Rolling IC]({ic_png.name})\n")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {out_md}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--asset", choices=["stocks", "crypto"], required=True)
    p.add_argument("--interval", default="1d")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--horizon", type=int, default=5)
    args = p.parse_args()

    fac_path = FACTOR_DIR / f"{args.asset}.parquet"
    if not fac_path.exists():
        raise FileNotFoundError(
            f"Factor matrix missing: {fac_path}\n"
            f"Run it first:  python phase1/run_factors.py --asset {args.asset} "
            f"--start {args.start} --end {args.end}"
        )
    fac = pd.read_parquet(fac_path)
    panel = dpanel.load_panel(args.asset)

    # fac is built row-for-row from the panel; daily_ic aligns positionally, so
    # the two artifacts must share identical (date, symbol) ordering. Catch a
    # stale/rebuilt panel early rather than computing silently-wrong IC.
    if not fac[["date", "symbol"]].reset_index(drop=True).equals(
            panel[["date", "symbol"]].reset_index(drop=True)):
        raise ValueError(
            "Factor matrix and panel are misaligned (different (date, symbol) "
            "ordering). Re-run run_factors.py after rebuilding the panel."
        )

    # 1. IC analysis
    ppy = dpanel.bars_per_year(args.asset, args.interval)
    print(f"Computing IC/ICIR... (annualizing with {ppy} bars/year, "
          f"interval={args.interval})")
    summary, daily_ics = run_ic(fac, panel, args.asset,
                                horizon=args.horizon, periods_per_year=ppy)

    # 2. Screen: IC filter, then correlation pruning on the wide factor matrix
    summary = fscr.apply_ic_filter(summary)
    fac_indexed = fac.set_index(["date", "symbol"])
    summary = fscr.prune_correlated(fac_indexed, summary)

    # 3. Plots + report
    REPORTS.mkdir(parents=True, exist_ok=True)
    surv = summary.index[summary["passes_corr"]].tolist()
    heat = REPORTS / f"{args.asset}_corr.png"
    if len(surv) >= 2:
        make_corr_heatmap(fac_indexed[surv].corr(method="spearman"), heat)
    else:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "no survivors", ha="center")
        fig.savefig(heat)
        plt.close(fig)

    ic_png = REPORTS / f"{args.asset}_rolling_ic.png"
    make_rolling_ic_plot(daily_ics, summary, top_k=min(8, len(summary)),
                         out_path=ic_png, window=ppy // 4)

    out_md = REPORTS / f"{args.asset}_factor_report.md"
    write_report(args.asset, summary, panel, args.horizon,
                 out_md, heat, ic_png, n_candidates=len(summary))

    summary.to_csv(REPORTS / f"{args.asset}_factor_summary.csv")
    print(f"Summary saved: {REPORTS / f'{args.asset}_factor_summary.csv'}")


if __name__ == "__main__":
    main()
