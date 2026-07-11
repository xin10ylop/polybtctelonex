"""Appendix 11 judgment — multicoin campaign (97 days, 5 coins x {5m,15m}).

Reads results/mc/*.parquet gate-monitor rows (frozen nix1 params, one row per
window). Prints every table the appendix needs:
  1. Monthly economics under three fill conventions:
       A  book-walk $50 ($5 stake at walked ask)          col pnl
       B  tape-validated (print <= ask+1c within 1.5s)    col pnl_tape
       C  $5 top-of-book bracket (needs tob_usd >= 5)     recomputed here
  2. Ask-bucket win rates vs structural breakevens (cheap/mid/rich).
  3. FROZEN DEPLOYMENT STACK on convention C: basis guard + calibrated EV
     gate (bot/calibration.json). Deploy bar: clearly positive Jun1-Jul7
     (months unseen when the stack was frozen 2026-07-09) else NO DEPLOY.
  4. Calibration transfer: frozen BTC wr-vs-|z| bins vs realized alt wr.
  5. Basis-guard event analysis (cross-coin, counterfactual pnl).
  6. Concentration / tail risk of the stack's daily pnl.
  7. Bankroll projections from LATEST-month rates + real ToB depth.
"""
from __future__ import annotations

import glob
import json
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees

STAKE = 5.0
CAL = json.load(open("bot/calibration.json"))["bins"]
FREEZE_OOS_LO = "2026-06-01"  # months unseen at freeze


def wr_cal(z_abs: float) -> float:
    for b in CAL:
        if b["z_lo"] <= z_abs < b["z_hi"]:
            return b["wr"]
    return float("nan")


def load() -> pl.DataFrame:
    df = pl.concat([pl.read_parquet(p) for p in sorted(glob.glob("results/mc/*.parquet"))])
    df = df.filter(pl.col("gate") == "pass").with_columns(
        pl.col("date").str.slice(0, 7).alias("mo"),
        (pl.col("z") > 0).alias("dir_up"))
    df = df.with_columns(
        pl.when(pl.col("dir_up")).then(pl.col("up_won"))
          .otherwise(~pl.col("up_won")).alias("win"))
    # convention C: $5 at top-of-book, needs $5 of size resting there
    rate = pl.col("date").map_elements(
        lambda d: fees.params(d, "5m")[0], return_dtype=pl.Float64)
    # (5m/15m share the same regime schedule; verified on-chain per coin)
    shares = STAKE / pl.col("tob_ask")
    fee = shares * rate * pl.col("tob_ask") * (1 - pl.col("tob_ask"))
    df = df.with_columns(
        pl.when((pl.col("tob_usd") >= STAKE) & (pl.col("tob_ask") < 0.999))
          .then(shares * pl.col("win").cast(pl.Float64) - STAKE - fee)
          .otherwise(None).alias("pnl_tob"))
    # frozen stack: basis guard + calibrated EV gate on the walked ask
    zabs = pl.col("z").abs()
    wcal = zabs.map_elements(wr_cal, return_dtype=pl.Float64)
    feew = rate * pl.col("wask") * (1 - pl.col("wask"))
    df = df.with_columns(
        wcal.alias("wr_cal"),
        (~((pl.col("ask") < 0.5) & (pl.col("basis_bp").abs() > 5.0))).alias("basis_ok"),
        ((wcal - pl.col("wask") - feew) >= 0.02).alias("cal_ok"))
    return df.with_columns((pl.col("basis_ok") & pl.col("cal_ok")).alias("stack_ok"))


def monthly(df: pl.DataFrame, col: str, label: str, by_coin: bool = False) -> None:
    keys = ["mo", "coin"] if by_coin else ["mo"]
    t = (df.filter(pl.col(col).is_not_null())
           .group_by(keys).agg(
               pl.len().alias("n"), pl.col("win").mean().round(3).alias("wr"),
               pl.col(col).sum().round(1).alias("tot$"),
               pl.col("date").n_unique().alias("days"))
           .with_columns((pl.col("tot$") / pl.col("days")).round(2).alias("$/day"))
           .sort(keys))
    print(f"\n--- {label} ---")
    print(t.to_pandas().to_string(index=False))


