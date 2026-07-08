"""NIXULTIMATE full-timeline audit — month by month, Apr 2 to Jul 7.

USER-ORDERED DEPLOYMENT AUDIT. This script reads the May 13 - Jul 5 period,
which is the spent HOLDOUT (its one-shot was consumed by Appendix 6). The
strategy parameters here are FROZEN and may not be changed in response to
anything this audit shows — it exists to time the edge's decay for the
deployment decision and to calibrate kill-switches, not to select or tune.
Run with --holdout-audit to acknowledge this; refuses otherwise.

Both engines (nix1 = 5m hybrid, N8 = 15m hybrid), identical frozen gates.
Per calendar month: trades, $/trade, t, win rate, $/day, plus gate
diagnostics (z-passed windows, valid-ask rate, EV-blocked rate, median ask
of z-passed windows) — the "how open is the gate" curve.

Also: basis-guard cost analysis — the defensive filter (skip contrarian
entries ask<0.5 when |Binance - Chainlink anchor| > 5bp) that would have
blocked both Jul 6 fake signals; reports what it costs on dev.

Chainlink broadcast data exists only from 2026-04-02 — no engine (ours or
anyone's) can be simulated before that date.
Output: results/nix_audit_monthly.parquet + results/nix_audit_trades.parquet
"""
from __future__ import annotations

import datetime as dt
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
BLAT = 150_000
FILL_LAT = 250_000
STAKE = 5.0
BASIS_GUARD_BP = 5.0
START, END = "2026-04-02", "2026-07-07"
HOLDOUT_LO, HOLDOUT_HI = "2026-05-13", "2026-07-05"


def read_daily(fam: str, channel: str, date: str) -> pl.DataFrame | None:
    for root in (f"data/processed/daily/{fam}/{channel}/{date}.parquet",
                 f"data/HOLDOUT/daily/{fam}/{channel}/{date}.parquet"):
        if os.path.exists(root):
            return pl.read_parquet(root)
    return None


def run_engine(fam: str, dur: int, dates: list[str]) -> tuple[list[dict], list[dict]]:
    toff = dur - 3
    trades, gates = [], []
    for date in dates:
        b = read_daily(fam, "bookcurves", date)
        tr = read_daily(fam, "trades", date)
        cpp = f"data/processed/daily/crypto_prices/{date}.parquet"
        bnp = f"data/processed/binance/aggTrades/{date}.parquet"
        if b is None or tr is None or not os.path.exists(cpp) or not os.path.exists(bnp):
            continue
        cp = pl.read_parquet(cpp).sort("timestamp_us")
        bn = pl.read_parquet(bnp).sort("ts_us")
        b = b.sort("wts", "local_timestamp_us")
        tr = tr.sort("wts", "local_timestamp_us")
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta(fam, d0, d0 + 86400)
        ct = cp["timestamp_us"].to_numpy()
        sv = cp["server_timestamp_us"].to_numpy()
        cpx = cp["price"].to_numpy().astype(float)
        clog = np.log(cpx)
        bt = bn["ts_us"].to_numpy()
        bpx = bn["price"].to_numpy().astype(float)
        blog = np.log(bpx)
        bw = b["wts"].to_numpy()
        bts = b["local_timestamp_us"].to_numpy()
        b_buy = b["buy_avgpx_50"].to_numpy().astype(float)
        b_sell = b["sell_avgpx_50"].to_numpy().astype(float)
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(float)
        rate = fees.params(date, fam)[0]
        for r_ in meta.iter_rows(named=True):
            w_ = r_["wts"]
            rid = r_["result_id"]
            if rid not in ("0", "1"):
                continue
            up_won = 1.0 if rid == "0" else 0.0
            i_open = np.searchsorted(ct, w_ * 1_000_000, "left")
            T = (w_ + toff) * 1_000_000
            if i_open >= len(ct) or sv[i_open] > T:
                continue
            j0 = np.searchsorted(ct, (w_ - 300) * 1_000_000, "left")
            if i_open - j0 < 30:
                continue
            rets = np.diff(clog[j0:i_open])
            dts = np.diff(ct[j0:i_open]) / 1e6
            sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
            if not (np.isfinite(sig) and sig > 0):
                continue
            kb = np.searchsorted(sv, T, "right") - 1
            if kb < i_open:
                continue
            b1 = np.searchsorted(bt, ct[kb] + BLAT, "right") - 1
            b2 = np.searchsorted(bt, T - BLAT, "right") - 1
            if b1 < 0 or b2 <= b1:
                continue
            delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
            z = delta / (sig * math.sqrt(dur - toff))
            if abs(z) < Z_THR:
                continue
            basis_bp = abs(blog[b1] - clog[kb]) * 1e4  # Binance vs CL anchor gap
            fair = norm.cdf(abs(z))
            dir_up = z > 0
            g = {"date": date, "fam": fam, "wts": int(w_), "stage": "z"}
            lo = np.searchsorted(bw, w_, "left")
            hi = np.searchsorted(bw, w_, "right")
            kk = np.searchsorted(bts[lo:hi], T + FILL_LAT, "right") - 1 if hi > lo else -1
            if kk < 0:
                gates.append(g)
                continue
            ask = b_buy[lo + kk] if dir_up else 1 - b_sell[lo + kk]
            if not (np.isfinite(ask) and 0.02 < ask < 0.995):
                g["stage"] = "no_ask"
                gates.append(g)
                continue
            g["ask"] = round(float(ask), 4)
            if fair - ask - rate * ask * (1 - ask) < EV_MARGIN:
                g["stage"] = "ev_block"
                gates.append(g)
                continue
            tlo = np.searchsorted(tw, w_, "left")
            thi = np.searchsorted(tw, w_, "right")
            stt = tts[tlo:thi]
            sp = tpx[tlo:thi]
            tok = sp if dir_up else 1 - sp
            m1 = np.searchsorted(stt, T + FILL_LAT, "left")
            m2 = np.searchsorted(stt, T + FILL_LAT + 1_500_000, "right")
            pr = tok[m1:m2]
            okm = pr <= ask + 0.01 if len(pr) else np.array([False])
            if not okm.any():
                g["stage"] = "no_fill"
                gates.append(g)
                continue
            g["stage"] = "traded"
            gates.append(g)
            fillpx = max(ask, float(pr[okm].min()))
            win = up_won if dir_up else 1 - up_won
            sh = STAKE / fillpx
            pnl = sh * win - STAKE - sh * rate * fillpx * (1 - fillpx)
            trades.append({"date": date, "fam": fam, "wts": int(w_),
                           "ask": round(float(ask), 4), "fill": round(fillpx, 4),
                           "basis_bp": round(float(basis_bp), 2),
                           "guard_blocked": bool(ask < 0.5 and basis_bp > BASIS_GUARD_BP),
                           "pnl": round(float(pnl), 4)})
    return trades, gates


