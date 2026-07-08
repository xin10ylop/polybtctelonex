"""NIXULTIMATE N8 — nix1's frozen signal on the 15m family (sibling market).

Identical construction to src/oracle_hybrid.py (free-feed hybrid nowcast,
FROZEN gates: 3s before close, |z|>=1.5, EV margin 0.02, $50-bucket book-walk
fill at T+250ms, tape-validated, $5 stakes) — applied to the 15m up/down
market instead of the 5m. Not a retune: every parameter carried over; the
only change is the market. Hypothesis: the final-seconds competition that
compressed 5m books to 98-99c is thinner on the 15m, and the 15m fee rate is
lower (r=0.0624 vs 0.070).

Dev era Apr 2 - May 12 (crypto_prices coverage), one leaderboard row per day.
2026-07-06/07 reserved for the frozen fresh-OOS check.
Output: results/nix_15m_lastsec_{tag}.parquet
"""
from __future__ import annotations

import datetime as dt
import math
import sys

import numpy as np
import polars as pl
from scipy.stats import norm

sys.path.insert(0, "src")
import fees
import loader
import windows as W

DUR = 900
TOFF = DUR - 3          # same "3 seconds before close" as the frozen 5m config
Z_THR = 1.5
EV_MARGIN = 0.02
BINANCE_LAT_US = 150_000
FILL_LAT_US = 250_000
STAKE = 5.0


def run_day(date: str) -> list[dict]:
    try:
        cp = loader.load_crypto_prices([date]).collect().sort("timestamp_us")
        b = loader.load_daily("15m", "bookcurves", [date]).collect().sort("wts", "local_timestamp_us")
        tr = loader.load_daily("15m", "trades", [date]).collect().sort("wts", "local_timestamp_us")
        bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("15m", d0, d0 + 86400)
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
    rate = fees.params(date, "15m")[0]
    trades = []
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
        kb = np.searchsorted(sv, T, "right") - 1
        if kb < i_open:
            continue
        b1 = np.searchsorted(bt, ct[kb] + BINANCE_LAT_US, "right") - 1
        b2 = np.searchsorted(bt, T - BINANCE_LAT_US, "right") - 1
        if b1 < 0 or b2 <= b1:
            continue
        delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
        z = delta / (sig * math.sqrt(DUR - TOFF))
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
        if fair - ask - rate * ask * (1 - ask) < EV_MARGIN:
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
        win = up_won if dir_up else 1 - up_won
        sh = STAKE / fillpx
        pnl = sh * win - STAKE - sh * rate * fillpx * (1 - fillpx)
        trades.append({"date": date, "wts": int(w_), "dir": "up" if dir_up else "down",
                       "z": round(float(z), 2), "fair": round(float(fair), 4),
                       "ask": round(float(ask), 4), "fill": round(fillpx, 4),
                       "pnl": round(float(pnl), 4)})
    return trades


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args and args[0] == "dev":
        dates = [d for d in loader.available_dates("15m", "bookcurves")
                 if "2026-04-02" <= d <= "2026-05-12"]
        tag = "dev"
    else:
        dates = args
        tag = "_".join(dates)
    all_tr = []
    for date in dates:
        trs = run_day(date)
        all_tr += trs
        p = np.array([t["pnl"] for t in trs]) if trs else np.array([])
        print(f"{date}: trades {len(trs):3d}  pnl ${p.sum():7.2f}  "
              f"wr {(p > 0).mean() if len(p) else 0:.0%}", flush=True)
    if all_tr:
        p = np.array([t["pnl"] for t in all_tr])
        mu, sd = p.mean(), p.std(ddof=1)
        t = mu / (sd / math.sqrt(len(p))) if sd > 0 else 0.0
        print(f"\nTOTAL [{tag}]: n={len(p)} pnl=${p.sum():.2f} mean=${mu:.2f} "
              f"t={t:.1f} wr={(p > 0).mean():.1%}")
        pl.DataFrame(all_tr).write_parquet(f"results/nix_15m_lastsec_{tag}.parquet")
    else:
        print(f"\nTOTAL [{tag}]: n=0")


if __name__ == "__main__":
    main()