def main() -> None:
    df = load()
    ndays = df["date"].n_unique()
    print(f"pass windows: {len(df)} over {ndays} days, "
          f"{df['coin'].n_unique()} coins x {df['fam'].n_unique()} fams")

    print("\n================ 1. MONTHLY, THREE CONVENTIONS ================")
    monthly(df, "pnl", "A  book-walk $50, $5 stake")
    monthly(df, "pnl_tape", "B  tape-validated")
    monthly(df, "pnl_tob", "C  $5 top-of-book bracket")
    monthly(df, "pnl_tob", "C by coin", by_coin=True)

    print("\n================ 2. ASK BUCKETS (convention C) ================")
    d = df.filter(pl.col("pnl_tob").is_not_null()).with_columns(
        pl.when(pl.col("tob_ask") < 0.5).then(pl.lit("cheap<.50"))
          .when(pl.col("tob_ask") < 0.7).then(pl.lit("mid .5-.7"))
          .otherwise(pl.lit("rich .7+")).alias("bucket"))
    t = (d.group_by("mo", "bucket").agg(
            pl.len().alias("n"), pl.col("win").mean().round(3).alias("wr"),
            pl.col("tob_ask").mean().round(3).alias("avg_ask"),
            pl.col("pnl_tob").sum().round(1).alias("tot$"))
          .with_columns((pl.col("avg_ask") + 0.018).round(3).alias("~breakeven"))
          .sort("mo", "bucket"))
    print(t.to_pandas().to_string(index=False))

    print("\n================ 3. FROZEN STACK (C + basis guard + calibrated EV) ================")
    s = df.filter(pl.col("pnl_tob").is_not_null() & pl.col("stack_ok"))
    monthly(s, "pnl_tob", "frozen stack, monthly")
    monthly(s, "pnl_tob", "frozen stack by coin", by_coin=True)
    oos = s.filter(pl.col("date") >= FREEZE_OOS_LO)
    tot = oos["pnl_tob"].sum()
    days = oos["date"].n_unique()
    daily = oos.group_by("date").agg(pl.col("pnl_tob").sum()).sort("date")
    dv = daily["pnl_tob"].to_numpy()
    tstat = dv.mean() / (dv.std(ddof=1) / np.sqrt(len(dv))) if len(dv) > 2 else float("nan")
    print(f"\nDEPLOY BAR (unseen {FREEZE_OOS_LO}..Jul7): n={len(oos)}, "
          f"total ${tot:+.1f} over {days} trade-days, ${tot/max(days,1):+.2f}/day, "
          f"daily t={tstat:.2f}")
    print("VERDICT:", "PASS — clearly positive" if tot > 0 and tstat > 2 else
          "NO DEPLOY — bar not met")

    print("\n================ 4. CALIBRATION TRANSFER (frozen bins vs alt reality) ================")
    zb = df.filter(pl.col("pnl_tob").is_not_null()).with_columns(
        pl.col("z").abs().alias("zabs"))
    for b in CAL:
        seg = zb.filter((pl.col("zabs") >= b["z_lo"]) & (pl.col("zabs") < b["z_hi"]))
        if len(seg) == 0:
            continue
        print(f"  |z| {b['z_lo']:>4}-{b['z_hi']:<6} frozen wr {b['wr']:.3f} | "
              f"alt realized {seg['win'].mean():.3f} (n={len(seg)}, "
              f"avg ask {seg['tob_ask'].mean():.3f})")

    print("\n================ 5. BASIS-GUARD EVENTS ================")
    ev = df.filter((pl.col("ask") < 0.5) & (pl.col("basis_bp").abs() > 5.0)
                   & pl.col("pnl_tob").is_not_null())
    print(f"blocked cheap+basis windows: {len(ev)}; counterfactual pnl "
          f"${ev['pnl_tob'].sum():+.1f}, wr {ev['win'].mean():.3f}" if len(ev)
          else "no blocked windows")
    if len(ev):
        print(ev.group_by("mo").agg(pl.len().alias("n"),
              pl.col("pnl_tob").sum().round(1).alias("cf$")).sort("mo")
              .to_pandas().to_string(index=False))
        same = (ev.group_by("date", "wts").agg(pl.col("coin").n_unique().alias("nc")))
        print("cross-coin same-window events (nc>1):",
              len(same.filter(pl.col("nc") > 1)), "of", len(same))

    print("\n================ 6. CONCENTRATION / TAIL (frozen stack, all months) ================")
    dall = s.group_by("date").agg(pl.col("pnl_tob").sum().alias("d")).sort("date")
    v = dall["d"].to_numpy()
    if len(v):
        cum = np.cumsum(v)
        dd = (np.maximum.accumulate(cum) - cum).max()
        top5 = np.sort(v)[-5:].sum()
        print(f"trade-days {len(v)}, total ${v.sum():+.1f}, mean ${v.mean():+.2f}/day, "
              f"worst day ${v.min():+.1f}, best ${v.max():+.1f}")
        print(f"top-5 days = ${top5:+.1f} ({top5/v.sum()*100 if v.sum()>0 else float('nan'):.0f}% "
              f"of total), max drawdown ${dd:.1f}")

    print("\n================ 7. BANKROLL PROJECTIONS ================")
    ju = s.filter(pl.col("date") >= FREEZE_OOS_LO)
    rate_day = ju["pnl_tob"].sum() / max(ju["date"].n_unique(), 1)
    tob = df.filter(pl.col("stack_ok") & pl.col("tob_usd").is_not_null())["tob_usd"].to_numpy()
    print(f"latest-regime (Jun-Jul) rate at $5 stakes: ${rate_day:+.2f}/day")
    print(f"ToB depth on stack-passing windows: median ${np.median(tob):.0f}, "
          f"p25 ${np.percentile(tob,25):.0f} -> max stake ~= p25 depth, "
          f"max bankroll ~= 20x that")
    for bank in (100, 1000):
        stake = bank / 20
        scale = stake / STAKE
        print(f"  ${bank} bankroll (stake ${stake:.0f}): {rate_day*scale:+.2f}/day "
              f"-> 90d {rate_day*scale*90:+.0f} (linear, latest-regime rate, "
              f"NO capacity/impact beyond ToB check)")
    print("\nMC_JUDGE DONE")


if __name__ == "__main__":
    main()
