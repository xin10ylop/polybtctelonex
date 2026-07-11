"""Diagnostic decomposition of the boundary signal's win rate (2026-07-11).

User ask: think deep — where does the win rate fail, what drops it, what
lifts it, is any of it an enforceable parameter/pattern? Discipline: a
candidate condition must show an edge on a TRAIN slice AND confirm on a later
VALIDATION slice; in-sample-only patterns are data-mining, not results.

Runs on the cached results/nix_scalp6_rows.parquet (t0=-0.5, dev<=May12).
"""
from __future__ import annotations

import polars as pl

BE = 0.518  # pure-hold breakeven win rate at ~0.51 entry


def wr(d: pl.DataFrame, label: str) -> None:
    if len(d) < 30:
        print(f"  {label}: n<30"); return
    w = d["win"].mean(); n = len(d); se = (w * (1 - w) / n) ** 0.5
    verdict = "ABOVE" if w - 1.96 * se > BE else ("at/below" if w < BE else "spans")
    print(f"  {label}: n={n:>5} wr {w:.1%} (95% CI {100*(w-1.96*se):.1f}-"
          f"{100*(w+1.96*se):.1f}) vs breakeven {BE:.1%} -> {verdict}")


def main() -> None:
    df = pl.read_parquet("results/nix_scalp6_rows.parquet").filter(
        (pl.col("t0") == -0.5) & (pl.col("date") <= "2026-05-12"))

    print("WHAT DROPS THE PERCENTAGE (win rate by |z| bin, both families):")
    b = df.with_columns(pl.when(pl.col("absz") < 0.05).then(pl.lit("<.05"))
          .when(pl.col("absz") < 0.10).then(pl.lit(".05-.10"))
          .when(pl.col("absz") < 0.20).then(pl.lit(".10-.20"))
          .when(pl.col("absz") < 0.40).then(pl.lit(".20-.40"))
          .otherwise(pl.lit(".40+ (calm-market spike)")).alias("zb"))
    for r in b.group_by("zb").agg(pl.len().alias("n"),
              pl.col("win").mean().round(3).alias("wr"),
              pl.col("sig").mean().round(1).alias("sig")).sort("zb").iter_rows(named=True):
        print(f"  |z| {r['zb']:<24} n={r['n']:>6} wr {r['wr']:.1%} sig~{r['sig']}")
    print("  -> |z|>=.40 in calm markets (low sig, big spike) REVERTS: signal inverts.")

    print("\nENFORCEABILITY TEST (5m, |z|>=0.05, train Feb-Mar -> validate Apr-May):")
    d5 = df.filter((pl.col("family") == "5m") & (pl.col("absz") >= 0.05))
    wr(d5.filter(pl.col("mo").is_in(["2026-02", "2026-03"])), "TRAIN Feb-Mar ")
    wr(d5.filter(pl.col("mo").is_in(["2026-04", "2026-05"])), "VALID Apr-May ")

    print("\nMonth trend (5m |z|>=.05) — emerging edge or drift?:")
    for r in d5.group_by("mo").agg(pl.len().alias("n"),
              pl.col("win").mean().round(3).alias("wr")).sort("mo").iter_rows(named=True):
        print(f"  {r['mo']}: n={r['n']:>4} wr {r['wr']:.1%}")

    print("\nDEAD conditioning variables (no lift, for the record):")
    for col, expr, lab in (
        ("momentum", pl.col("bret_5s") > 0, "5s Binance move agrees w/ signal"),
        ("book", pl.col("q_imb") > 0.1, "book imbalance agrees w/ signal")):
        a = df.filter(expr)["win"].mean(); c = df.filter(~expr)["win"].mean()
        print(f"  {lab}: agree {a:.1%} vs not {c:.1%}  (delta {100*(a-c):+.1f}pp)")


if __name__ == "__main__":
    main()
