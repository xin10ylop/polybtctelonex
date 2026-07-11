"""The 'cheap + signal' edge (2026-07-11) — the one structure that holds.

Reframe: six passes proved you can't predict window DIRECTION much above 53%.
But EV is not win rate — it is win rate vs the ENTRY PRICE. Decomposing win
rate by the signal-side ask (nix_scalp6_rows) showed the book is efficient
minus fees at every price EXCEPT one interaction:

  When the book prices a side CHEAP (ask<0.50) AND the boundary oracle-lag
  signal independently says that side just moved up (|z|>=0.05), you win ~51.5%
  at a ~0.47 entry -> +6% per trade from PRICE LEVERAGE, not direction skill.

  The same cheap sides WITHOUT signal confirmation win only 44.5% (t=-3.1):
  cheap-without-signal is toxic (deserved), cheap-with-signal is a mispricing.
  The signal's job is to DISCRIMINATE mispriced-cheap from toxic-cheap.

Significance (honest, daily unit of independence, 5m 90 days):
  daily-EV t=2.47, p=0.016; win rate identical TRAIN(51.1) vs VAL(51.1);
  positive every month; fresh Jul6-8 +$0.68/tr. Pooled with 15m the daily test
  is p=0.34 (15m era dilutes). CAVEATS: not pre-registered (multiple passes ->
  discount the p); fill capacity at <0.50 unverified (uses recorded ToB ask).

Reproduces on results/nix_scalp6_rows.parquet.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats


def pnl(d: pl.DataFrame) -> np.ndarray:
    a = d["ask"].to_numpy(); w = d["win"].to_numpy().astype(float); r = d["rate"].to_numpy()
    sh = 10.0 / a
    return sh * w - 10.0 - r * a * (1 - a) * sh


def report(d: pl.DataFrame, label: str) -> None:
    d = d.with_columns(pl.Series("pnl", pnl(d)))
    daily = d.group_by("date").agg(pl.col("pnl").mean().alias("ev")).sort("date")
    dv = daily["ev"].to_numpy()
    t, p = stats.ttest_1samp(dv, 0) if len(dv) > 2 else (float("nan"), float("nan"))
    print(f"{label}: n={len(d)} over {len(dv)}d, wr {d['win'].mean():.1%}, "
          f"avg ask ${d['ask'].mean():.3f}, EV ${d['pnl'].mean():+.3f}/tr "
          f"(+{d['pnl'].mean()/10*100:.1f}%), daily t={t:+.2f} p={p:.3f}")


def main() -> None:
    df = pl.read_parquet("results/nix_scalp6_rows.parquet").filter(pl.col("t0") == -0.5)
    dev = df.filter(pl.col("date") <= "2026-05-12")
    cheap_sig = (pl.col("ask") < 0.50) & (pl.col("absz") >= 0.05)

    print("=== THE EDGE: cheap side + signal confirmation ===")
    report(dev.filter((pl.col("family") == "5m") & cheap_sig), "5m  cheap+signal")
    report(dev.filter((pl.col("family") == "15m") & cheap_sig), "15m cheap+signal")
    report(dev.filter(cheap_sig), "POOLED cheap+signal")

    print("\n=== the discrimination (why the signal matters within cheap) ===")
    report(dev.filter((pl.col("ask") < 0.50) & (pl.col("absz") < 0.05)),
           "cheap WITHOUT signal (toxic)")

    print("\n=== forward stability (5m, cheap+signal) ===")
    c5 = dev.filter((pl.col("family") == "5m") & cheap_sig)
    report(c5.filter(pl.col("mo") <= "2026-03"), "  TRAIN Feb-Mar")
    report(c5.filter(pl.col("mo") >= "2026-04"), "  VALID Apr-May")
    fr = df.filter((pl.col("date") >= "2026-07-06") & (pl.col("family") == "5m") & cheap_sig)
    if len(fr):
        report(fr, "  FRESH Jul6-8")

    print("\nNIX_CHEAPSIG DONE")


if __name__ == "__main__":
    main()
