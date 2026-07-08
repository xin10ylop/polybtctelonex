"""NIXULTIMATE 2.0 — mid-hour stale-quote sniper on the 1h family.

Structure: hourly books are human-slow; when Binance moves, resting asks can
stay stale for minutes. Every minute of every hour-window, compare a
CALIBRATED win probability against the actual book ask; if p_hat - ask - fee
clears a margin, taker-buy at the book-walk price and hold to close.

Honesty: raw Phi(z) is miscalibrated at minute horizons (proven on tape).
So p_hat = isotonic regression of outcome on z, fit per time-remaining
bucket on TRAIN ONLY (<= 2026-03-19), applied unchanged to VAL. Margins
{0.05, 0.10} pre-registered. One trade per window (first trigger). Fees
date-correct. RESERVE (May 13+) untouched.

Usage: .venv/bin/python src/nix1h_sniper.py
Output: results/nix1h_sniper_points.parquet + results/nix1h_sniper.parquet
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
import windows as W

TRAIN_END = "2026-03-19"
VAL_END = "2026-05-12"
MARGINS = [0.05, 0.10]
MINUTES = list(range(2, 58))
TREM_BUCKETS = [(0, 300), (300, 600), (600, 1200), (1200, 1800), (1800, 2700), (2700, 3600)]


def build_points() -> pl.DataFrame:
    out = "results/nix1h_sniper_points.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    rows = []
    kcache: dict = {}

    def klines(day):
        if day not in kcache:
            p = f"data/processed/binance/klines_1s/{day}.parquet"
            kcache[day] = pl.read_parquet(p).sort("open_time_us") if os.path.exists(p) else None
        return kcache[day]

    dates = sorted(p.split("/")[-1][:10]
                   for p in glob.glob("data/processed/daily/1h/bookcurves/*.parquet"))
    dates = [d for d in dates if d <= VAL_END]
    for date in dates:
        b = pl.read_parquet(f"data/processed/daily/1h/bookcurves/{date}.parquet") \
            .sort("wts", "local_timestamp_us")
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta("1h", d0, d0 + 86400)
        bw = b["wts"].to_numpy()
        bts = b["local_timestamp_us"].to_numpy()
        b_buy = b["buy_avgpx_50"].to_numpy().astype(float)
        b_sell = b["sell_avgpx_50"].to_numpy().astype(float)
        rate = fees.params(date, "1h")[0]
        for r_ in meta.iter_rows(named=True):
            w_ = r_["wts"]
            rid = r_["result_id"]
            if rid not in ("0", "1"):
                continue
            k = klines(date)
            end_s = w_ + 3600
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
            lo = np.searchsorted(bw, w_, "left")
            hi = np.searchsorted(bw, w_, "right")
            if hi <= lo:
                continue
            for m in MINUTES:
                T = w_ + 60 * m
                iT = np.searchsorted(t_us, (T - 1) * 1_000_000, "right") - 1
                j0 = np.searchsorted(t_us, (T - 300) * 1_000_000, "left")
                if iT <= j0 + 30:
                    continue
                sig = float(np.std(np.diff(np.log(cl[j0:iT + 1]))))
                if not (np.isfinite(sig) and sig > 0):
                    continue
                t_rem = 3600 - 60 * m
                z = math.log(cl[iT] / O) / (sig * math.sqrt(t_rem))
                kk = np.searchsorted(bts[lo:hi], T * 1_000_000 + 250_000, "right") - 1
                if kk < 0:
                    continue
                au = b_buy[lo + kk]
                ad = 1 - b_sell[lo + kk]
                rows.append({"date": date, "wts": int(w_), "min": m,
                             "t_rem": t_rem, "z": round(z, 3),
                             "ask_up": round(float(au), 4) if np.isfinite(au) else None,
                             "ask_dn": round(float(ad), 4) if np.isfinite(ad) else None,
                             "rate": rate, "up_won": rid == "0"})
        kcache.clear()
        print(date, flush=True)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


def main() -> None:
    from sklearn.isotonic import IsotonicRegression
    pts = build_points()
    print(f"decision points: {len(pts)}", flush=True)
    tr = pts.filter(pl.col("date") <= TRAIN_END)
    models = {}
    for blo, bhi in TREM_BUCKETS:
        s = tr.filter((pl.col("t_rem") > blo) & (pl.col("t_rem") <= bhi))
        if len(s) < 500:
            continue
        iso = IsotonicRegression(y_min=0.001, y_max=0.999, out_of_bounds="clip")
        iso.fit(s["z"].to_numpy(), s["up_won"].to_numpy().astype(float))
        models[(blo, bhi)] = iso

    def p_up(z, t_rem):
        for (blo, bhi), m in models.items():
            if blo < t_rem <= bhi:
                return float(m.predict([z])[0])
        return None

    results = []
    for margin in MARGINS:
        taken: dict[int, bool] = {}
        for r in pts.sort("date", "wts", "min").iter_rows(named=True):
            if taken.get(r["wts"]):
                continue
            p = p_up(r["z"], r["t_rem"])
            if p is None:
                continue
            for side_up, ask, prob in ((True, r["ask_up"], p),
                                       (False, r["ask_dn"], 1 - p)):
                if ask is None or not (0.02 < ask < 0.98):
                    continue
                if prob - ask - r["rate"] * ask * (1 - ask) < margin:
                    continue
                won = r["up_won"] == side_up
                sh = 5.0 / ask
                pnl = sh * (1.0 if won else 0.0) - 5.0 - sh * r["rate"] * ask * (1 - ask)
                results.append({"margin": margin, "date": r["date"], "wts": r["wts"],
                                "min": r["min"], "side_up": side_up,
                                "ask": ask, "p": round(prob, 4), "won": won,
                                "pnl": round(pnl, 4)})
                taken[r["wts"]] = True
                break
    df = pl.DataFrame(results, infer_schema_length=None)
    df.write_parquet("results/nix1h_sniper.parquet")
    for margin in MARGINS:
        c = df.filter(pl.col("margin") == margin)
        for lab, sel in (("TRAIN", c.filter(pl.col("date") <= TRAIN_END)),
                         ("VAL", c.filter(pl.col("date") > TRAIN_END))):
            p = sel["pnl"].to_numpy()
            if len(p) < 2:
                print(f"m={margin} {lab}: n={len(p)}")
                continue
            mu, sd = p.mean(), p.std(ddof=1)
            print(f"m={margin} {lab}: n={len(p)} pnl=${p.sum():.2f} mean=${mu:.3f} "
                  f"t={mu / (sd / np.sqrt(len(p))):.2f} wr={(p > 0).mean():.1%}")
    print("SNIPER DONE", flush=True)


if __name__ == "__main__":
    main()
