"""Phase 4 — validation gauntlet over all Phase 3 leaderboards.

Filters (run brief): (1) >=300 val trades; (2) val per-trade t>=3 AND pf>=1.15;
(3) val maxDD <= 35% of working capital (20x notional); (4) val mean >= 50% of
train mean, same sign; (5) multiple-testing deflation: |t| >= sqrt(2 ln M).
Filters 6-10 (bootstrap, plateau, regime, fee stress, capacity) apply only to
configs surviving 1-5. Writes reports/phase4_gauntlet.md with the funnel,
IS-vs-OOS correlation, and per-family survival.
"""
from __future__ import annotations

import datetime as dt
import glob
import math

import polars as pl

FILES = sorted(glob.glob("results/grid_*.parquet"))


def main() -> None:
    frames = []
    for f in FILES:
        g = pl.read_parquet(f)
        g = g.with_columns(pl.lit(f.split("/")[-1]).alias("src"))
        frames.append(g)
    g = pl.concat(frames, how="diagonal")
    g = g.filter(pl.col("train_n").is_not_null() & pl.col("val_n").is_not_null())
    M = len(g)
    t_deflate = math.sqrt(2 * math.log(max(M, 2)))

    funnel = [("all configs evaluated", M)]
    s = g.filter(pl.col("val_n") >= 300)
    funnel.append(("(1) >=300 validation trades", len(s)))
    s = s.filter((pl.col("val_t") >= 3.0) & (pl.col("val_pf") >= 1.15))
    funnel.append(("(2) val t>=3 AND pf>=1.15", len(s)))
    s = s.filter(pl.col("val_maxdd") <= 0.35 * 20 * pl.col("notional"))
    funnel.append(("(3) val maxDD <= 35% of 20x notional", len(s)))
    s = s.filter((pl.col("train_mean") > 0)
                 & (pl.col("val_mean") >= 0.5 * pl.col("train_mean")))
    funnel.append(("(4) val >= 50% of train, same sign", len(s)))
    s = s.filter(pl.col("val_t") >= t_deflate)
    funnel.append((f"(5) deflated significance t>={t_deflate:.2f} (M={M})", len(s)))

    # IS vs OOS diagnostics
    d = g.filter((pl.col("train_n") >= 300) & (pl.col("val_n") >= 100))
    corr = d.select(pl.corr("train_mean", "val_mean")).item()
    top_decile = d.sort("train_t", descending=True).head(max(len(d) // 10, 1))
    td_val = top_decile["val_mean"].mean()
    pos_val_share = float((d["val_mean"] > 0).mean())

    fam = (g.with_columns(
            (pl.col("val_n") >= 300).alias("f1"),
            ((pl.col("val_t") >= 3) & (pl.col("val_pf") >= 1.15)).alias("f2"))
           .group_by("tag")
           .agg(pl.len().alias("configs"),
                pl.col("f1").sum().alias("pass_n300"),
                (pl.col("f1") & pl.col("f2")).sum().alias("pass_t3"),
                pl.col("val_t").max().alias("best_val_t"),
                pl.col("val_pf").max().alias("best_val_pf"),
                pl.col("val_n").max().alias("max_val_n"))
           .sort("best_val_t", descending=True))

    lines = [
        "# Phase 4 — Validation Gauntlet",
        "",
        f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. "
        f"Sources: {', '.join(f.split('/')[-1] for f in FILES)}.",
        "All results post-fee (date-correct regimes) + real book-walk slippage, "
        "250ms latency unless tagged otherwise. Flat $-notional per trade.",
        "",
        "## The funnel",
        "",
        "| filter | configs remaining |",
        "|---|---|",
    ]
    for name, n in funnel:
        lines.append(f"| {name} | {n:,} |")
    lines += [
        "",
        "## In-sample vs out-of-sample diagnostics",
        "",
        f"- corr(train mean P&L, val mean P&L) across {len(d):,} adequately-sized configs: "
        f"**{corr:.3f}**",
        f"- top train-decile configs' average VAL mean per trade: **${td_val:.2f}**",
        f"- share of configs with positive val mean: **{pos_val_share:.1%}**",
        "",
        "## Per-family survival",
        "",
        "| family tag | configs | val n>=300 | + t>=3&pf>=1.15 | best val t | best val pf | max val n |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in fam.iter_rows(named=True):
        lines.append(f"| {r['tag']} | {r['configs']} | {r['pass_n300']} | {r['pass_t3']} | "
                     f"{r['best_val_t']:.2f} | {r['best_val_pf']:.2f} | {r['max_val_n']} |")
    survivors = s
    lines += ["", "## Verdict", ""]
    if len(survivors) == 0:
        lines.append(
            "**ZERO configurations survive the gauntlet.** Filters 6–10 (bootstrap, "
            "parameter plateau, regime robustness, fee stress, capacity) were not "
            "reached — no candidate cleared filters 1–5. Per Hard Rule 4 this is a "
            "valid outcome; see FINAL_REPORT.md.")
    else:
        lines.append(f"{len(survivors)} candidates proceed to filters 6-10:")
        for r in survivors.head(10).iter_rows(named=True):
            lines.append(f"- {r['tag']} {r['entry']} exit={r['exit']} "
                         f"val_t={r['val_t']} pf={r['val_pf']} n={r['val_n']}")
        survivors.write_parquet("results/gauntlet_candidates.parquet")
    with open("reports/phase4_gauntlet.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(f"{k}: {v}" for k, v in funnel))
    print(f"IS/OOS corr={corr:.3f}, survivors={len(survivors)}")


if __name__ == "__main__":
    main()
