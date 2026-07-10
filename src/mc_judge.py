"""NIXULTIMATE 3.0 — frozen-stack judgment (Appendix 11).

Implements EXACTLY the pre-registration written 2026-07-09 ~11:50 UTC (see
reports/mc_campaign_notes.md), before Apr 12 - Jul 5 was seen:

  deployment stack = frozen machine (gate == "pass")
                   + basis guard   (skip if ask < 0.50 and |basis_bp| > 5)
                   + CALIBRATED EV gate (bot/calibration.json wr-vs-|z| bins
                     fitted on BTC dev trades, replacing Phi(z); same 2c margin)

  DEPLOY BAR: the stack must be significantly positive on the UNSEEN
  Apr 12 - Jul 5 days (both fill conventions; tob-$5 variant bracketed)
  or the verdict is NO DEPLOY. Judgment uses the ask-bucket lens
  (cheap < 50c / mid 50-75c / rich >= 75c vs fee-adjusted breakevens).

No parameters here are tunable; this script only aggregates and reports.
Usage: .venv/bin/python src/mc_judge.py [--out reports/mc_judgment.md]
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees

STAKE = 5.0
SEEN_DATES = {"2026-07-06", "2026-07-07"} | {
    (dt.date(2026, 4, 2) + dt.timedelta(days=i)).isoformat() for i in range(10)
}  # Apr 2-11 + Jul 6-7 were seen before the pre-registration froze the stack


def wr_cal_expr(cal: dict) -> pl.Expr:
    """Calibrated win-prob from |z| via the frozen BTC-dev bins."""
    az = pl.col("z").abs()
    expr = pl.lit(None, dtype=pl.Float64)
    for b in reversed(cal["bins"]):
        expr = (
            pl.when((az >= b["z_lo"]) & (az < b["z_hi"]))
            .then(pl.lit(b["wr"]))
            .otherwise(expr)
        )
    return expr


def load() -> pl.DataFrame:
    files = sorted(glob.glob("results/mc/*.parquet"))
    dfs = []
    for f in files:
        d = pl.read_parquet(f)
        if "coin" in d.columns:
            dfs.append(d)
    df = pl.concat(dfs)
    cal = json.load(open("bot/calibration.json"))
    rates = {
        (date, fam): fees.params(date, fam)[0]
        for date in df["date"].unique().to_list()
        for fam in ("5m", "15m")
    }
    rate_df = pl.DataFrame(
        {
            "date": [k[0] for k in rates],
            "fam": [k[1] for k in rates],
            "rate": [rates[k] for k in rates],
        }
    )
    df = df.join(rate_df, on=["date", "fam"], how="left")
    df = df.with_columns(
        wr_cal_expr(cal).alias("wr_cal"),
        pl.col("date").str.slice(0, 7).alias("month"),
        (pl.col("z") > 0).alias("dir_up"),
    )
    df = df.with_columns(
        (
            pl.col("wr_cal")
            - pl.col("ask")
            - pl.col("rate") * pl.col("ask") * (1 - pl.col("ask"))
        ).alias("ev_cal"),
        ((pl.col("ask") < 0.50) & (pl.col("basis_bp").abs() > 5.0)).alias(
            "basis_blocked"
        ),
        # optimistic top-of-book $5 fill (no tape validation): bracketed upper leg
        pl.when((pl.col("tob_ask") > 0.02) & (pl.col("tob_ask") < 0.995)
                & (pl.col("tob_usd") >= STAKE))
        .then(
            (STAKE / pl.col("tob_ask"))
            * (pl.col("dir_up") == pl.col("up_won")).cast(pl.Float64)
            - STAKE
            - (STAKE / pl.col("tob_ask"))
            * pl.col("rate") * pl.col("tob_ask") * (1 - pl.col("tob_ask"))
        )
        .otherwise(None)
        .alias("pnl_tob"),
    )
    # a null basis on a contrarian (ask<0.50) entry cannot clear the guard live
    df = df.with_columns(
        pl.when(pl.col("ask") < 0.50)
        .then(pl.col("basis_blocked").fill_null(True))
        .otherwise(pl.col("basis_blocked").fill_null(False))
        .alias("basis_blocked")
    )
    return df.with_columns(
        (
            (pl.col("gate") == "pass")
            & ~pl.col("basis_blocked")
            & (pl.col("ev_cal") >= 0.02)
        ).alias("stack")
    )


def tstat(x: np.ndarray) -> float:
    if len(x) < 2 or np.std(x, ddof=1) == 0:
        return float("nan")
    return float(np.mean(x) / np.std(x, ddof=1) * math.sqrt(len(x)))


def daily_stats(df: pl.DataFrame, pnl_col: str, dates: list[str]) -> dict:
    """Daily P&L over `dates`, counting no-trade days as $0."""
    per = dict(
        df.filter(pl.col(pnl_col).is_not_null())
        .group_by("date")
        .agg(pl.col(pnl_col).sum())
        .iter_rows()
    )
    daily = np.array([per.get(d, 0.0) for d in dates])
    tr = df.filter(pl.col(pnl_col).is_not_null())[pnl_col].to_numpy()
    return {
        "ndays": len(dates),
        "ntr": len(tr),
        "total": float(daily.sum()),
        "per_day": float(daily.mean()) if len(daily) else float("nan"),
        "t_daily": tstat(daily),
        "per_trade": float(tr.mean()) if len(tr) else float("nan"),
        "t_trade": tstat(tr),
        "wr": float((tr > 0).mean()) if len(tr) else float("nan"),
        "green": float((daily > 0).mean()) if len(daily) else float("nan"),
    }


def fmt(s: dict) -> str:
    return (
        f"n={s['ntr']:4d} | ${s['per_trade']:+6.2f}/tr t={s['t_trade']:+5.1f} | "
        f"${s['per_day']:+7.2f}/day t={s['t_daily']:+5.1f} | "
        f"wr={s['wr']:.0%} green={s['green']:.0%} | total ${s['total']:+9.2f}"
    )


def month_dates(df: pl.DataFrame, month: str) -> list[str]:
    return sorted(df.filter(pl.col("month") == month)["date"].unique().to_list())


def bucket_table(df: pl.DataFrame, pnl_col: str, w) -> list[str]:
    out = []
    sub = df.filter(w & pl.col(pnl_col).is_not_null())
    sub = sub.with_columns(
        pl.when(pl.col("ask") < 0.50).then(pl.lit("cheap<50c"))
        .when(pl.col("ask") < 0.75).then(pl.lit("mid 50-75c"))
        .otherwise(pl.lit("rich>=75c")).alias("bucket")
    )
    for b in ("cheap<50c", "mid 50-75c", "rich>=75c"):
        g = sub.filter(pl.col("bucket") == b)
        if g.is_empty():
            out.append(f"  {b:11s}: n=0")
            continue
        pnl = g[pnl_col].to_numpy()
        wr = float((pnl > 0).mean())
        mask = float(g["ask"].mean())
        rate = float(g["rate"].mean())
        be = mask + rate * mask * (1 - mask)  # wr needed to break even at mean ask
        share = len(g) / max(len(sub), 1)
        out.append(
            f"  {b:11s}: n={len(g):4d} ({share:4.0%}) wr={wr:.1%} vs BE {be:.1%} "
            f"| mean ask {mask:.2f} | ${pnl.mean():+6.2f}/tr | total ${pnl.sum():+8.2f}"
        )
    return out


def main() -> None:
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv \
        else "reports/mc_judgment.md"
    df = load()
    all_dates = sorted(df["date"].unique().to_list())
    months = sorted(df["month"].unique().to_list())
    L = []
    L.append("# NIXULTIMATE 3.0 — frozen-stack judgment (pre-registered)")
    L.append(f"\nGenerated {dt.datetime.utcnow().isoformat()}Z over "
             f"{len(all_dates)} days ({all_dates[0]} .. {all_dates[-1]}), "
             f"{len(df)} window-rows.")
    n_pass = int((df["gate"] == "pass").sum())
    n_stack = int(df["stack"].sum())
    L.append(f"\nFrozen machine fired {n_pass} times; stack (basis guard + "
             f"calibrated EV gate) keeps {n_stack}.")

    stack = df.filter(pl.col("stack"))
    for label, pcol in (("A. conservative $50-mirror book-walk", "pnl"),
                        ("B. tape-validated", "pnl_tape"),
                        ("C. top-of-book $5 (optimistic bracket)", "pnl_tob")):
        L.append(f"\n## Fill convention {label}\n")
        L.append("### Stack, monthly x coin ($5 stakes)\n```")
        for m in months:
            mdates = month_dates(df, m)
            s = daily_stats(stack.filter(pl.col("month") == m), pcol, mdates)
            L.append(f"{m} ALL   {fmt(s)}")
            for coin in ("eth", "sol", "xrp", "bnb", "doge"):
                cs = daily_stats(
                    stack.filter((pl.col("month") == m) & (pl.col("coin") == coin)),
                    pcol, mdates)
                L.append(f"  {coin:4s}      {fmt(cs)}")
        L.append("```")
        L.append("\n### Ask-bucket decomposition (stack), by month\n```")
        for m in months:
            L.append(f"{m}:")
            L += bucket_table(stack, pcol, pl.col("month") == m)
        L.append("```")

    # ---- deploy bar ----
    unseen = [d for d in all_dates if d not in SEEN_DATES]
    junjul = [d for d in unseen if d >= "2026-06-01"]
    jun12 = [d for d in unseen if d >= "2026-06-12"]
    L.append("\n## DEPLOY BAR (pre-registered)\n```")
    for tag, dset in (("UNSEEN Apr12-Jul5", unseen),
                      ("Jun1-Jul5 (recent)", junjul),
                      ("Jun12-Jul5 (most recent)", jun12)):
        sub = stack.filter(pl.col("date").is_in(dset))
        for label, pcol in (("walk", "pnl"), ("tape", "pnl_tape"),
                            ("tob$5", "pnl_tob")):
            s = daily_stats(sub, pcol, dset)
            L.append(f"{tag:26s} [{label:5s}] {fmt(s)}")
        L.append("")
    L.append("```")

    # raw machine reference (no overlays) on unseen days
    raw = df.filter(pl.col("gate") == "pass")
    L.append("\n## Reference: raw frozen machine (no overlays), unseen days\n```")
    for label, pcol in (("walk", "pnl"), ("tape", "pnl_tape"), ("tob$5", "pnl_tob")):
        s = daily_stats(raw.filter(pl.col("date").is_in(unseen)), pcol, unseen)
        L.append(f"raw [{label:5s}] {fmt(s)}")
    L.append("```")

    # gate diagnostics by month (fill-convention artifact context)
    L.append("\n## Gate mix by month (all windows)\n```")
    gd = (df.group_by("month", "gate").agg(pl.len())
          .pivot(values="len", index="month", on="gate")
          .sort("month"))
    L.append(str(gd))
    L.append("```")

    os.makedirs("reports", exist_ok=True)
    open(out_path, "w").write("\n".join(L) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
