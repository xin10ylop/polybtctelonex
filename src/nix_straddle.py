"""NIXULTIMATE N1 — two-sided whipsaw straddle (pure maker, game-theoretic).

Books are exact mirrors (verified), so Up_ask + Down_ask >= 1 always: the
"Up+Down < $1" arbitrage exists ONLY via resting limit orders. Structure:
at t0, rest a bid on BOTH tokens at level L (Up bid at L; Down bid at L,
which sits in the Up book as an ask at 1-L). Cancel unfilled legs at tc.

  both fill   -> locked, fee-free profit S*(1-2L)  (crowd whipsawed through
                 both levels — pure harvest of human overreaction)
  one fills   -> discounted lottery held to resolution (adverse selection:
                 the side that fills is the side the crowd is dumping)

Fills are strict trade-through on the real tape: Up bid fills only if a print
goes STRICTLY below L while live; Down bid only if a print goes strictly
above 1-L. Maker legs pay zero fee. $5 per side, S = 5/L shares each.

Grid: L x t0 x tc. Train (<= Mar 19) / val (Mar 20 - May 12) discipline.
Output: results/nix_straddle.parquet + stdout leaderboard.
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
LEVELS = [0.40, 0.42, 0.44, 0.45, 0.46, 0.47, 0.48]
T0S = [0, 30]
TCS = [150, 240, 297]
STAKE = 5.0


def run() -> None:
    recs = []  # one row per (config, window with >=1 fill)
    dates = [d for d in loader.available_dates("5m", "trades") if d <= MINE_END]
    for date in dates:
        try:
            tr = (loader.load_daily("5m", "trades", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
        except FileNotFoundError:
            continue
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta("5m", d0, d0 + 86400)
        res = {int(w): r for w, r in zip(meta["wts"], meta["result_id"])}
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
        is_train = date <= TRAIN_END
        for w_ in np.unique(tw):
            rid = res.get(int(w_))
            if rid not in ("0", "1"):
                continue
            up_won = rid == "0"
            lo = np.searchsorted(tw, w_, "left")
            hi = np.searchsorted(tw, w_, "right")
            seg_t = tts[lo:hi]
            seg_p = tpx[lo:hi]
            for t0 in T0S:
                a = np.searchsorted(seg_t, (w_ + t0) * 1_000_000, "right")
                for tc in TCS:
                    b = np.searchsorted(seg_t, (w_ + tc) * 1_000_000, "right")
                    if b <= a:
                        continue
                    mn = seg_p[a:b].min()
                    mx = seg_p[a:b].max()
                    for L in LEVELS:
                        s = STAKE / L
                        fu = mn < L          # Up bid trade-through
                        fd = mx > 1.0 - L    # Down bid trade-through
                        if not (fu or fd):
                            continue
                        if fu and fd:
                            pnl = s * (1.0 - 2 * L)
                            kind = "both"
                        elif fu:
                            pnl = s * (1.0 - L) if up_won else -s * L
                            kind = "up_only"
                        else:
                            pnl = s * (1.0 - L) if not up_won else -s * L
                            kind = "down_only"
                        recs.append((L, t0, tc, is_train, kind, round(pnl, 4)))
    df = pl.DataFrame(recs, schema=["L", "t0", "tc", "is_train", "kind", "pnl"],
                      orient="row")
    df.write_parquet("results/nix_straddle.parquet")
    # leaderboard
    rows = []
    for (L, t0, tc), g in df.group_by(["L", "t0", "tc"]):
        r = {"L": L, "t0": t0, "tc": tc}
        for split, gg in (("train", g.filter(pl.col("is_train"))),
                          ("val", g.filter(~pl.col("is_train")))):
            p = gg["pnl"].to_numpy()
            n = len(p)
            r[f"{split}_n"] = n
            if n < 2:
                continue
            mu, sd = p.mean(), p.std(ddof=1)
            r[f"{split}_pnl"] = round(float(p.sum()), 2)
            r[f"{split}_mean"] = round(float(mu), 4)
            r[f"{split}_t"] = round(float(mu / (sd / np.sqrt(n))), 2) if sd > 0 else 0.0
            r[f"{split}_both%"] = round(float((gg["kind"] == "both").mean()), 3)
            single = gg.filter(pl.col("kind") != "both")
            r[f"{split}_single_wr"] = round(float((single["pnl"] > 0).mean()), 3) \
                if len(single) else None
        rows.append(r)
    lb = pl.DataFrame(rows, infer_schema_length=None).sort("val_t", descending=True,
                                                           nulls_last=True)
    pl.Config.set_tbl_cols(14)
    pl.Config.set_tbl_rows(45)
    print(lb)


if __name__ == "__main__":
    run()
