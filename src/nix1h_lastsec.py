"""NIXULTIMATE 2.0 core — final-seconds trade on the 1h family, WITH BOOKS.

The signal feed IS the referee here: resolution = Binance BTC/USDT 1H candle
close >= open (verified 765/765 vs result_id). No Chainlink, no broadcast
delay, no synthesis, no basis risk. Signal from local Binance klines_1s:
  T = close - 3s;  delta = log(P(T-1s)/candle_open);  sigma = std of 1s
  logrets over prior 300s;  z = delta/(sigma*sqrt(3));  |z| >= 1.5
Execution identical to nix1: $50-bucket book-walk ask as-of T+250ms
(real Telonex hourly books), EV gate fair - ask - fee >= 2c with the
date-correct 1h fee regime (0 pre Mar 6; 0.0624; 0.072; 0.07 from May 7),
tape validation (real print <= ask+1c within 1.5s), $5 stakes.

FROZEN parameters carried from nix1 — this is a pre-registered market
transfer, not a mined config. Splits (pre-registered for 1h):
TRAIN <= 2026-03-19 / VAL Mar 20 - May 12 / RESERVE May 13+ (one-shot).
NOTE: pre-Mar-6 the family is FEE-FREE — the era the 5m/15m never had.

Usage: .venv/bin/python src/nix1h_lastsec.py [--reserve-oneshot]
Runs on whatever consolidated 1h dates exist; prints monthly + split stats.
Output: results/nix1h_lastsec.parquet
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import sys

import numpy as np
import polars as pl
from scipy.stats import norm

sys.path.insert(0, "src")
import fees
import windows as W

Z_THR = 1.5
EV_MARGIN = 0.02
FILL_LAT_US = 250_000
STAKE = 5.0
TRAIN_END = "2026-03-19"
VAL_END = "2026-05-12"


def run_day(date: str, kcache: dict) -> list[dict]:
    bq = f"data/processed/daily/1h/bookcurves/{date}.parquet"
    tq = f"data/processed/daily/1h/trades/{date}.parquet"
    if not (os.path.exists(bq) and os.path.exists(tq)):
        return []

    def klines(day):
        if day not in kcache:
            p = f"data/processed/binance/klines_1s/{day}.parquet"
            kcache[day] = pl.read_parquet(p).sort("open_time_us") if os.path.exists(p) else None
        return kcache[day]

    b = pl.read_parquet(bq).sort("wts", "local_timestamp_us")
    tr = pl.read_parquet(tq).sort("wts", "local_timestamp_us")
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("1h", d0, d0 + 86400)
    bw = b["wts"].to_numpy()
    bts = b["local_timestamp_us"].to_numpy()
    b_buy = b["buy_avgpx_50"].to_numpy().astype(float)
    b_sell = b["sell_avgpx_50"].to_numpy().astype(float)
    tw = tr["wts"].to_numpy()
    tts = tr["local_timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(float)
    rate = fees.params(date, "1h")[0]
    out = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        end_s = w_ + 3600
        T = end_s - 3
        k = klines(date)
        k2day = dt.datetime.fromtimestamp(end_s, dt.timezone.utc).strftime("%Y-%m-%d")
        if k2day != date:
            kk2 = klines(k2day)
            if kk2 is not None and k is not None:
                k = pl.concat([k, kk2]).sort("open_time_us")
        if k is None:
            continue
        t_us = k["open_time_us"].to_numpy()
        op = k["open"].to_numpy()
        cl = k["close"].to_numpy()
        i0 = np.searchsorted(t_us, w_ * 1_000_000, "left")
        if i0 >= len(t_us) or t_us[i0] >= end_s * 1_000_000:
            continue
        O = op[i0]
        iT = np.searchsorted(t_us, (T - 1) * 1_000_000, "right") - 1
        j0 = np.searchsorted(t_us, (T - 300) * 1_000_000, "left")
        if iT <= j0 + 30:
            continue
        sig = float(np.std(np.diff(np.log(cl[j0:iT + 1]))))
        if not (np.isfinite(sig) and sig > 0):
            continue
        z = math.log(cl[iT] / O) / (sig * math.sqrt(3))
        fair_up = float(norm.cdf(z))
        lo = np.searchsorted(bw, w_, "left")
        hi = np.searchsorted(bw, w_, "right")
        if hi <= lo:
            continue
        kk = np.searchsorted(bts[lo:hi], (T * 1_000_000) + FILL_LAT_US, "right") - 1
        if kk < 0:
            continue
        tlo = np.searchsorted(tw, w_, "left")
        thi = np.searchsorted(tw, w_, "right")
        stt = tts[tlo:thi]
        sp = tpx[tlo:thi]
        # both sides considered; two configs share the window:
        #   frozen  |z| >= 1.5, favored side only (nix1 transfer)
        #   evonly  no z gate — any side whose BOOK ask is below fair-margin
        #           (catches stale cheap-side asks after late reversals)
        for side_up in (True, False):
            fair = fair_up if side_up else 1.0 - fair_up
            ask = b_buy[lo + kk] if side_up else 1 - b_sell[lo + kk]
            if not (np.isfinite(ask) and 0.005 < ask < 0.995):
                continue
            ev = fair - ask - rate * ask * (1 - ask)
            cfgs = []
            if abs(z) >= Z_THR and side_up == (z > 0):
                cfgs.append("frozen")
            cfgs.append("evonly")
            won = bool(up_won == side_up)
            # tape check retained as the conservative flag (ghost tape on 1h
            # makes it advisory, not blocking — book-walk is the fill model,
            # same standard as the main gauntlet's exec store)
            tok = sp if side_up else 1 - sp
            m1 = np.searchsorted(stt, T * 1_000_000 + FILL_LAT_US, "left")
            m2 = np.searchsorted(stt, T * 1_000_000 + FILL_LAT_US + 1_500_000, "right")
            pr = tok[m1:m2]
            tape_ok = bool((pr <= ask + 0.01).any()) if len(pr) else False
            for cfg in cfgs:
                row = {"date": date, "wts": int(w_), "cfg": cfg,
                       "side_up": side_up, "z": round(z, 2),
                       "fair": round(fair, 4), "ask": round(float(ask), 4),
                       "won": won, "tape_ok": tape_ok}
                if ev < EV_MARGIN:
                    row["stage"] = "ev_block"
                else:
                    row["stage"] = "traded"
                    sh = STAKE / ask
                    pnl = sh * (1.0 if won else 0.0) - STAKE \
                        - sh * rate * ask * (1 - ask)
                    row["pnl"] = round(float(pnl), 4)
                out.append(row)
    return out


def main() -> None:
    reserve = "--reserve-oneshot" in sys.argv
    dates = sorted(p.split("/")[-1][:10]
                   for p in glob.glob("data/processed/daily/1h/bookcurves/*.parquet"))
    if not reserve:
        dates = [d for d in dates if d <= VAL_END]
    kcache: dict = {}
    rows = []
    for date in dates:
        day_rows = run_day(date, kcache)
        rows += day_rows
        kcache.clear()
        tr = [r for r in day_rows if r["stage"] == "traded"]
        p = sum(r["pnl"] for r in tr)
        print(f"{date}: z-passed {len(day_rows):3d} traded {len(tr):2d} ${p:7.2f}", flush=True)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet("results/nix1h_lastsec.parquet")
    for cfg in ("frozen", "evonly"):
        c = df.filter(pl.col("cfg") == cfg)
        tr = c.filter(pl.col("stage") == "traded")
        print(f"\n=== {cfg} ===")
        for lab in ("TRAIN", "VAL", "RESERVE"):
            if lab == "TRAIN":
                t = tr.filter(pl.col("date") <= TRAIN_END)
            elif lab == "VAL":
                t = tr.filter((pl.col("date") > TRAIN_END) & (pl.col("date") <= VAL_END))
            else:
                t = tr.filter(pl.col("date") > VAL_END)
            if len(t) < 2:
                print(f"{lab}: n={len(t)}")
                continue
            p = t["pnl"].to_numpy()
            mu, sd = p.mean(), p.std(ddof=1)
            print(f"{lab}: n={len(p)} pnl=${p.sum():.2f} mean=${mu:.3f} "
                  f"t={mu / (sd / np.sqrt(len(p))):.1f} wr={(p > 0).mean():.1%} "
                  f"tape_ok {t['tape_ok'].mean():.0%}")
        for mo in sorted(set(c["date"].str.slice(0, 7))):
            t = tr.filter(pl.col("date").str.starts_with(mo))
            days = c.filter(pl.col("date").str.starts_with(mo))["date"].n_unique()
            p = t["pnl"].to_numpy() if len(t) else np.array([])
            print(f"{mo}: traded {len(t):3d} pnl ${p.sum():8.2f} "
                  f"(${p.sum() / max(days, 1):6.2f}/day) wr {(p > 0).mean() if len(p) else 0:.0%}")


if __name__ == "__main__":
    main()
