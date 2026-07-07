"""Extension pass 1 — cross-timeframe columns for 5m decisions.

For each 5m (wts, t_offset) decision point at time T: the CONCURRENT 15m
market's state as-of T (availability = local_timestamp_us):
  xtf15_mid      concurrent 15m Up mid
  xtf15_vel60    its 60s odds velocity
  xtf15_align    (15m_mid-0.5) with sign flipped onto the 5m question
  xtf15_t_rem    seconds remaining in the 15m window
Output: results/xtf/5m/{date}.parquet keyed (wts, t_offset).
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader
import windows as W
from features import OFFSETS


def build_day(date: str) -> int:
    out = f"results/xtf/5m/{date}.parquet"
    if os.path.exists(out):
        return 0
    try:
        q15 = (loader.load_daily("15m", "quotes", [date]).collect()
               .sort("wts", "local_timestamp_us"))
    except FileNotFoundError:
        return 0
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0, d0 + 86400).sort("wts")
    if meta.is_empty() or q15.is_empty():
        return 0
    wts5 = meta["wts"].to_numpy()
    q_wts = q15["wts"].to_numpy()
    q_ts = q15["local_timestamp_us"].to_numpy()
    q_mid = ((q15["bid_price"] + q15["ask_price"]) / 2).to_numpy().astype(np.float64)
    frames = []
    for off in OFFSETS["5m"]:
        T = (wts5 + off) * 1_000_000
        w15 = ((wts5 + off) // 900) * 900
        mid = np.full(len(wts5), np.nan)
        vel = np.full(len(wts5), np.nan)
        for i in range(len(wts5)):
            lo = np.searchsorted(q_wts, w15[i], side="left")
            hi = np.searchsorted(q_wts, w15[i], side="right")
            if hi <= lo:
                continue
            seg = q_ts[lo:hi]
            k = np.searchsorted(seg, T[i], side="right") - 1
            if k >= 0:
                mid[i] = q_mid[lo + k]
                k2 = np.searchsorted(seg, T[i] - 60_000_000, side="right") - 1
                if k2 >= 0:
                    vel[i] = q_mid[lo + k] - q_mid[lo + k2]
        frames.append(pl.DataFrame({
            "wts": wts5, "t_offset": np.full(len(wts5), off, dtype=np.int64),
            "xtf15_mid": mid, "xtf15_vel60": vel,
            "xtf15_align": mid - 0.5,
            "xtf15_t_rem": (w15 + 900 - (wts5 + off)).astype(np.float64)}))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pl.concat(frames).sort("wts", "t_offset").write_parquet(out, compression="zstd")
    return 1


if __name__ == "__main__":
    n = 0
    for date in loader.available_dates("5m", "quotes"):
        n += build_day(date)
    print(f"XTF DONE ({n} new)")
