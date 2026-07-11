"""Bankroll projection audit for the pre-registered multicoin variant
(raw frozen signal + basis guard, NO calibration gate) — 2026-07-11.

Rates come ONLY from the unseen current-regime window (2026-06-01..07-07,
the same window that selected this variant post-hoc — the one-shot on
post-Jul-7 days must still validate it; see FINAL_REPORT.md Appendix 11).

Fill model (stake-dependent, from real per-trade book state):
  min(stake, tob_usd) fills at the touch (tob_ask); the remainder fills at
  the implied beyond-ToB price recovered from the recorded $50-walk average
  (col `fill`), clipped to [tob_ask, 0.999]. Data envelope ends at $50/trade
  -> max modellable bankroll = 20 x $50 = $1,000.

Outputs: capacity curve $/day vs stake, chronological compounding sim from
$100 (stake = bankroll/20 daily), rolling 7-day distribution, extrapolated
days-to-max. Audit checks: baseline reproduces mc_judge (+$4.81/day strict
ToB at $5), one trade hand-verified.
"""
from __future__ import annotations

import glob
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees


def load_unseen() -> pl.DataFrame:
    df = pl.concat([pl.read_parquet(p) for p in sorted(glob.glob("results/mc/*.parquet"))])
    df = df.filter(pl.col("gate") == "pass").with_columns((pl.col("z") > 0).alias("du"))
    df = df.with_columns(
        pl.when(pl.col("du")).then(pl.col("up_won")).otherwise(~pl.col("up_won")).alias("win"),
        pl.col("date").map_elements(lambda d: fees.params(d, "5m")[0],
                                    return_dtype=pl.Float64).alias("rate"),
        (~((pl.col("ask") < 0.5) & (pl.col("basis_bp").abs() > 5.0))).alias("basis_ok"))
    u = df.filter((pl.col("date") >= "2026-06-01") & pl.col("basis_ok")
                  & pl.col("tob_ask").is_finite() & (pl.col("tob_ask") < 0.999)
                  & pl.col("tob_usd").is_not_null()).sort("date", "wts")
    return u.with_columns(((5.0 / pl.col("tob_ask")) * pl.col("win").cast(pl.Float64) - 5.0
                           - (5.0 / pl.col("tob_ask")) * pl.col("rate")
                           * pl.col("tob_ask") * (1 - pl.col("tob_ask"))).alias("pnl5"))


def main() -> None:
    u = load_unseen()
    ta = u["tob_ask"].to_numpy(); tu = u["tob_usd"].to_numpy()
    wk = u["fill"].to_numpy(); win = u["win"].to_numpy().astype(float)
    rt = u["rate"].to_numpy(); dates = u["date"].to_numpy()
    sh50 = 50.0 / wk
    shtf = np.minimum(tu, 50.0) / ta
    rest_usd = np.maximum(50.0 - tu, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        p_rest = np.where(rest_usd > 0.5,
                          rest_usd / np.maximum(sh50 - shtf, 1e-9), ta)
    p_rest = np.clip(p_rest, ta, 0.999)

    def trade_pnl(S: float) -> np.ndarray:
        S = min(S, 50.0)
        at = np.minimum(S, tu); rr = S - at
        sh = at / ta + np.where(rr > 0, rr / p_rest, 0.0)
        spent = at + rr
        avgp = spent / np.maximum(sh, 1e-12)
        fee = sh * rt * avgp * (1 - avgp)
        return np.where((tu >= 1.0) & np.isfinite(avgp) & (avgp < 0.999),
                        sh * win - spent - fee, np.nan)

    nd = u["date"].n_unique()
    base = u.filter(pl.col("tob_usd") >= 5.0)
    print(f"AUDIT baseline strict-ToB $5: ${base['pnl5'].sum()/nd:+.2f}/day "
          f"(mc_judge decomposition: +$4.81)")
    p5 = u["pnl5"].to_numpy()
    print("\nstake | $/day blended | $/day strict-ToB")
    curve = {}
    for S in (5, 7.5, 10, 15, 20, 30, 40, 50):
        curve[S] = float(np.nansum(trade_pnl(S)) / nd)
        strict = p5[tu >= S].sum() * (S / 5) / nd
        print(f" ${S:>4} | ${curve[S]:+8.2f} | ${strict:+8.2f}")

    ud = sorted(set(dates))
    bank, path = 100.0, []
    for d in ud:
        S = max(min(bank / 20.0, 50.0), 1.0)
        day = float(np.nansum(trade_pnl(S)[dates == d]))
        bank += day
        path.append((d, S, day, bank))
    print(f"\ncompounding $100, stake=bank/20 daily: week1 ${path[6][3]:.2f}, "
          f"end {ud[-1]} ${bank:.2f}")
    dv = np.array([p[2] for p in path])
    cum = np.cumsum(dv)
    print(f"daily mean ${dv.mean():+.2f} sd ${dv.std(ddof=1):.2f} "
          f"worst ${dv.min():+.2f}; max drawdown ${(np.maximum.accumulate(cum)-cum).max():.2f}")

    d5 = np.array([float(np.nansum(trade_pnl(5.0)[dates == d])) for d in ud])
    roll = np.array([d5[i:i + 7].sum() for i in range(len(d5) - 6)])
    print(f"7-day windows at $5 stakes: median ${np.median(roll):+.2f}, "
          f"worst ${roll.min():+.2f}, best ${roll.max():+.2f}, "
          f"positive {(roll > 0).mean():.0%} of {len(roll)}")

    Ss = np.array(sorted(curve)); gs = np.array([curve[s] for s in Ss])
    b, day, marks = 100.0, 0, {}
    while b < 1000.0 and day < 2000:
        b += float(np.interp(min(b / 20.0, 50.0), Ss, gs)); day += 1
        for m in (250, 500, 1000):
            if b >= m and m not in marks:
                marks[m] = day
    print(f"extrapolation: $250 ~{marks.get(250)}d, $500 ~{marks.get(500)}d, "
          f"$1000 (max, $50 stakes) ~{marks.get(1000)}d at ${curve[50]:+.2f}/day there")
    print("\nMC_BANKROLL DONE")


if __name__ == "__main__":
    main()
