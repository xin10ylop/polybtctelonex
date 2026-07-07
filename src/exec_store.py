"""Phase 3 execution store — for every (window, t_offset) decision point,
the realized taker fill prices from the REAL book as-of T+latency, for
latencies 250ms / 1s / 3s and notionals $50/$200/$1000/$5000, both sides.

Output: results/exec/{family}/{date}.parquet keyed (wts, t_offset).
Resumable per date. Columns: {lat}_{side}_avgpx_{N} (+ exhaust flags at l250).
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

LATENCIES = {"l250": 250_000, "l1s": 1_000_000, "l3s": 3_000_000}
NOTIONALS = (50, 200, 1000, 5000)


def build_day(family: str, date: str) -> int:
    out = f"results/exec/{family}/{date}.parquet"
    if os.path.exists(out):
        return 0
    try:
        b = (loader.load_daily(family, "bookcurves", [date]).collect()
             .sort("wts", "local_timestamp_us"))
    except FileNotFoundError:
        return 0
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(family, d0, d0 + 86400).sort("wts")
    if meta.is_empty() or b.is_empty():
        return 0
    wts_arr = meta["wts"].to_numpy()
    b_wts = b["wts"].to_numpy()
    b_ts = b["local_timestamp_us"].to_numpy()
    cols_needed = {}
    for side in ("buy", "sell"):
        for N in NOTIONALS:
            cols_needed[f"{side}_avgpx_{N}"] = b[f"{side}_avgpx_{N}"].to_numpy()
            cols_needed[f"{side}_exhaust_{N}"] = b[f"{side}_exhaust_{N}"].to_numpy()
    frames = []
    for off in OFFSETS[family]:
        T = (wts_arr + off) * 1_000_000
        row: dict = {"wts": wts_arr, "t_offset": np.full(len(wts_arr), off, dtype=np.int64)}
        for lname, lus in LATENCIES.items():
            fill_t = T + lus
            # as-of per window slice
            idx = np.full(len(wts_arr), -1)
            for i, w_ in enumerate(wts_arr):
                lo = np.searchsorted(b_wts, w_, side="left")
                hi = np.searchsorted(b_wts, w_, side="right")
                if hi > lo:
                    k = np.searchsorted(b_ts[lo:hi], fill_t[i], side="right") - 1
                    if k >= 0:
                        idx[i] = lo + k
            ok = idx >= 0
            safe = np.clip(idx, 0, None)
            for side in ("buy", "sell"):
                for N in NOTIONALS:
                    v = cols_needed[f"{side}_avgpx_{N}"][safe]
                    row[f"{lname}_{side}_avgpx_{N}"] = np.where(ok, v, np.nan).astype(np.float32)
                    if lname == "l250":
                        ex = cols_needed[f"{side}_exhaust_{N}"][safe]
                        row[f"{side}_exhaust_{N}"] = np.where(ok, ex, True)
        frames.append(pl.DataFrame(row))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    pl.concat(frames).sort("wts", "t_offset").write_parquet(out, compression="zstd")
    return 1


def main() -> None:
    n = 0
    for family in ("5m", "15m"):
        for date in loader.available_dates(family, "bookcurves"):
            n += build_day(family, date)
            if n and n % 20 == 0:
                print(f"checkpoint {family} {date}", flush=True)
    print("EXEC STORE DONE")


if __name__ == "__main__":
    main()
