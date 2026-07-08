"""Free-feed hybrid nowcast — the oracle final-seconds trade WITHOUT the paid feed.

Synthesizes the private Chainlink Data Streams feed from two free sources:
  anchor   = latest Chainlink tick ALREADY BROADCAST by Polymarket at decision
             time T (server_timestamp_us <= T; the payload itself is stale by
             the ~1.1-1.7s broadcast delay)
  nowcast  = Binance aggTrades log-return from the anchor's SOURCE time
             (+150ms feed latency) to T-150ms, exploiting Binance leading the
             Chainlink source by ~1.25s
  estimate = clog[anchor] + blog[b2] - blog[b1] - clog[open]

All gates are the FROZEN oracle-trade parameters (no new tuning):
  toff=297s, |z|>=1.5 with sigma from prior-300s Chainlink feed (per-sqrt-sec),
  EV gate fair-ask-fee >= 0.02, taker fill from $50 book-walk curve as-of
  T+250ms, tape-validated (a real print <= ask+1c within [T+250ms, T+1.75s]),
  $5 stakes, date-correct taker fees, hold ~3s to resolution.

Usage:
  .venv/bin/python src/oracle_hybrid.py dev                    # Apr 2 - May 12
  .venv/bin/python src/oracle_hybrid.py 2026-07-06 --diagnose  # single day
Output: results/oracle_hybrid_{tag}.parquet (one row per trade) and per-day
summary to stdout. --diagnose additionally prints every z-passed window with
its fair/ask/EV and outcome, including EV-blocked non-trades.
"""
from __future__ import annotations

import datetime as dt
import math
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
import loader
import windows as W
from scipy.stats import norm

# frozen parameters — carried over unchanged from the holdout-confirmed
# oracle_lastsec config; retuning any of these voids the OOS claim
TOFF = 297
Z_THR = 1.5
EV_MARGIN = 0.02
BINANCE_LAT_US = 150_000
FILL_LAT_US = 250_000
STAKE = 5.0


