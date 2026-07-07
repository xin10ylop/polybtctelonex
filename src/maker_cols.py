"""Phase 3 — maker-fill support columns. For every (window, t_offset): the max
and min Up-token trade price printed AFTER decision time T+250ms until window
end. A resting sell limit at L is (conservatively) considered filled iff
max_tpx_after > L strictly; a buy limit iff min_tpx_after < L strictly —
the trade-through rule from src/execution.py, vectorized over all windows.

Output: results/maker/{family}/{date}.parquet
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

LAT_US = 250_000


def build_day(family: str, date: str) -> int:
    out = f"results/maker/{family}/{date}.parquet"
    if os.path.exists(out):
        return 0
    try:
        t = (loader.load_daily(family, "trades", [date]).collect()
             .sort("wts", "local_timestamp_us"))
    except FileNotFoundError:
        return 0
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(family, d0, d0 + 86400).sort("wts")
    if meta.is_empty():
        return 0
    wts_arr = meta["wts"].to_numpy()
    t_wts = t["wts"].to_numpy()
    t_ts = t["local_timestamp_us"].to_numpy()
    t_px = t["price"].to_numpy().astype(np.float64)
    frames = []
    dur = W.FAMILY_DUR[family]
    for off in OFFSETS[family]:
        T = (wts_arr + off) * 1_000_000 + LAT_US
        mx = np.full(len(wts_arr), np.nan)
        mn = np.full(len(wts_arr), np.nan)
        for i, w_ in enumerate(wts_arr):
            lo = np.searchsorted(t_wts, w_, side="left")
            hi = np.searchsorted(t_wts, w_, side="right")
            if hi <= lo:
                continue
            seg_ts = t_ts[lo:hi]
            k = np.searchsorted(seg_ts, T[i], side="right")
            end = np.searchsorted(seg_ts, (w_ + dur) * 1_000_000, side="right")
            if end > k:
                px = t_px[lo + k:lo + end]
                mx[i], mn[i] = px.max(), px.min()
        frames.append(pl.DataFrame({
            "wts": wts_arr, "t_offset": np.full(len(wts_arr), off, dtype=np.int64),
            "max_tpx_after": mx.astype(np.float32), "min_tpx_after": mn.astype(np.float32)}))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pl.concat(frames).sort("wts", "t_offset").write_parquet(out, compression="zstd")
    return 1


def main() -> None:
    n = 0
    for family in ("5m", "15m"):
        for date in loader.available_dates(family, "trades"):
            n += build_day(family, date)
    print("MAKER COLS DONE")


if __name__ == "__main__":
    main()
