"""NIXULTIMATE N6 — cross-timeframe laggard maker (5m catches up to 15m).

Both markets price the same BTC path. When the 15m market repriced sharply in
the last D seconds but the concurrent 5m market has not moved commensurately,
the 5m is the laggard: rest a maker bid on the side the 15m move implies,
capture the catch-up with a maker +5c exit (both legs fee-free), else hold.

Signal at T = w5 + toff:  gap = (mid15(T) - mid15(T-D)) - (mid5(T) - mid5(T-D))
  gap >= +g  ->  bid 5m Up   (15m repriced up, 5m lagging)
  gap <= -g  ->  bid 5m Down
Entry level: join (token best bid as-of T) or 1c behind. Live [T+250ms, T+H].
Exit: maker sell at entry+5c (strict trade-through after the fill), else hold
to resolution. Fills strict trade-through on the 5m tape. $5 stakes.
Train/val discipline, mining dates <= 2026-05-12.
Output: results/nix_xtf_maker.parquet + leaderboard.
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader
import windows as W

TRAIN_END = "2026-03-19"
MINE_END = "2026-05-12"
TOFFS = [30, 60, 150, 240]
DELTAS = [10, 30]
GAPS = [0.03, 0.05, 0.08]
LEVELS = ["join", "behind1"]
HOLDS = [30, 60]          # seconds the entry order stays live
EXIT_D = 0.05
STAKE = 5.0


def run() -> None:
    recs = []
    dates = [d for d in loader.available_dates("5m", "trades") if d <= MINE_END]
    for date in dates:
        try:
            tr = (loader.load_daily("5m", "trades", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
            q5 = (loader.load_daily("5m", "quotes", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
            q15 = (loader.load_daily("15m", "quotes", [date]).collect()
                   .sort("wts", "local_timestamp_us"))
        except FileNotFoundError:
            continue
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta("5m", d0, d0 + 86400)
        res = {int(w): r for w, r in zip(meta["wts"], meta["result_id"])}
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
        q5w = q5["wts"].to_numpy()
        q5t = q5["local_timestamp_us"].to_numpy()
        q5b = q5["bid_price"].to_numpy().astype(np.float64)
        q5a = q5["ask_price"].to_numpy().astype(np.float64)
        q5m = (q5b + q5a) / 2
        q15w = q15["wts"].to_numpy()
        q15t = q15["local_timestamp_us"].to_numpy()
        q15m = ((q15["bid_price"] + q15["ask_price"]) / 2).to_numpy().astype(np.float64)
        is_train = date <= TRAIN_END

        def asof15(w15, T):
            lo = np.searchsorted(q15w, w15, "left")
            hi = np.searchsorted(q15w, w15, "right")
            k = np.searchsorted(q15t[lo:hi], T, "right") - 1
            return q15m[lo + k] if k >= 0 else np.nan

        for w_ in np.unique(tw):
            rid = res.get(int(w_))
            if rid not in ("0", "1"):
                continue
            up_won = rid == "0"
            tlo = np.searchsorted(tw, w_, "left")
            thi = np.searchsorted(tw, w_, "right")
            seg_t = tts[tlo:thi]
            seg_p = tpx[tlo:thi]
            qlo = np.searchsorted(q5w, w_, "left")
            qhi = np.searchsorted(q5w, w_, "right")
            if qhi <= qlo:
                continue
            for toff in TOFFS:
                T = (w_ + toff) * 1_000_000
                w15 = ((w_ + toff) // 900) * 900
                k5 = np.searchsorted(q5t[qlo:qhi], T, "right") - 1
                if k5 < 0:
                    continue
                bid5, ask5, mid5 = q5b[qlo + k5], q5a[qlo + k5], q5m[qlo + k5]
                m15 = asof15(w15, T)
                if not (np.isfinite(m15) and 0.03 < mid5 < 0.97):
                    continue
                for D in DELTAS:
                    Tp = T - D * 1_000_000
                    k5p = np.searchsorted(q5t[qlo:qhi], Tp, "right") - 1
                    m15p = asof15(w15, Tp)
                    if k5p < 0 or not np.isfinite(m15p):
                        continue
                    gap = (m15 - m15p) - (mid5 - q5m[qlo + k5p])
                    for g in GAPS:
                        if abs(gap) < g:
                            continue
                        dir_up = gap > 0
                        tok_bid = bid5 if dir_up else 1.0 - ask5
                        for lvl_name in LEVELS:
                            L = tok_bid if lvl_name == "join" else tok_bid - 0.01
                            if not (0.02 < L < 0.97):
                                continue
                            a = np.searchsorted(seg_t, T + 250_000, "right")
                            for H in HOLDS:
                                b = np.searchsorted(seg_t, T + H * 1_000_000, "right")
                                if b <= a:
                                    continue
                                sl = seg_p[a:b]
                                tok = sl if dir_up else 1.0 - sl
                                through = tok < L
                                if not through.any():
                                    continue
                                fi = a + int(np.argmax(through))
                                S = STAKE / L
                                # maker +5c exit after the fill, before expiry
                                tok_after = (seg_p[fi + 1:] if dir_up
                                             else 1.0 - seg_p[fi + 1:])
                                exited = (tok_after > L + EXIT_D).any() \
                                    if len(tok_after) else False
                                if exited:
                                    pnl = S * EXIT_D
                                else:
                                    win = up_won if dir_up else not up_won
                                    pnl = S * (1.0 - L) if win else -S * L
                                recs.append((toff, D, g, lvl_name, H, is_train,
                                             bool(exited), round(pnl, 4)))
    df = pl.DataFrame(recs, schema=["toff", "D", "g", "lvl", "H", "is_train",
                                    "exited", "pnl"], orient="row")
    df.write_parquet("results/nix_xtf_maker.parquet")
    rows = []
    for key, g_ in df.group_by(["toff", "D", "g", "lvl", "H"]):
        r = dict(zip(["toff", "D", "g", "lvl", "H"], key))
        for split, gg in (("train", g_.filter(pl.col("is_train"))),
                          ("val", g_.filter(~pl.col("is_train")))):
            p = gg["pnl"].to_numpy()
            n = len(p)
            r[f"{split}_n"] = n
            if n < 2:
                continue
            mu, sd_ = p.mean(), p.std(ddof=1)
            r[f"{split}_pnl"] = round(float(p.sum()), 2)
            r[f"{split}_t"] = round(float(mu / (sd_ / np.sqrt(n))), 2) if sd_ > 0 else 0.0
            r[f"{split}_wr"] = round(float((p > 0).mean()), 3)
            r[f"{split}_exit%"] = round(float(gg["exited"].mean()), 3)
        rows.append(r)
    lb = pl.DataFrame(rows, infer_schema_length=None).sort("val_t", descending=True,
                                                           nulls_last=True)
    pl.Config.set_tbl_cols(16)
    pl.Config.set_tbl_rows(40)
    print(lb)


if __name__ == "__main__":
    run()
