"""Capacity check for the cheap+signal edge (2026-07-11).

The EV assumes you get filled at the recorded top-of-book ask (<0.50). Cheap
sides can be thin -> if $10 doesn't rest there, the edge is a paper mirage.
This reloads bookcurves for every 5m cheap+signal window and measures the
REAL depth at the signal-side touch (ToB $), plus the fill price for a $50
book-walk (buy_avgpx_50), at the actual fill time T0+250ms.
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader

T0OFF = -0.5
LAT = 250_000


def main() -> None:
    rows = pl.read_parquet("results/nix_scalp6_rows.parquet").filter(
        (pl.col("t0") == T0OFF) & (pl.col("family") == "5m")
        & (pl.col("date") <= "2026-05-12")
        & (pl.col("ask") < 0.50) & (pl.col("absz") >= 0.05))
    print(f"cheap+signal 5m windows: {len(rows)}")
    out = []
    for date, grp in rows.group_by("date"):
        date = date[0] if isinstance(date, tuple) else date
        try:
            b = (loader.load_daily("5m", "bookcurves", [date]).collect()
                 .sort("wts", "timestamp_us"))
        except FileNotFoundError:
            continue
        bw = b["wts"].to_numpy(); bts = b["timestamp_us"].to_numpy()
        bid0 = b["bid_p0"].to_numpy().astype(np.float64)
        ask0 = b["ask_p0"].to_numpy().astype(np.float64)
        bsz = b["bid_s0"].to_numpy().astype(np.float64)
        asz = b["ask_s0"].to_numpy().astype(np.float64)
        # $50 book-walk avg price on buy(ask) and sell(bid) sides
        bwalk = b["buy_avgpx_50"].to_numpy().astype(np.float64)
        swalk = b["sell_avgpx_50"].to_numpy().astype(np.float64)
        bwsh = b["buy_shares_50"].to_numpy().astype(np.float64)
        swsh = b["sell_shares_50"].to_numpy().astype(np.float64)
        for r in grp.iter_rows(named=True):
            w_ = r["wts"]; side = r["side"]
            T = w_ * 1_000_000 + int(T0OFF * 1_000_000) + LAT
            lo = np.searchsorted(bw, w_, "left"); hi = np.searchsorted(bw, w_, "right")
            if hi <= lo:
                continue
            k = int(np.searchsorted(bts[lo:hi], T, "right")) - 1
            if k < 0:
                continue
            j = lo + k
            if side == "up":
                touch_usd = asz[j] * ask0[j]
                walk_px = bwalk[j]; walk_sh = bwsh[j]
                touch_px = ask0[j]
            else:  # buying the down token = up-sell side
                touch_usd = bsz[j] * (1 - bid0[j])
                walk_px = 1 - swalk[j]; walk_sh = swsh[j]
                touch_px = 1 - bid0[j]
            out.append({"touch_usd": touch_usd, "touch_px": touch_px,
                        "walk50_px": walk_px, "walk50_sh": walk_sh,
                        "slip_bp": (walk_px - touch_px) * 1e4 if np.isfinite(walk_px) else None})
    d = pl.DataFrame(out)
    tu = d["touch_usd"].to_numpy()
    print(f"\nToB $ depth at the signal-side touch (n={len(d)}):")
    for q in (10, 25, 50, 75, 90):
        print(f"  p{q}: ${np.percentile(tu, q):,.0f}")
    for thr in (5, 10, 25, 50):
        print(f"  windows with >= ${thr} at touch: {100*np.mean(tu>=thr):.0f}%")
    slip = d["slip_px" if "slip_px" in d.columns else "slip_bp"].drop_nulls().to_numpy()
    print(f"\n$50 book-walk slippage vs touch: median {np.median(slip):.0f}bp, "
          f"p90 {np.percentile(slip,90):.0f}bp")
    print(f"$50 order fully fills (>= ~100 sh near touch): "
          f"{100*np.mean(d['walk50_sh'].to_numpy()>=95):.0f}% of windows")
    print("\nNIX_CAPACITY DONE")


if __name__ == "__main__":
    main()
