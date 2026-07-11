"""The user's manual scalp, simulated EXACTLY as described (2026-07-10).

Shape: buy one side at <=51c, 5-10s BEFORE the window opens; immediately rest
a sell limit at entry+4c (~55c); if the limit hasn't filled by open+10s (or
+30s), market-sell everything. Direction chosen by: blind up / blind down /
Binance momentum (60s, 300s) / fade of each.

Execution fidelity:
  - taker entry: top-of-book ask as-of t0+250ms, must be <=0.51 with >=$10
    resting; taker fee (date-correct). This matches "my $10 bets always fill".
  - maker entry variant: resting bid at 0.50/0.51 from t0, strict
    trade-through fill (a real print strictly below the bid), fee-free.
  - TP sell at entry+0.04: resting maker order, strict trade-through
    (a real print strictly ABOVE it), fee-free.
  - stop: top-of-book bid as-of (open+stop+250ms), taker fee.
  - Down side = exact mirror of the Up book/tape (verified project-wide).

Diagnostics per config: entry fill rate, TP hit rate given fill (this is the
"wins 7 out of 10" number), stop-loss size distribution, and worst trades —
so the manual experience can be reconciled with the full-sample expectancy.
Sample: all 90 mining days (Feb 12 - May 12) + Jul 6-7 fresh, BTC 5m.
Output: results/nix_scalp.parquet + leaderboard.
"""
from __future__ import annotations

import datetime as dt
import math
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import os

import fees
import loader
import windows as W

FAM = os.environ.get("SCALP_FAM", "5m")
ZEROFEE = bool(os.environ.get("SCALP_ZEROFEE"))

STAKE = 10.0
T0S = [-10, -5]
ENTRIES = [("taker", 0.51), ("maker", 0.50), ("maker", 0.51)]
STOPS = [10, 30, None]          # None = hold to resolution
TP_DELTA = 0.04
LAT = 250_000
TRAIN_END = "2026-03-19"


def day_rows(date: str) -> list[dict]:
    try:
        tr = (loader.load_daily(FAM, "trades", [date]).collect()
              .sort("wts", "local_timestamp_us"))
        b = (loader.load_daily(FAM, "bookcurves", [date]).collect()
             .sort("wts", "local_timestamp_us"))
        bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(FAM, d0, d0 + 86400)
    tw = tr["wts"].to_numpy()
    tts = tr["local_timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy()
    bts = b["local_timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    bsz = b["bid_s0"].to_numpy().astype(np.float64)
    asz = b["ask_s0"].to_numpy().astype(np.float64)
    bt = bn["ts_us"].to_numpy()
    blog = np.log(bn["price"].to_numpy().astype(np.float64))
    rate = 0.0 if ZEROFEE else fees.params(date, FAM)[0]
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        tlo = np.searchsorted(tw, w_, "left")
        thi = np.searchsorted(tw, w_, "right")
        blo = np.searchsorted(bw, w_, "left")
        bhi = np.searchsorted(bw, w_, "right")
        if bhi <= blo:
            continue
        seg_t = tts[tlo:thi]
        seg_p = tpx[tlo:thi]
        sb_t = bts[blo:bhi]

        def tob(T):
            k = np.searchsorted(sb_t, T, "right") - 1
            if k < 0:
                return None
            j = blo + k
            return bid0[j], ask0[j], bsz[j], asz[j]

        for t0s in T0S:
            T0 = (w_ + t0s) * 1_000_000
            # Binance momentum signs at decision time (150ms latency margin)
            b2 = np.searchsorted(bt, T0 - 150_000, "right") - 1
            moms = {}
            for lb, nm in ((60, "m60"), (300, "m300")):
                b1 = np.searchsorted(bt, T0 - 150_000 - lb * 1_000_000, "right") - 1
                moms[nm] = (0.0 if (b1 < 0 or b2 <= b1)
                            else math.copysign(1.0, blog[b2] - blog[b1])
                            if blog[b2] != blog[b1] else 0.0)
            for ent_style, ent_px in ENTRIES:
                for side in ("up", "down"):
                    # token-space tape for this side
                    tok = seg_p if side == "up" else 1.0 - seg_p
                    # ---- entry ----
                    if ent_style == "taker":
                        q = tob(T0 + LAT)
                        if q is None:
                            continue
                        bq, aq, bs_, as_ = q
                        a = aq if side == "up" else (1 - bq if np.isfinite(bq) else np.nan)
                        adep = (as_ * aq if side == "up" else bs_ * (1 - bq))
                        if not (np.isfinite(a) and a <= ent_px and adep >= STAKE):
                            continue
                        fill_px, fill_t = float(a), T0 + LAT
                        fee_in = rate * fill_px * (1 - fill_px) * (STAKE / fill_px)
                    else:
                        i0 = np.searchsorted(seg_t, T0, "left")
                        iw = np.searchsorted(seg_t, w_ * 1_000_000, "left")
                        hit = np.nonzero(tok[i0:iw] < ent_px)[0]
                        if len(hit) == 0:
                            continue
                        fill_px = ent_px
                        fill_t = int(seg_t[i0 + hit[0]])
                        fee_in = 0.0
                    sh = STAKE / fill_px
                    tp = fill_px + TP_DELTA
                    ifill = np.searchsorted(seg_t, fill_t, "right")
                    for stop in STOPS:
                        if stop is None:
                            iend = len(seg_t)
                        else:
                            iend = np.searchsorted(
                                seg_t, (w_ + stop) * 1_000_000, "right")
                        hit_tp = np.nonzero(tok[ifill:iend] > tp)[0]
                        if len(hit_tp):
                            pnl = sh * TP_DELTA - fee_in          # maker TP, no fee
                            outcome = "tp"
                        elif stop is None:
                            win = 1.0 if (side == "up") == up_won else 0.0
                            pnl = sh * win - STAKE - fee_in
                            outcome = "hold"
                        else:
                            q = tob((w_ + stop) * 1_000_000 + LAT)
                            if q is None:
                                continue
                            bq, aq, _, _ = q
                            xb = bq if side == "up" else (1 - aq if np.isfinite(aq) else np.nan)
                            if not np.isfinite(xb):
                                continue
                            pnl = (sh * (xb - fill_px) - fee_in
                                   - rate * xb * (1 - xb) * sh)
                            outcome = "stop"
                        rows.append({
                            "date": date, "wts": int(w_), "t0": t0s,
                            "entry": f"{ent_style}{int(ent_px*100)}",
                            "side": side, "stop": -1 if stop is None else stop,
                            "m60": moms["m60"], "m300": moms["m300"],
                            "pnl": round(float(pnl), 4), "outcome": outcome,
                            "fill_px": round(fill_px, 4)})
    return rows


def main() -> None:
    dates = ([d for d in loader.available_dates(FAM, "trades") if d <= "2026-05-12"]
             + ["2026-07-06", "2026-07-07"])
    all_rows = []
    for date in dates:
        all_rows += day_rows(date)
        print(date, flush=True)
    df = pl.DataFrame(all_rows)
    tag = FAM + ("_zerofee" if ZEROFEE else "")
    df.write_parquet(f"results/nix_scalp_{tag}.parquet")
    print(f"NIX_SCALP DONE: {len(df)} trade-rows")


if __name__ == "__main__":
    main()
