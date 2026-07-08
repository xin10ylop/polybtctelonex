"""NIXULTIMATE pass 1 — crowd-flow and book-pressure columns.

The hypothesis space: Polymarket odds are driven by human taker flow reacting
to BTC. These columns measure the crowd directly, per (wts, t_offset) at
decision time T (availability = local_timestamp_us, current market only):

  flow_imb_{10,30,60}s  signed taker flow imbalance (buyUp - sellUp)/gross
  flow_net_30s          raw net shares, last 30s
  flow_open_imb         imbalance since window open (pre-open offs: pre-market flow)
  nprints_30s           print count, last 30s (activity)
  big_imb_30s           imbalance of prints >= 100 shares only (whales)
  q_imb                 top-of-book size imbalance (bid-ask)/(bid+ask)
  depth_imb             5c-depth imbalance (bid_depth-ask_depth)/sum

Output: results/nixflow/5m/{date}.parquet. Mining dates <= 2026-05-12 ONLY —
2026-07-06/07 stay virgin for the fresh-OOS check.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader
from features import OFFSETS

MINE_END = "2026-05-12"
BIG = 100.0


def build_day(date: str) -> int:
    out = f"results/nixflow/5m/{date}.parquet"
    if os.path.exists(out):
        return 0
    try:
        tr = (loader.load_daily("5m", "trades", [date]).collect()
              .sort("wts", "local_timestamp_us"))
        q = (loader.load_daily("5m", "quotes", [date]).collect()
             .sort("wts", "local_timestamp_us"))
        b = (loader.load_daily("5m", "bookcurves", [date]).collect()
             .sort("wts", "local_timestamp_us"))
    except FileNotFoundError:
        return 0
    if tr.is_empty():
        return 0
    tw = tr["wts"].to_numpy()
    tts = tr["local_timestamp_us"].to_numpy()
    sgn = np.where(tr["side"].to_numpy() == "buy", 1.0, -1.0)
    sz = tr["size"].to_numpy().astype(np.float64)
    net_c = np.concatenate([[0.0], np.cumsum(sgn * sz)])
    grs_c = np.concatenate([[0.0], np.cumsum(sz)])
    big = sz >= BIG
    bnet_c = np.concatenate([[0.0], np.cumsum(np.where(big, sgn * sz, 0.0))])
    bgrs_c = np.concatenate([[0.0], np.cumsum(np.where(big, sz, 0.0))])

    qw = q["wts"].to_numpy()
    qts = q["local_timestamp_us"].to_numpy()
    qi = ((q["bid_size"] - q["ask_size"]) / (q["bid_size"] + q["ask_size"])) \
        .to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy()
    bts = b["local_timestamp_us"].to_numpy()
    di = ((b["bid_depth_5c"] - b["ask_depth_5c"]) /
          (b["bid_depth_5c"] + b["ask_depth_5c"])).to_numpy().astype(np.float64)

    uw = np.unique(tw)
    offs = OFFSETS["5m"]
    n, no = len(uw), len(offs)

    def seg(arr_w, w):
        return np.searchsorted(arr_w, w, "left"), np.searchsorted(arr_w, w, "right")

    cols = {c: np.full((n, no), np.nan) for c in
            ("flow_imb_10s", "flow_imb_30s", "flow_imb_60s", "flow_net_30s",
             "flow_open_imb", "nprints_30s", "big_imb_30s", "q_imb", "depth_imb")}
    for i, w_ in enumerate(uw):
        tlo, thi = seg(tw, w_)
        qlo, qhi = seg(qw, w_)
        blo, bhi = seg(bw, w_)
        for j, off in enumerate(offs):
            T = (w_ + off) * 1_000_000
            k = tlo + np.searchsorted(tts[tlo:thi], T, "right")
            for name, lb in (("flow_imb_10s", 10), ("flow_imb_30s", 30),
                             ("flow_imb_60s", 60)):
                a = tlo + np.searchsorted(tts[tlo:thi], T - lb * 1_000_000, "right")
                g = grs_c[k] - grs_c[a]
                if g > 0:
                    cols[name][i, j] = (net_c[k] - net_c[a]) / g
            a30 = tlo + np.searchsorted(tts[tlo:thi], T - 30_000_000, "right")
            cols["flow_net_30s"][i, j] = net_c[k] - net_c[a30]
            cols["nprints_30s"][i, j] = k - a30
            bg = bgrs_c[k] - bgrs_c[a30]
            if bg > 0:
                cols["big_imb_30s"][i, j] = (bnet_c[k] - bnet_c[a30]) / bg
            g_open = grs_c[k] - grs_c[tlo]
            if g_open > 0:
                cols["flow_open_imb"][i, j] = (net_c[k] - net_c[tlo]) / g_open
            kq = np.searchsorted(qts[qlo:qhi], T, "right") - 1
            if kq >= 0:
                cols["q_imb"][i, j] = qi[qlo + kq]
            kb = np.searchsorted(bts[blo:bhi], T, "right") - 1
            if kb >= 0:
                cols["depth_imb"][i, j] = di[blo + kb]

    df = pl.DataFrame({"wts": np.repeat(uw, no),
                       "t_offset": np.tile(np.array(offs, dtype=np.int64), n),
                       **{c: v.ravel() for c, v in cols.items()}})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.write_parquet(out, compression="zstd")
    return 1


if __name__ == "__main__":
    n = 0
    for date in loader.available_dates("5m", "trades"):
        if date > MINE_END:
            continue
        n += build_day(date)
        print(date, flush=True)
    print(f"NIXFLOW DONE ({n} new)")
