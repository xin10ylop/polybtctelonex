"""Does nix2's edge track FEE EPOCHS or calendar time?

The reconstruction split Feb12-Mar28 (wr 49.1%, EV -$0.06) vs Mar29-May12
(wr 55.6%, EV +$1.31). That boundary sits within two days of the Mar 30 taker
fee change (0.0624 -> 0.072), so the two explanations are confounded.

The decisive statistic is WIN RATE, which is completely independent of the fee
level -- fees change what a win pays, never whether you win. So:

  * if win rate STEPS at the fee change -> something real changed in the
    market (plausible mechanism: a higher taker fee pushes makers to quote
    wider, and a wider book is what nix2 harvests);
  * if win rate is flat and only EV moves -> it was pure fee accounting and
    the "edge appeared" story is wrong;
  * if win rate drifts smoothly -> it is calendar/regime noise, not the fee.

Also recomputes P&L with the DATE-CORRECT fee (the reconstruction used a flat
0.07 everywhere, which overcharges the 0.0624 epoch), and measures the actual
book spread per epoch as the mechanism check.

  .venv/bin/python src/nix_feeregime.py
"""
from __future__ import annotations

import glob
import math
import os

import polars as pl

RECON = "data/processed/nix2_recon.parquet"
WIN = "data/processed/windows.parquet"
QU = "data/processed/daily/5m/quotes"


def wilson(k: int, n: int) -> tuple[float, float]:
    """95% CI for a proportion — small samples need it."""
    if n == 0:
        return (float("nan"), float("nan"))
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main() -> None:
    t = pl.read_parquet(RECON)
    w = pl.read_parquet(WIN).filter(pl.col("family") == "5m")
    fee_by_date = dict(zip(w["date"].to_list(), w["fee_rate"].to_list()))
    t = t.with_columns(
        pl.col("date").replace_strict(fee_by_date, default=None).alias("fee"))

    # Rule 3: fees always on, and DATE-CORRECT. The reconstruction charged a
    # flat 0.07; recompute each trade at the fee actually in force that day.
    t = t.with_columns(
        (pl.col("pnl")
         + 0.07 * pl.col("ask") * (1 - pl.col("ask")) * (10.0 / pl.col("ask"))
         - pl.col("fee") * pl.col("ask") * (1 - pl.col("ask")) * (10.0 / pl.col("ask"))
         ).alias("pnl_correct"))

    print("=== win rate by fee epoch (win rate is FEE-INDEPENDENT) ===")
    for fee, sub in sorted(t.group_by("fee"), key=lambda x: x[0][0] or 0):
        f = fee[0]
        n = sub.height
        k = int(sub["won"].sum())
        lo, hi = wilson(k, n)
        ev = sub["pnl_correct"].mean()
        d0, d1 = sub["date"].min(), sub["date"].max()
        print(f"  fee {f:.4f}  {d0}..{d1}  n={n:>4}  "
              f"wr {k/n:6.2%} [{lo:.1%},{hi:.1%}]  EV ${ev:+.3f}")

    # is the change a STEP at Mar 30, or a smooth drift?
    print("\n=== biweekly: step at the fee change, or gradual drift? ===")
    t = t.with_columns(
        pl.col("date").str.strptime(pl.Date, "%Y-%m-%d").alias("d"))
    t = t.with_columns(
        ((pl.col("d") - pl.col("d").min()).dt.total_days() // 14).alias("blk"))
    for blk, sub in sorted(t.group_by("blk"), key=lambda x: x[0][0]):
        n = sub.height
        k = int(sub["won"].sum())
        lo, hi = wilson(k, n)
        mark = "  <-- fee 0.0624 -> 0.072" if sub["date"].min() <= "2026-03-30" <= sub["date"].max() else ""
        print(f"  {sub['date'].min()}..{sub['date'].max()}  n={n:>3}  "
              f"wr {k/n:6.2%} [{lo:5.1%},{hi:5.1%}]  "
              f"EV ${sub['pnl_correct'].mean():+.3f}{mark}")

    # MECHANISM: did the book actually widen when the fee rose?
    print("\n=== mechanism: median touch spread near the open, by epoch ===")
    qd = sorted(glob.glob(f"{QU}/*.parquet"))
    acc: dict[float, list[float]] = {}
    for p in qd:
        d = os.path.basename(p)[:-8]
        fee = fee_by_date.get(d)
        if fee is None:
            continue
        q = pl.read_parquet(p, columns=["local_timestamp_us", "wts",
                                        "bid_price", "ask_price"])
        # quotes within 10s before each window open
        q = q.filter(
            (pl.col("local_timestamp_us") <= pl.col("wts") * 1_000_000)
            & (pl.col("local_timestamp_us") >= pl.col("wts") * 1_000_000 - 10_000_000)
            & pl.col("bid_price").is_not_null() & pl.col("ask_price").is_not_null())
        if q.height:
            acc.setdefault(fee, []).extend(
                (q["ask_price"] - q["bid_price"]).to_list())
    for fee in sorted(acc):
        v = sorted(acc[fee])
        if not v:
            continue
        med = v[len(v) // 2]
        print(f"  fee {fee:.4f}: median spread {med:.4f}  n={len(v):,}")

    print("\n=== verdict ===")
    e = {f[0]: s for f, s in t.group_by("fee")}
    if 0.0624 in e and 0.072 in e:
        a, b = e[0.0624], e[0.072]
        ka, na = int(a["won"].sum()), a.height
        kb, nb = int(b["won"].sum()), b.height
        pa, pb = ka / na, kb / nb
        pp = (ka + kb) / (na + nb)
        se = math.sqrt(pp * (1 - pp) * (1 / na + 1 / nb))
        z = (pb - pa) / se if se > 0 else float("nan")
        print(f"  win-rate step across the Mar 30 fee change: "
              f"{pa:.2%} -> {pb:.2%}  (z={z:+.2f})")
        print("  -> " + ("REAL market change, not fee accounting"
                         if abs(z) > 1.96 else
                         "NOT significant — cannot distinguish from noise"))


if __name__ == "__main__":
    main()
