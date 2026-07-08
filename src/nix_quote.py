"""NIXULTIMATE N5 — model-quoting maker: nix1's pricing brain as the house.

nix1 proved the free hybrid nowcast prices these markets better than the
resting book (25/27 correct fresh-OOS) but taking at the end is fee-walled
and competed. Flip roles: MID-window, when the crowd's mid is dislocated
from model fair by d+, rest a bid on the underpriced token at fair - m.
Impatient humans crossing the spread fill us at a model-certified discount.
Maker = zero fee, both legs.

At T = w + toff:  fair_up = Phi(z) from the broadcast-safe hybrid nowcast
  fair_up - mid5 >= +d  ->  bid Up   at fair_up - m
  fair_up - mid5 <= -d  ->  bid Down at (1 - fair_up) - m
Post-only (level < token ask). Live [T+250ms, T+H]; fill = strict
trade-through; exit maker +5c after fill or hold to resolution. $5 stakes.

Data era: crypto_prices exists Apr 2+ -> internal split fit (Apr 2-25) /
validate (Apr 26 - May 12). Mining dates <= 2026-05-12 only.
Output: results/nix_quote.parquet + leaderboard.
"""
from __future__ import annotations

import datetime as dt
import math
import sys

import numpy as np
import polars as pl
from scipy.stats import norm

sys.path.insert(0, "src")
import loader
import windows as W

FIT_END = "2026-04-25"
MINE_END = "2026-05-12"
TOFFS = [60, 150, 240]
DTHRS = [0.05, 0.08, 0.12]
MARGINS = [0.03, 0.05, 0.08]
HOLDS = [30, 60]
EXITS = ["hold", "mk5"]
BLAT = 150_000
STAKE = 5.0


def run() -> None:
    recs = []
    dates = [d for d in loader.available_dates("5m", "trades")
             if "2026-04-02" <= d <= MINE_END]
    for date in dates:
        try:
            tr = (loader.load_daily("5m", "trades", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
            q5 = (loader.load_daily("5m", "quotes", [date]).collect()
                  .sort("wts", "local_timestamp_us"))
            cp = loader.load_crypto_prices([date]).collect().sort("timestamp_us")
            bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
        except FileNotFoundError:
            continue
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        meta = W.market_meta("5m", d0, d0 + 86400)
        res = {int(w): r for w, r in zip(meta["wts"], meta["result_id"])}
        ct = cp["timestamp_us"].to_numpy()
        sv = cp["server_timestamp_us"].to_numpy()
        clog = np.log(cp["price"].to_numpy().astype(float))
        bt = bn["ts_us"].to_numpy()
        blog = np.log(bn["price"].to_numpy().astype(float))
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
        qw = q5["wts"].to_numpy()
        qts = q5["local_timestamp_us"].to_numpy()
        qb = q5["bid_price"].to_numpy().astype(np.float64)
        qa = q5["ask_price"].to_numpy().astype(np.float64)
        fit = date <= FIT_END
        for w_ in np.unique(tw):
            rid = res.get(int(w_))
            if rid not in ("0", "1"):
                continue
            up_won = rid == "0"
            i_open = np.searchsorted(ct, w_ * 1_000_000, "left")
            if i_open >= len(ct):
                continue
            j0 = np.searchsorted(ct, (w_ - 300) * 1_000_000, "left")
            if i_open - j0 < 30:
                continue
            rets = np.diff(clog[j0:i_open])
            dts = np.diff(ct[j0:i_open]) / 1e6
            sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
            if not (np.isfinite(sig) and sig > 0):
                continue
            tlo = np.searchsorted(tw, w_, "left")
            thi = np.searchsorted(tw, w_, "right")
            seg_t = tts[tlo:thi]
            seg_p = tpx[tlo:thi]
            qlo = np.searchsorted(qw, w_, "left")
            qhi = np.searchsorted(qw, w_, "right")
            for toff in TOFFS:
                T = (w_ + toff) * 1_000_000
                if sv[i_open] > T:
                    continue
                kb = np.searchsorted(sv, T, "right") - 1
                if kb < i_open:
                    continue
                b1 = np.searchsorted(bt, ct[kb] + BLAT, "right") - 1
                b2 = np.searchsorted(bt, T - BLAT, "right") - 1
                if b1 < 0 or b2 <= b1:
                    continue
                delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
                z = delta / (sig * math.sqrt(300 - toff))
                fair_up = float(norm.cdf(z))
                kq = np.searchsorted(qts[qlo:qhi], T, "right") - 1
                if kq < 0:
                    continue
                bidq, askq = qb[qlo + kq], qa[qlo + kq]
                mid5 = (bidq + askq) / 2
                d = fair_up - mid5
                for dthr in DTHRS:
                    if abs(d) < dthr:
                        continue
                    dir_up = d > 0
                    fair_tok = fair_up if dir_up else 1.0 - fair_up
                    tok_ask = askq if dir_up else 1.0 - bidq
                    for m in MARGINS:
                        L = fair_tok - m
                        if not (0.02 < L < 0.97) or L >= tok_ask:
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
                            tok_after = (seg_p[fi + 1:] if dir_up
                                         else 1.0 - seg_p[fi + 1:])
                            hit5 = (tok_after > L + 0.05).any() if len(tok_after) else False
                            win = up_won if dir_up else not up_won
                            hold_pnl = S * (1.0 - L) if win else -S * L
                            for ex in EXITS:
                                pnl = S * 0.05 if (ex == "mk5" and hit5) else hold_pnl
                                recs.append((toff, dthr, m, H, ex, fit, round(pnl, 4)))
    df = pl.DataFrame(recs, schema=["toff", "dthr", "m", "H", "exit", "fit", "pnl"],
                      orient="row")
    df.write_parquet("results/nix_quote.parquet")
    rows = []
    for key, g_ in df.group_by(["toff", "dthr", "m", "H", "exit"]):
        r = dict(zip(["toff", "dthr", "m", "H", "exit"], key))
        for split, gg in (("hfit", g_.filter(pl.col("fit"))),
                          ("hval", g_.filter(~pl.col("fit")))):
            p = gg["pnl"].to_numpy()
            n = len(p)
            r[f"{split}_n"] = n
            if n < 2:
                continue
            mu, sd_ = p.mean(), p.std(ddof=1)
            r[f"{split}_pnl"] = round(float(p.sum()), 2)
            r[f"{split}_t"] = round(float(mu / (sd_ / np.sqrt(n))), 2) if sd_ > 0 else 0.0
            r[f"{split}_wr"] = round(float((p > 0).mean()), 3)
        rows.append(r)
    lb = pl.DataFrame(rows, infer_schema_length=None).sort("hval_t", descending=True,
                                                           nulls_last=True)
    pl.Config.set_tbl_cols(16)
    pl.Config.set_tbl_rows(40)
    print(lb)


if __name__ == "__main__":
    run()