def month_of(d: str) -> str:
    return d[:7]


def era_of(d: str) -> str:
    if d < HOLDOUT_LO:
        return "dev"
    if d <= HOLDOUT_HI:
        return "HOLDOUT-audit"
    return "fresh"


def main() -> None:
    if "--holdout-audit" not in sys.argv:
        sys.exit("Refusing: this audit reads the spent HOLDOUT period. "
                 "Re-run with --holdout-audit to acknowledge (frozen params, no retuning).")
    print("*** HOLDOUT AUDIT READ: frozen parameters, deployment audit only, "
          "no retuning permitted on the basis of these results ***")
    all_dates = sorted({p[:10] for p in os.listdir("data/processed/daily/crypto_prices")})
    dates = [d for d in all_dates if START <= d <= END]
    all_tr, all_g = [], []
    for fam, dur in (("5m", 300), ("15m", 900)):
        trs, gs = run_engine(fam, dur, dates)
        all_tr += trs
        all_g += gs
        print(f"{fam}: {len(trs)} trades, {len(gs)} z-passed windows", flush=True)
    tdf = pl.DataFrame(all_tr)
    gdf = pl.DataFrame(all_g)
    tdf.write_parquet("results/nix_audit_trades.parquet")
    rows = []
    for fam in ("5m", "15m"):
        for mo in sorted(set(month_of(d) for d in dates)):
            g = gdf.filter((pl.col("fam") == fam) & (pl.col("date").str.starts_with(mo)))
            t = tdf.filter((pl.col("fam") == fam) & (pl.col("date").str.starts_with(mo)))
            if g.is_empty():
                continue
            ndays = g["date"].n_unique()
            p = t["pnl"].to_numpy()
            mu = p.mean() if len(p) else 0.0
            sd = p.std(ddof=1) if len(p) > 1 else 0.0
            asks = g.filter(pl.col("ask").is_not_null())["ask"]
            rows.append({
                "fam": fam, "month": mo,
                "era": "/".join(sorted(set(era_of(d) for d in g["date"].unique()))),
                "days": ndays, "z_passed": len(g),
                "ev_block%": round(float((g["stage"] == "ev_block").mean()), 3),
                "no_ask%": round(float((g["stage"] == "no_ask").mean()), 3),
                "med_ask": round(float(asks.median()), 3) if len(asks) else None,
                "n_trades": len(p),
                "pnl": round(float(p.sum()), 2),
                "$/trade": round(float(mu), 3) if len(p) else None,
                "t": round(float(mu / (sd / np.sqrt(len(p)))), 1) if sd > 0 else None,
                "wr": round(float((p > 0).mean()), 3) if len(p) else None,
                "$/day": round(float(p.sum()) / ndays, 2),
            })
    mdf = pl.DataFrame(rows, infer_schema_length=None)
    mdf.write_parquet("results/nix_audit_monthly.parquet")
    pl.Config.set_tbl_rows(20)
    pl.Config.set_tbl_cols(16)
    print(mdf.sort("fam", "month"))
    # basis-guard cost/benefit on the whole timeline
    for fam in ("5m", "15m"):
        t = tdf.filter(pl.col("fam") == fam)
        blocked = t.filter(pl.col("guard_blocked"))
        print(f"\nbasis guard ({fam}): would block {len(blocked)}/{len(t)} trades "
              f"worth ${float(blocked['pnl'].sum()):.2f} of ${float(t['pnl'].sum()):.2f} "
              f"(blocked wr {float((blocked['pnl'] > 0).mean()) if len(blocked) else 0:.0%})")


if __name__ == "__main__":
    main()
