"""Scalp pass 5 (2026-07-11) — RENEW the boundary-print direction signal.

Pass 4 found the only positive edge in four passes: at T0 = boundary-0.5s,
a pure-Binance return over the oracle's ~1s value-lag window ("g") predicts
the window's resolution direction at 53.8% (breakeven 52.76% at 51c) — the
window opens tilted because its reference print lags Binance by ~1s. Its
weakness was (a) n too small (~40 5m dev days, t=1.3) and (b) its P&L was
still trapped in the user's +4c sell-limit, which CAPS a correct directional
bet at +8% when holding a 50c token to resolution pays +100%.

This pass, freed from the 51c/sell-limit rule (user's instruction):
  - extends the FROZEN signal to the 15m family and POOLS (4x the data);
  - stores raw per-trade fields so the analysis can price ANY monetization
    without rebuilding: PURE HOLD to resolution, TP+4c-then-hold, TP+4c-bail;
  - sweeps entry caps {0.53, 0.60, 0.70} — a real directional edge can pay
    above 51c.
Signal is IDENTICAL to pass 4 (not re-mined). sigma scales per family by
sqrt(duration). Dev era 2026-04-02..05-12; fresh days >=2026-07-06 reported
apart, never pooled into dev. Bar: mean>0 AND t>=3.0.

Output: results/nix_scalp5_rows.parquet + stdout report.
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

FAMS = (("5m", 300), ("15m", 900))
T0S = (-1.0, -0.5)
LAT = 250_000
BLAT = 150_000
LOOK_US = 1_000_000
TP = 0.04
BAIL = 10
STAKE = 10.0
DEV_LO, DEV_HI = "2026-04-02", "2026-05-12"


def day_rows(family: str, dur: int, date: str) -> list[dict]:
    clp = f"data/processed/daily/crypto_prices/{date}.parquet"
    if not os.path.exists(clp):
        return []
    try:
        tr = (loader.load_daily(family, "trades", [date]).collect()
              .sort("wts", "timestamp_us"))
        b = (loader.load_daily(family, "bookcurves", [date]).collect()
             .sort("wts", "timestamp_us"))
        bn = pl.read_parquet(
            f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    if tr.is_empty() or b.is_empty():
        return []
    cl = pl.read_parquet(clp).sort("timestamp_us")
    cts_loc = cl["local_timestamp_us"].to_numpy()
    cpx = cl["price"].to_numpy().astype(np.float64)
    loc_order = np.argsort(cts_loc, kind="stable")
    cts_loc_s, cpx_loc_s = cts_loc[loc_order], cpx[loc_order]

    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(family, d0, d0 + 86400)
    tw = tr["wts"].to_numpy(); tts = tr["timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy(); bts = b["timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    bt = bn["ts_us"].to_numpy()
    bpx = bn["price"].to_numpy().astype(np.float64)
    blog = np.log(bpx)
    rate = fees.params(date, family)[0]
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        B = w_ * 1_000_000
        tlo, thi = np.searchsorted(tw, w_, "left"), np.searchsorted(tw, w_, "right")
        blo, bhi = np.searchsorted(bw, w_, "left"), np.searchsorted(bw, w_, "right")
        if bhi <= blo:
            continue
        seg_t, seg_p = tts[tlo:thi], tpx[tlo:thi]
        sb_t = bts[blo:bhi]

        def tob(T):
            k = int(np.searchsorted(sb_t, T, "right")) - 1
            return (bid0[blo + k], ask0[blo + k]) if k >= 0 else (np.nan, np.nan)

        g0 = B - 5_000_000 - np.arange(300, -1, -1) * 1_000_000
        gi = np.searchsorted(bt, g0, "right") - 1
        gp = np.where(gi >= 0, blog[np.maximum(gi, 0)], np.nan)
        sig = float(np.nanstd(np.diff(gp))) * math.sqrt(float(dur)) * 1e4
        if not (np.isfinite(sig) and sig > 0):
            continue
        for t0 in T0S:
            T0 = B + int(t0 * 1_000_000)
            ka = int(np.searchsorted(cts_loc_s, T0, "right")) - 1
            kbn = int(np.searchsorted(bt, T0 - BLAT, "right")) - 1
            kb1 = int(np.searchsorted(bt, T0 - BLAT - LOOK_US, "right")) - 1
            if ka < 0 or kbn < 0 or kb1 < 0:
                continue
            g = math.log(bpx[kbn] / bpx[kb1]) * 1e4
            z = g / sig
            side = "up" if g > 0 else "down"
            bq, aq = tob(T0 + LAT)
            ask = aq if side == "up" else (1 - bq if np.isfinite(bq) else np.nan)
            win = int((side == "up") == up_won)
            tau_s = None
            bid_bail = None
            if np.isfinite(ask):
                tok = seg_p if side == "up" else 1.0 - seg_p
                ifill = np.searchsorted(seg_t, T0 + LAT, "right")
                hits = np.nonzero(tok[ifill:] > ask + TP)[0]
                if len(hits):
                    tau_s = round((int(seg_t[ifill + hits[0]]) - B) / 1e6, 2)
                bq2, aq2 = tob(B + BAIL * 1_000_000 + LAT)
                xb = bq2 if side == "up" else (1 - aq2 if np.isfinite(aq2) else np.nan)
                bid_bail = round(float(xb), 4) if np.isfinite(xb) else None
            rows.append({
                "date": date, "family": family, "wts": int(w_), "t0": t0,
                "g_bp": round(g, 3), "z": round(z, 4), "sig": round(sig, 2),
                "anchor_age_s": round((T0 - cts_loc_s[ka]) / 1e6, 2),
                "side": side, "win": win, "rate": rate,
                "ask": round(float(ask), 4) if np.isfinite(ask) else None,
                "tau_s": tau_s, "bid_bail": bid_bail})
    return rows


def build() -> pl.DataFrame:
    out = "results/nix_scalp5_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    all_rows = []
    for family, dur in FAMS:
        avail = [d for d in loader.available_dates(family, "trades")
                 if (DEV_LO <= d <= DEV_HI) or d >= "2026-07-06"]
        for date in avail:
            all_rows += day_rows(family, dur, date)
        print(f"{family}: {len(avail)} days scanned", flush=True)
    df = pl.DataFrame(all_rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


# ---- monetizations priced from raw fields (per $10 stake) ----
def price(df: pl.DataFrame, mode: str, cap: float) -> np.ndarray:
    ask = df["ask"].to_numpy().astype(np.float64)
    win = df["win"].to_numpy().astype(np.float64)
    rate = df["rate"].to_numpy().astype(np.float64)
    tau = df["tau_s"].to_numpy().astype(np.float64)
    bail = df["bid_bail"].to_numpy().astype(np.float64)
    ok = np.isfinite(ask) & (ask <= cap)
    sh = np.where(ok, STAKE / np.where(ok, ask, 1.0), np.nan)
    fee_in = rate * ask * (1 - ask) * sh
    if mode == "hold_pure":
        out = sh * win - STAKE - fee_in
    elif mode == "tp4_hold":
        hit = np.isfinite(tau)
        out = np.where(hit, sh * TP - fee_in, sh * win - STAKE - fee_in)
    elif mode == "tp4_bail":
        hit = np.isfinite(tau) & (tau <= BAIL)
        exit_pnl = sh * (bail - ask) - fee_in - rate * bail * (1 - bail) * sh
        out = np.where(hit, sh * TP - fee_in, exit_pnl)
    else:
        raise ValueError(mode)
    return np.where(ok, out, np.nan)


def tstat(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 2 else float("nan")


def cell(df, label, mode, cap, hits):
    v = price(df, mode, cap)
    m = np.isfinite(v)
    if m.sum() < 100:
        return
    t = tstat(v[m])
    wr = df.filter(pl.Series(m))["win"].mean()
    print(f"  {label:<40} n={m.sum():>5} wr {wr:5.1%} ${np.nanmean(v[m]):+.4f}/tr t={t:+.2f}")
    if np.nanmean(v[m]) > 0 and t >= 3.0:
        hits.append(label)


def report(df: pl.DataFrame, tag: str) -> list[str]:
    hits: list[str] = []
    print(f"\n########## {tag} ##########")
    d = df.filter((pl.col("t0") == -0.5) & pl.col("ask").is_not_null())
    print("ask vs |z| (0.50 = tilt unpriced by the book):")
    for lo, hi in ((0.0, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, 99)):
        s = d.filter((pl.col("z").abs() >= lo) & (pl.col("z").abs() < hi))
        if len(s) > 50:
            print(f"    |z| {lo:.2f}-{hi:<5} n={len(s):>5} ask~{s['ask'].mean():.3f} "
                  f"win {s['win'].mean():5.1%}")
    for t0 in T0S:
        for zg in (0.05, 0.15, 0.30):
            base = df.filter((pl.col("t0") == t0) & (pl.col("z").abs() >= zg))
            for mode in ("hold_pure", "tp4_hold", "tp4_bail"):
                for cap in (0.53, 0.60, 0.70):
                    if mode != "hold_pure" and cap != 0.53:
                        continue
                    cell(base, f"t0={t0} |z|>={zg} {mode} cap{cap}", mode, cap, hits)
    return hits


def main() -> None:
    df = build()
    dev = df.filter(pl.col("date") <= DEV_HI)
    fresh = df.filter(pl.col("date") >= "2026-07-06")
    print(f"\nrows {len(df)}: dev {len(dev)} ({dev['date'].n_unique()}d), "
          f"fresh {len(fresh)} ({fresh['date'].n_unique()}d)")
    for fam in ("5m", "15m"):
        s = dev.filter(pl.col("family") == fam)
        print(f"  dev {fam}: {len(s)} rows, {s['date'].n_unique()} days")

    hits = []
    hits += report(dev.filter(pl.col("family") == "5m"), "DEV 5m")
    hits += report(dev.filter(pl.col("family") == "15m"), "DEV 15m")
    hits += report(dev, "DEV POOLED 5m+15m")
    print(f"\n===== SURVIVORS at bar (mean>0 AND t>=3.0): {len(hits)} =====")
    for h in hits:
        print("  ", h)

    if len(fresh):
        print("\n===== FRESH DAYS (no bar; honest numbers) =====")
        for cap in (0.53, 0.60):
            for mode in ("hold_pure", "tp4_hold"):
                v = price(fresh.filter(pl.col("z").abs() >= 0.05), mode, cap)
                m = np.isfinite(v)
                if m.sum():
                    print(f"  fresh {mode} |z|>=.05 cap{cap}: n={m.sum()} "
                          f"${np.nanmean(v[m]):+.3f}/tr total ${np.nansum(v[m]):+.1f}")
    print("\nNIX_SCALP5 DONE")


if __name__ == "__main__":
    main()
