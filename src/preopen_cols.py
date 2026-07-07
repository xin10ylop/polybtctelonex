"""Pre-open extension — signals available BEFORE a 5m window opens.

For each 5m window w and pre-open offset (t_offset < 0), at T = w + offset:
  prior_live_mid  the CURRENTLY-RESOLVING window's (w-300) mid as-of T —
                  a probabilistic read of the outcome about to print
  prior2_up       outcome of the last fully-resolved window (w-600), known at T
Output: results/preopen/5m/{date}.parquet keyed (wts, t_offset<0 only).
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

NEG_OFFS = [o for o in OFFSETS["5m"] if o < 0]


def build_day(date: str) -> int:
    out = f"results/preopen/5m/{date}.parquet"
    if os.path.exists(out):
        return 0
    try:
        q = (loader.load_daily("5m", "quotes", [date]).collect()
             .sort("wts", "local_timestamp_us"))
    except FileNotFoundError:
        return 0
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0 - 600, d0 + 86400).sort("wts")
    if meta.is_empty() or q.is_empty():
        return 0
    res_map = {int(w): (1.0 if r == "0" else 0.0 if r == "1" else np.nan)
               for w, r in zip(meta["wts"], meta["result_id"])}
    wts5 = meta.filter(pl.col("wts") >= d0)["wts"].to_numpy()
    q_wts = q["wts"].to_numpy()
    q_ts = q["local_timestamp_us"].to_numpy()
    q_mid = ((q["bid_price"] + q["ask_price"]) / 2).to_numpy().astype(np.float64)
    frames = []
    for off in NEG_OFFS:
        T = (wts5 + off) * 1_000_000
        plm = np.full(len(wts5), np.nan)
        p2 = np.array([res_map.get(int(w) - 600, np.nan) for w in wts5])
        for i, w_ in enumerate(wts5):
            pw = w_ - 300
            lo = np.searchsorted(q_wts, pw, side="left")
            hi = np.searchsorted(q_wts, pw, side="right")
            if hi <= lo:
                continue
            k = np.searchsorted(q_ts[lo:hi], T[i], side="right") - 1
            if k >= 0:
                plm[i] = q_mid[lo + k]
        frames.append(pl.DataFrame({
            "wts": wts5, "t_offset": np.full(len(wts5), off, dtype=np.int64),
            "prior_live_mid": plm, "prior2_up": p2}))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pl.concat(frames).sort("wts", "t_offset").write_parquet(out, compression="zstd")
    return 1


if __name__ == "__main__":
    n = 0
    for date in loader.available_dates("5m", "quotes"):
        n += build_day(date)
    print(f"PREOPEN COLS DONE ({n})")
