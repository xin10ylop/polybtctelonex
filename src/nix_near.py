"""NIXULTIMATE N7 — near-resolution maker harvest (the 'stingo43' archetype,
but as the RESTING counterparty, so the taker-fee wall does not apply).

nix1's fresh-OOS diagnosis: in the final seconds the winning side sits at
0.98-0.99 and a TAKER cannot clear fair-ask-fee >= 2c. But a MAKER bid pays
zero fee: buying the near-certain side at B wins (1-B) with prob ~fair and
loses B with prob ~(1-fair). Breakeven win prob = B. Anyone market-selling
the winner into our bid in the last seconds (panic hedgers, position
flatteners) is the counterparty.

Two gates for the 'near-certain' call at T = w + toff:
  pm    the crowd itself: Up BBO mid >= G (or <= 1-G) as-of T  [no Chainlink]
  hyb   free hybrid nowcast fair >= F                          [Chainlink bcast]

Placement is post-only: requires B < ask as-of T (in token space). Fill =
strict trade-through print < B while live [T+250ms .. end of window tape].
$5 stake, S = 5/B shares, zero fee, redeem at resolution.

Splits: pm-gate on full 5m era (train <= Mar 19 / val Mar 20 - May 12);
hyb-gate only has Apr 2+ data -> internal fit (Apr 2-25) / validate (Apr 26-
May 12), labelled hfit/hval. Mining dates <= 2026-05-12 only.
Output: results/nix_near.parquet + leaderboard.
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

TRAIN_END = "2026-03-19"
HFIT_END = "2026-04-25"
MINE_END = "2026-05-12"
TOFFS = [290, 294, 297]
BIDS = [0.97, 0.98, 0.985, 0.99]
PM_GATES = [0.93, 0.95, 0.97]
HYB_GATES = [0.995, 0.999]
BLAT = 150_000
STAKE = 5.0


def hybrid_fair_fn(date: str):
    """Returns fair(w_, T) -> (fair_prob, dir_up) or None, using only
    broadcast-available Chainlink + Binance (same construction as nix1)."""
    try:
        cp = loader.load_crypto_prices([date]).collect().sort("timestamp_us")
        bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return None
    ct = cp["timestamp_us"].to_numpy()
    sv = cp["server_timestamp_us"].to_numpy()
    clog = np.log(cp["price"].to_numpy().astype(float))
    bt = bn["ts_us"].to_numpy()
    blog = np.log(bn["price"].to_numpy().astype(float))

    def fair(w_: int, T: int):
        i_open = np.searchsorted(ct, w_ * 1_000_000, "left")
        if i_open >= len(ct) or sv[i_open] > T:
            return None
        j0 = np.searchsorted(ct, (w_ - 300) * 1_000_000, "left")
        if i_open - j0 < 30:
            return None
        rets = np.diff(clog[j0:i_open])
        dts = np.diff(ct[j0:i_open]) / 1e6
        sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
        if not (np.isfinite(sig) and sig > 0):
            return None
        kb = np.searchsorted(sv, T, "right") - 1
        if kb < i_open:
            return None
        b1 = np.searchsorted(bt, ct[kb] + BLAT, "right") - 1
        b2 = np.searchsorted(bt, T - BLAT, "right") - 1
        if b1 < 0 or b2 <= b1:
            return None
        delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
        t_rem = max(w_ + 300 - T / 1_000_000, 0.25)
        z = delta / (sig * math.sqrt(t_rem))
        return float(norm.cdf(abs(z))), bool(z > 0)

    return fair


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
        hfair = hybrid_fair_fn(date)
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
        qw = q["wts"].to_numpy()
        qts = q["local_timestamp_us"].to_numpy()
        qbid = q["bid_price"].to_numpy().astype(np.float64)
        qask = q["ask_price"].to_numpy().astype(np.float64)
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
            for toff in TOFFS:
                T = (w_ + toff) * 1_000_000
                kq = np.searchsorted(qts[qlo:qhi], T, "right") - 1
                if kq < 0:
                    continue
                bidq, askq = qbid[qlo + kq], qask[qlo + kq]
                mid = (bidq + askq) / 2
                a = np.searchsorted(seg_t, T + 250_000, "right")
                if thi - tlo <= a:
                    continue
                mn = seg_p[a:].min() if a < len(seg_p) else np.nan
                mx = seg_p[a:].max() if a < len(seg_p) else np.nan
                if not np.isfinite(mn):
                    continue
                # candidate signals: (gate_name, gate_val, dir_up)
                sigs = []
                for G in PM_GATES:
                    if mid >= G:
                        sigs.append((f"pm{G}", True))
                    elif mid <= 1 - G:
                        sigs.append((f"pm{G}", False))
                if hfair is not None:
                    hf = hfair(int(w_), T)
                    if hf is not None:
                        f_, du_ = hf
                        for F in HYB_GATES:
                            if f_ >= F:
                                sigs.append((f"hyb{F}", du_))
                if not sigs:
                    continue
                for gate, dir_up in sigs:
                    # token-space ask for the chosen side (post-only check)
                    tok_ask = askq if dir_up else 1.0 - bidq
                    for B in BIDS:
                        if B >= tok_ask:
                            continue
                        filled = (mn < B) if dir_up else (mx > 1.0 - B)
                        if not filled:
                            continue
                        S = STAKE / B
                        win = up_won if dir_up else not up_won
                        pnl = S * (1.0 - B) if win else -S * B
                        recs.append((date, gate, toff, B, round(pnl, 4)))
    df = pl.DataFrame(recs, schema=["date", "gate", "toff", "B", "pnl"], orient="row")
    df.write_parquet("results/nix_near.parquet")
    rows = []
    for (gate, toff, B), g in df.group_by(["gate", "toff", "B"]):
        r = {"gate": gate, "toff": toff, "B": B}
        hyb = str(gate).startswith("hyb")
        cut = HFIT_END if hyb else TRAIN_END
        s1, s2 = ("hfit", "hval") if hyb else ("train", "val")
        for split, gg in ((s1, g.filter(pl.col("date") <= cut)),
                          (s2, g.filter(pl.col("date") > cut))):
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
        rows.append(r)
    lb = pl.DataFrame(rows, infer_schema_length=None)
    pl.Config.set_tbl_cols(14)
    pl.Config.set_tbl_rows(80)
    print(lb.filter(pl.col("gate").str.starts_with("pm")).sort("val_t", descending=True, nulls_last=True))
    print(lb.filter(pl.col("gate").str.starts_with("hyb")).sort("hval_t", descending=True, nulls_last=True))


if __name__ == "__main__":
    run()
