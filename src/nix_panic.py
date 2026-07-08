"""NIXULTIMATE N4 — panic-harvest deep maker bids (mid-relative).

Game theory: crowd overreaction to BTC wiggles market-dumps one token into a
thin book. Be the resting counterparty. At T = w + toff, read the Up mid from
the BBO as-of T, then rest:

  side=up    bid Up at mid-k          (fills only if crowd dumps Up k+ cents)
  side=down  bid Down at (1-mid)-k    (= crowd pumps Up through mid+k)
  side=both  BOTH of the above — a bracket: whipsaw through +-k locks
             S*2k fee-free; one fill = discounted hold to resolution

Fills strict trade-through on the tape while live [T+250ms, w+tc]; unfilled
legs cancelled at tc (before the resolution regime). Maker = zero fee.
$5 per leg. Train/val discipline, mining dates <= 2026-05-12.
Output: results/nix_panic.parquet + leaderboard.
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
TOFFS = [30, 60, 150]
KS = [0.05, 0.08, 0.12]
TC = 297
SIDES = ["up", "down", "both"]
STAKE = 5.0


def run() -> None:
    recs = []
    dates = [d for d in loader.available_dates("5m", "trades") if d <= MINE_END]
    for date in dates:
        try:
            tr = (loader.load_daily("5m", "trades", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
            q = (loader.load_daily("5m", "quotes", [date]).collect()
                 .sort("wts", "local_timestamp_us"))
        except FileNotFoundError:
            continue
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta("5m", d0, d0 + 86400)
        res = {int(w): r for w, r in zip(meta["wts"], meta["result_id"])}
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
        qw = q["wts"].to_numpy()
        qts = q["local_timestamp_us"].to_numpy()
        qmid = ((q["bid_price"] + q["ask_price"]) / 2).to_numpy().astype(np.float64)
        is_train = date <= TRAIN_END
        for w_ in np.unique(tw):
            rid = res.get(int(w_))
            if rid not in ("0", "1"):
                continue
            up_won = rid == "0"
            tlo = np.searchsorted(tw, w_, "left")
            thi = np.searchsorted(tw, w_, "right")
            seg_t = tts[tlo:thi]
            seg_p = tpx[tlo:thi]
            qlo = np.searchsorted(qw, w_, "left")
            qhi = np.searchsorted(qw, w_, "right")
            b_end = np.searchsorted(seg_t, (w_ + TC) * 1_000_000, "right")
            for toff in TOFFS:
                T = (w_ + toff) * 1_000_000
                kq = np.searchsorted(qts[qlo:qhi], T, "right") - 1
                if kq < 0:
                    continue
                mid = qmid[qlo + kq]
                if not (0.05 < mid < 0.95):
                    continue
                a = np.searchsorted(seg_t, T + 250_000, "right")
                if b_end <= a:
                    continue
                mn = seg_p[a:b_end].min()
                mx = seg_p[a:b_end].max()
                for k in KS:
                    bu = mid - k            # Up bid
                    bd = (1.0 - mid) - k    # Down bid (Up-space ask at mid+k)
                    fu = (bu > 0.01) and (mn < bu)
                    fd = (bd > 0.01) and (mx > mid + k)
                    su = STAKE / max(bu, 1e-9)
                    sd = STAKE / max(bd, 1e-9)
                    for side in SIDES:
                        if side == "up":
                            if not fu:
                                continue
                            pnl = su * (1.0 - bu) if up_won else -su * bu
                            kind = "up_only"
                        elif side == "down":
                            if not fd:
                                continue
                            pnl = sd * (1.0 - bd) if not up_won else -sd * bd
                            kind = "down_only"
                        else:
                            # bracket: equal shares S both legs; both-fill pays
                            # S regardless of outcome -> locked S*2k profit
                            if not (fu or fd):
                                continue
                            S = 2 * STAKE / max(bu + bd, 1e-9)
                            if fu and fd:
                                pnl = S - S * (bu + bd)
                                kind = "both"
                            elif fu:
                                pnl = S * (1.0 - bu) if up_won else -S * bu
                                kind = "up_only"
                            else:
                                pnl = S * (1.0 - bd) if not up_won else -S * bd
                                kind = "down_only"
                        recs.append((toff, k, side, is_train, kind, round(pnl, 4)))
    df = pl.DataFrame(recs, schema=["toff", "k", "side", "is_train", "kind", "pnl"],
                      orient="row")
    df.write_parquet("results/nix_panic.parquet")
    rows = []
    for (toff, k, side), g in df.group_by(["toff", "k", "side"]):
        r = {"toff": toff, "k": k, "side": side}
        for split, gg in (("train", g.filter(pl.col("is_train"))),
                          ("val", g.filter(~pl.col("is_train")))):
            p = gg["pnl"].to_numpy()
            n = len(p)
            r[f"{split}_n"] = n
            if n < 2:
                continue
            mu, sd_ = p.mean(), p.std(ddof=1)
            r[f"{split}_pnl"] = round(float(p.sum()), 2)
            r[f"{split}_mean"] = round(float(mu), 4)
            r[f"{split}_t"] = round(float(mu / (sd_ / np.sqrt(n))), 2) if sd_ > 0 else 0.0
            r[f"{split}_wr"] = round(float((p > 0).mean()), 3)
            r[f"{split}_both%"] = round(float((gg["kind"] == "both").mean()), 3)
        rows.append(r)
    lb = pl.DataFrame(rows, infer_schema_length=None).sort("val_t", descending=True,
                                                           nulls_last=True)
    pl.Config.set_tbl_cols(14)
    pl.Config.set_tbl_rows(30)
    print(lb)


if __name__ == "__main__":
    run()