def run_day(date: str) -> tuple[list[dict], list[dict]]:
    """Returns (trades, z_passed) for one date; z_passed includes blocked rows."""
    try:
        cp = loader.load_crypto_prices([date]).collect().sort("timestamp_us")
        b = loader.load_daily("5m", "bookcurves", [date]).collect().sort("wts", "local_timestamp_us")
        tr = loader.load_daily("5m", "trades", [date]).collect().sort("wts", "local_timestamp_us")
        bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return [], []
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0, d0 + 86400)
    ct = cp["timestamp_us"].to_numpy()
    sv = cp["server_timestamp_us"].to_numpy()
    clog = np.log(cp["price"].to_numpy().astype(float))
    bt = bn["ts_us"].to_numpy()
    blog = np.log(bn["price"].to_numpy().astype(float))
    bw = b["wts"].to_numpy()
    bts = b["local_timestamp_us"].to_numpy()
    b_buy = b["buy_avgpx_50"].to_numpy().astype(float)
    b_sell = b["sell_avgpx_50"].to_numpy().astype(float)
    tw = tr["wts"].to_numpy()
    tts = tr["local_timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(float)
    rate = fees.params(date, "5m")[0]
    trades, z_passed = [], []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = 1.0 if rid == "0" else 0.0
        i_open = np.searchsorted(ct, w_ * 1_000_000, "left")
        if i_open >= len(ct) or sv[i_open] > (w_ + TOFF) * 1_000_000:
            continue
        j0 = np.searchsorted(ct, (w_ - 300) * 1_000_000, "left")
        if i_open - j0 < 30:
            continue
        rets = np.diff(clog[j0:i_open])
        dts = np.diff(ct[j0:i_open]) / 1e6
        sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
        if not (np.isfinite(sig) and sig > 0):
            continue
        T = (w_ + TOFF) * 1_000_000
        kb = np.searchsorted(sv, T, "right") - 1  # last tick broadcast by T
        if kb < i_open:
            continue
        b1 = np.searchsorted(bt, ct[kb] + BINANCE_LAT_US, "right") - 1
        b2 = np.searchsorted(bt, T - BINANCE_LAT_US, "right") - 1
        if b1 < 0 or b2 <= b1:
            continue
        delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
        z = delta / (sig * math.sqrt(300 - TOFF))
        if abs(z) < Z_THR:
            continue
        fair = norm.cdf(abs(z))
        dir_up = z > 0
        lo = np.searchsorted(bw, w_, "left")
        hi = np.searchsorted(bw, w_, "right")
        if hi <= lo:
            continue
        kk = np.searchsorted(bts[lo:hi], T + FILL_LAT_US, "right") - 1
        if kk < 0:
            continue
        ask = b_buy[lo + kk] if dir_up else 1 - b_sell[lo + kk]
        if not (np.isfinite(ask) and 0.02 < ask < 0.995):
            continue
        ev = fair - ask - rate * ask * (1 - ask)
        win = up_won if dir_up else 1 - up_won
        row = {"date": date, "wts": int(w_), "dir": "up" if dir_up else "down",
               "z": round(float(z), 2), "fair": round(float(fair), 4),
               "ask": round(float(ask), 4), "ev": round(float(ev), 4),
               "dir_won": bool(win > 0.5)}
        z_passed.append(row)
        if ev < EV_MARGIN:
            continue
        tlo = np.searchsorted(tw, w_, "left")
        thi = np.searchsorted(tw, w_, "right")
        stt = tts[tlo:thi]
        sp = tpx[tlo:thi]
        tok = sp if dir_up else 1 - sp
        m1 = np.searchsorted(stt, T + FILL_LAT_US, "left")
        m2 = np.searchsorted(stt, T + FILL_LAT_US + 1_500_000, "right")
        pr = tok[m1:m2]
        ok = pr <= ask + 0.01 if len(pr) else np.array([False])
        if not ok.any():
            continue
        fillpx = max(ask, float(pr[ok].min()))
        sh = STAKE / fillpx
        pnl = sh * win - STAKE - sh * rate * fillpx * (1 - fillpx)
        trades.append({**row, "fill": round(fillpx, 4), "pnl": round(float(pnl), 4)})
    return trades, z_passed


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    diagnose = "--diagnose" in sys.argv
    if args and args[0] == "dev":
        dates = [d for d in loader.available_dates("5m", "bookcurves") if d >= "2026-04-02"]
        tag = "dev"
    else:
        dates = args
        tag = "_".join(dates)
    all_tr, all_zp = [], []
    for date in dates:
        trs, zps = run_day(date)
        all_tr += trs
        all_zp += zps
        p = np.array([t["pnl"] for t in trs]) if trs else np.array([])
        print(f"{date}: z-passed {len(zps):3d}  trades {len(trs):3d}  "
              f"pnl ${p.sum():7.2f}  wr {(p > 0).mean() if len(p) else 0:.0%}")
    if all_tr:
        p = np.array([t["pnl"] for t in all_tr])
        mu, sd = p.mean(), p.std(ddof=1)
        t = mu / (sd / math.sqrt(len(p))) if sd > 0 else 0.0
        print(f"\nTOTAL [{tag}]: n={len(p)} pnl=${p.sum():.2f} mean=${mu:.2f} "
              f"t={t:.1f} wr={(p > 0).mean():.1%}")
        pl.DataFrame(all_tr).write_parquet(f"results/oracle_hybrid_{tag}.parquet")
    else:
        print(f"\nTOTAL [{tag}]: n=0 (no trades)")
    if diagnose and all_zp:
        print("\nAll z-passed windows (incl. EV-blocked):")
        print(pl.DataFrame(all_zp).sort("date", "wts"))


if __name__ == "__main__":
    main()
