"""Scalp pass 4 (2026-07-11) — the boundary-print staleness trade.

MECHANISM (thought-first, not mined): a window's open = the first Chainlink
print at/after the boundary, and Chainlink print VALUES lag Binance by
~0.5-1.1s (the proven nix1/holdout edge). In the last second before open we
can hold a Binance move the opening print won't fully include -> the window
opens with its reference drawn where price USED to be -> the side of the
banked move starts ahead. Venue-basis noise cancels (open and close come
from the same feed). This is the user's exact pre-open scalp shape with a
mechanistic which-side signal, at entry timings never tested (-1s, -0.5s).

Signal (frozen nix1 form, NOT re-mined): anchor = last Chainlink broadcast
(local_ts <= T0); g = ln(Binance(T0-150ms)/anchor) in bp; sigma300 = 1s-grid
Binance vol over prior 300s scaled to 5min; z = g/sigma300. Side = sign(g).

MEASUREMENT FIRST: distribution of open-print staleness vs Binance(boundary),
P(win | z quintile), and whether the pre-open ask already prices the tilt.

TRADE GRID (pre-declared, 32 cells, survivor bar: positive AND t >= 3.5):
  T0 in {-5,-2,-1,-0.5}s x ask cap {0.51, 0.53} x gate |z| >= {0.05, 0.15}
  x exit {TP+4c with 10s bail-out, TP+4c resting + hold to resolution}
Fees on (taker entry + taker bail; TP maker leg free). $10 stakes.

Era: Chainlink feed days 2026-04-02..05-12 (+ fresh 07-06/07 reported apart).
Output: stdout report + results/nix_scalp4_rows.parquet.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
import loader
import windows as W

T0S = (-5.0, -2.0, -1.0, -0.5)
CAPS = (0.51, 0.53)
ZG = (0.05, 0.15)
LAT = 250_000
BLAT = 150_000
LOOK_US = 1_000_000  # oracle value-lag window (~1.1s measured, Appendix 6)
TP = 0.04
BAIL = 10
STAKE = 10.0


def day_rows(date: str) -> list[dict]:
    clp = f"data/processed/daily/crypto_prices/{date}.parquet"
    if not os.path.exists(clp):
        return []
    try:
        tr = (loader.load_daily("5m", "trades", [date]).collect()
              .sort("wts", "timestamp_us"))
        b = (loader.load_daily("5m", "bookcurves", [date]).collect()
             .sort("wts", "timestamp_us"))
        bn = pl.read_parquet(
            f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    cl = pl.read_parquet(clp).sort("timestamp_us")
    cts_src = cl["timestamp_us"].to_numpy()          # source time (resolution)
    cts_loc = cl["local_timestamp_us"].to_numpy()    # availability
    cpx = cl["price"].to_numpy().astype(np.float64)
    loc_order = np.argsort(cts_loc, kind="stable")
    cts_loc_s, cpx_loc_s = cts_loc[loc_order], cpx[loc_order]

    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0, d0 + 86400)
    tw = tr["wts"].to_numpy(); tts = tr["timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy(); bts = b["timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    bt = bn["ts_us"].to_numpy()
    bpx = bn["price"].to_numpy().astype(np.float64)
    blog = np.log(bpx)
    rate = fees.params(date, "5m")[0]
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        B = w_ * 1_000_000
        # open print + staleness vs Binance at boundary
        ko = int(np.searchsorted(cts_src, B, "left"))
        if ko >= len(cts_src):
            continue
        open_print = cpx[ko]
        kb = int(np.searchsorted(bt, B, "right")) - 1
        stale_bp = (math.log(open_print / bpx[kb]) * 1e4) if kb >= 0 else np.nan
        tlo, thi = np.searchsorted(tw, w_, "left"), np.searchsorted(tw, w_, "right")
        blo, bhi = np.searchsorted(bw, w_, "left"), np.searchsorted(bw, w_, "right")
        if bhi <= blo:
            continue
        seg_t, seg_p = tts[tlo:thi], tpx[tlo:thi]
        sb_t = bts[blo:bhi]

        def tob(T):
            k = int(np.searchsorted(sb_t, T, "right")) - 1
            return (bid0[blo + k], ask0[blo + k]) if k >= 0 else (np.nan, np.nan)

        # sigma300 once per window (at boundary-5s, prior 300s, 1s grid)
        g0 = B - 5_000_000 - np.arange(300, -1, -1) * 1_000_000
        gi = np.searchsorted(bt, g0, "right") - 1
        gp = np.where(gi >= 0, blog[np.maximum(gi, 0)], np.nan)
        sig300 = float(np.nanstd(np.diff(gp))) * math.sqrt(300.0) * 1e4
        if not (np.isfinite(sig300) and sig300 > 0):
            continue
        for t0 in T0S:
            T0 = B + int(t0 * 1_000_000)
            ka = int(np.searchsorted(cts_loc_s, T0, "right")) - 1
            kbn = int(np.searchsorted(bt, T0 - BLAT, "right")) - 1
            kb1 = int(np.searchsorted(bt, T0 - BLAT - LOOK_US, "right")) - 1
            if ka < 0 or kbn < 0 or kb1 < 0:
                continue
            # basis-proof signal: pure Binance return over the oracle's ~1s
            # value-lag window (cross-feed level gap is basis-contaminated)
            g = math.log(bpx[kbn] / bpx[kb1]) * 1e4
            g_cross = math.log(bpx[kbn] / cpx_loc_s[ka]) * 1e4
            z = g / sig300
            side = "up" if g > 0 else "down"
            bq, aq = tob(T0 + LAT)
            ask = aq if side == "up" else (1 - bq if np.isfinite(bq) else np.nan)
            row = {"date": date, "wts": int(w_), "t0": t0,
                   "g_bp": round(g, 3), "g_cross_bp": round(g_cross, 3),
                   "z": round(z, 4),
                   "sig300": round(sig300, 2),
                   "anchor_age_s": round((T0 - cts_loc_s[ka]) / 1e6, 2),
                   "stale_bp": round(stale_bp, 3) if np.isfinite(stale_bp) else None,
                   "side": side, "win": int((side == "up") == up_won),
                   "ask": round(float(ask), 4) if np.isfinite(ask) else None,
                   "pnl_bail": None, "pnl_hold": None}
            if np.isfinite(ask) and ask <= max(CAPS):
                sh = STAKE / ask
                fee_in = rate * ask * (1 - ask) * sh
                tok = seg_p if side == "up" else 1.0 - seg_p
                ifill = np.searchsorted(seg_t, T0 + LAT, "right")
                hits = np.nonzero(tok[ifill:] > ask + TP)[0]
                tau = int(seg_t[ifill + hits[0]]) if len(hits) else None
                tp_pnl = sh * TP - fee_in
                if tau is not None and tau <= B + BAIL * 1_000_000:
                    row["pnl_bail"] = round(tp_pnl, 4)
                else:
                    bq2, aq2 = tob(B + BAIL * 1_000_000 + LAT)
                    xb = bq2 if side == "up" else (1 - aq2 if np.isfinite(aq2) else np.nan)
                    if np.isfinite(xb):
                        row["pnl_bail"] = round(
                            sh * (xb - ask) - fee_in - rate * xb * (1 - xb) * sh, 4)
                row["pnl_hold"] = round(tp_pnl if tau is not None
                                        else sh * row["win"] - STAKE - fee_in, 4)
            rows.append(row)
    return rows


def build() -> pl.DataFrame:
    out = "results/nix_scalp4_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    dates = ([d for d in loader.available_dates("5m", "trades")
              if "2026-04-02" <= d <= "2026-05-12"] + ["2026-07-06", "2026-07-07"])
    all_rows = []
    for date in dates:
        all_rows += day_rows(date)
        print(date, flush=True)
    df = pl.DataFrame(all_rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


def tstat(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 2 else float("nan")


def main() -> None:
    df = build()
    dev = df.filter(pl.col("date") <= "2026-05-12")
    print(f"\nrows {len(df)} ({dev['date'].n_unique()} dev days + fresh)")

    print("\n===== MEASUREMENT: open-print staleness =====")
    st = dev.filter(pl.col("t0") == -0.5)["stale_bp"].drop_nulls().to_numpy()
    print(f"open print vs Binance(boundary): median {np.median(st):+.2f}bp, "
          f"|.|>2bp {np.mean(np.abs(st)>2):.0%}, |.|>5bp {np.mean(np.abs(st)>5):.0%}")

    print("\n===== MEASUREMENT: P(win | z), by t0 =====")
    for t0 in T0S:
        d = dev.filter(pl.col("t0") == t0)
        z = d["z"].to_numpy(); wn = d["win"].to_numpy()
        line = f"t0={t0:>5}: "
        for lo, hi in ((0.0, 0.05), (0.05, 0.15), (0.15, 0.5), (0.5, 99)):
            m = (np.abs(z) >= lo) & (np.abs(z) < hi)
            line += f"|z| {lo}-{hi}: {wn[m].mean():.1%} (n={m.sum()})  " if m.sum() > 50 else ""
        print(line)

    print("\n===== MEASUREMENT: does the ask already price the tilt? =====")
    d = dev.filter((pl.col("t0") == -0.5) & pl.col("ask").is_not_null())
    for lo, hi in ((0.05, 0.15), (0.15, 0.5), (0.5, 99)):
        m = d.filter((pl.col("z").abs() >= lo) & (pl.col("z").abs() < hi))
        if len(m) > 50:
            print(f"|z| {lo}-{hi}: signal-side ask mean {m['ask'].mean():.4f} "
                  f"(0.50 = unpriced), win {m['win'].mean():.1%}, n={len(m)}")

    print("\n===== TRADE GRID (32 cells, bar: positive AND t>=3.5) =====")
    surv = []
    for t0 in T0S:
        for cap in CAPS:
            for zg in ZG:
                base = dev.filter((pl.col("t0") == t0) & (pl.col("z").abs() >= zg)
                                  & pl.col("ask").is_not_null() & (pl.col("ask") <= cap))
                for ex in ("pnl_bail", "pnl_hold"):
                    v = base[ex].cast(pl.Float64).drop_nulls().to_numpy()
                    if len(v) < 100:
                        continue
                    t = tstat(v)
                    wr = base.filter(pl.col(ex).is_not_null())["win"].mean()
                    tag = f"t0={t0} cap={cap} |z|>={zg} {ex[4:]}"
                    print(f"{tag:<38} n={len(v):>5} wr {wr:.1%} "
                          f"${v.mean():+.4f}/tr t={t:+.1f}")
                    if v.mean() > 0 and t >= 3.5:
                        surv.append(tag)
    print(f"\nSURVIVORS: {len(surv)}")
    for s in surv:
        print("  ", s)
    fr = df.filter(pl.col("date") > "2026-07-01")
    if len(fr):
        v = fr.filter((pl.col("z").abs() >= 0.05) & (pl.col("ask") <= 0.53))
        for ex in ("pnl_bail", "pnl_hold"):
            vv = v[ex].cast(pl.Float64).drop_nulls().to_numpy()
            if len(vv):
                print(f"fresh Jul6-7 (|z|>=.05 cap .53) {ex}: n={len(vv)} "
                      f"${vv.mean():+.3f}/tr total ${vv.sum():+.1f}")
    print("\nNIX_SCALP4 DONE")


if __name__ == "__main__":
    main()
