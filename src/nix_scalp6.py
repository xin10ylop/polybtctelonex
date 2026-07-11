"""Scalp pass 6 (2026-07-11) — boundary signal on the FULL 15m history + a
walk-forward win-rate model (user chose Option B, and noted 15m has lots of
data — correctly: the signal is pure-Binance, so the crypto_prices gate that
capped pass 5 at 41 days was unnecessary).

Unlock: 15m tick+book data runs Oct 11 2025 .. May 12 2026 = 214 dev days
(5.2x pass 5). Holdout-safe: loader.available_dates excludes holdout and the
sealed May13-Jul5 reserve returns empty; we further cap dev at <=2026-05-12.
crypto_prices is now OPTIONAL (used only for the anchor_age diagnostic).

FROZEN signal (identical to pass 4/5): g = ln(Bin(T0-150ms)/Bin(T0-150ms-1s))
in bp; sig = 1s-grid Binance vol over prior 300s * sqrt(900); z = g/sig;
side = sign(g). T0 = boundary-0.5s (winner) and -1.0s (placebo control).
Monetization = pure directional hold to resolution. Fees always on
(fees.params(date,"15m"): 0 pre-Jan5, 0.0624, then 0.072).

Two questions:
  Q1 does the edge hold across 7 months (win rate is fee-free signal quality)
     and does 5x n resolve significance (bar t>=3)?
  Q2 (Option B) can a walk-forward LGBM on book/flow features lift win rate
     above the frozen-signal baseline, out-of-sample (expanding month folds)?

Output: results/nix_scalp6_rows.parquet + stdout report.
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

FAM, DUR = "15m", 900
T0S = (-1.0, -0.5)
LAT = 250_000
BLAT = 150_000
LOOK_US = 1_000_000
STAKE = 10.0
DEV_HI = "2026-05-12"

FEATS = ["absz", "g_bp", "sig", "q_imb", "spread", "mid", "ask",
         "bflow_5s", "bflow_30s", "bret_1s", "bret_5s", "bntr_5s",
         "hour", "dow"]


def day_rows(date: str) -> list[dict]:
    try:
        tr = (loader.load_daily(FAM, "trades", [date]).collect()
              .sort("wts", "timestamp_us"))
        b = (loader.load_daily(FAM, "bookcurves", [date]).collect()
             .sort("wts", "timestamp_us"))
        bn = pl.read_parquet(
            f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    if tr.is_empty() or b.is_empty():
        return []
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(FAM, d0, d0 + 86400)
    tw = tr["wts"].to_numpy(); tts = tr["timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy(); bts = b["timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    bsz = b["bid_s0"].to_numpy().astype(np.float64)
    asz = b["ask_s0"].to_numpy().astype(np.float64)
    bt = bn["ts_us"].to_numpy()
    bpx = bn["price"].to_numpy().astype(np.float64)
    blog = np.log(bpx)
    bq_ = bn["qty"].to_numpy().astype(np.float64)
    bsgn = np.where(bn["is_buyer_maker"].to_numpy(), -1.0, 1.0)
    cnet = np.concatenate([[0.0], np.cumsum(bsgn * bq_)])
    cgrs = np.concatenate([[0.0], np.cumsum(bq_)])
    rate = fees.params(date, FAM)[0]
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        B = w_ * 1_000_000
        blo, bhi = np.searchsorted(bw, w_, "left"), np.searchsorted(bw, w_, "right")
        if bhi <= blo:
            continue
        sb_t = bts[blo:bhi]

        def tob(T):
            k = int(np.searchsorted(sb_t, T, "right")) - 1
            if k < 0:
                return None
            j = blo + k
            return bid0[j], ask0[j], bsz[j], asz[j]

        g0 = B - 5_000_000 - np.arange(300, -1, -1) * 1_000_000
        gi = np.searchsorted(bt, g0, "right") - 1
        gp = np.where(gi >= 0, blog[np.maximum(gi, 0)], np.nan)
        sig = float(np.nanstd(np.diff(gp))) * math.sqrt(float(DUR)) * 1e4
        if not (np.isfinite(sig) and sig > 0):
            continue
        for t0 in T0S:
            T0 = B + int(t0 * 1_000_000)
            kbn = int(np.searchsorted(bt, T0 - BLAT, "right")) - 1
            kb1 = int(np.searchsorted(bt, T0 - BLAT - LOOK_US, "right")) - 1
            if kbn < 0 or kb1 < 0:
                continue
            g = math.log(bpx[kbn] / bpx[kb1]) * 1e4
            z = g / sig
            side = "up" if g > 0 else "down"
            q = tob(T0 + LAT)
            if q is None:
                continue
            bqp, aqp, bs_, as_ = q
            ask = aqp if side == "up" else (1 - bqp if np.isfinite(bqp) else np.nan)
            if not np.isfinite(ask):
                continue
            win = int((side == "up") == up_won)
            # book features at T0 (signal-side oriented)
            qb = tob(T0)
            if qb is not None:
                bb, aa, bsq, asq = qb
                denom = bsq + asq
                qimb = ((bsq - asq) / denom) if denom > 0 else 0.0
                qimb = qimb if side == "up" else -qimb
                spread = aa - bb
                mid = (aa + bb) / 2.0
                mid = mid if side == "up" else 1.0 - mid
            else:
                qimb = spread = mid = np.nan
            # binance flow features (signal-side signed)
            fsgn = 1.0 if side == "up" else -1.0
            def flow(lb):
                k1 = int(np.searchsorted(bt, T0 - BLAT - lb * 1_000_000, "right")) - 1
                g_ = cgrs[kbn + 1] - cgrs[k1 + 1]
                return fsgn * (cnet[kbn + 1] - cnet[k1 + 1]) / g_ if g_ > 0 else 0.0
            k5 = int(np.searchsorted(bt, T0 - BLAT - 5_000_000, "right")) - 1
            rows.append({
                "date": date, "wts": int(w_), "t0": t0, "mo": date[:7],
                "g_bp": round(g, 3), "absz": round(abs(z), 4), "sig": round(sig, 2),
                "side": side, "win": win, "rate": rate, "ask": round(float(ask), 4),
                "q_imb": round(qimb, 4), "spread": round(float(spread), 4),
                "mid": round(float(mid), 4),
                "bflow_5s": round(flow(5), 4), "bflow_30s": round(flow(30), 4),
                "bret_1s": round(fsgn * g, 3),
                "bret_5s": round(fsgn * (blog[kbn] - blog[k5]) * 1e4, 3) if k5 >= 0 else None,
                "bntr_5s": int(kbn - k5) if k5 >= 0 else None,
                "hour": (w_ % 86400) // 3600, "dow": (w_ // 86400 + 4) % 7})
    return rows


def build() -> pl.DataFrame:
    out = "results/nix_scalp6_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    avail = [d for d in loader.available_dates(FAM, "trades")
             if d <= DEV_HI or d >= "2026-07-06"]
    all_rows = []
    for i, date in enumerate(avail):
        all_rows += day_rows(date)
        if i % 30 == 0:
            print(f"  {date} ({i}/{len(avail)})", flush=True)
    df = pl.DataFrame(all_rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


def pnl_hold(df: pl.DataFrame, cap: float) -> np.ndarray:
    ask = df["ask"].to_numpy().astype(np.float64)
    win = df["win"].to_numpy().astype(np.float64)
    rate = df["rate"].to_numpy().astype(np.float64)
    ok = np.isfinite(ask) & (ask <= cap)
    sh = np.where(ok, STAKE / np.where(ok, ask, 1.0), np.nan)
    return np.where(ok, sh * win - STAKE - rate * ask * (1 - ask) * sh, np.nan)


def tstat(v):
    v = v[np.isfinite(v)]
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 2 else float("nan")


def main() -> None:
    df = build()
    dev = df.filter((pl.col("date") <= DEV_HI) & (pl.col("t0") == -0.5))
    fresh = df.filter((pl.col("date") >= "2026-07-06") & (pl.col("t0") == -0.5))
    print(f"\nrows total {len(df)}; dev(-0.5) {len(dev)} over {dev['date'].n_unique()} days "
          f"({dev['mo'].n_unique()} months); fresh {len(fresh)}")

    print("\n===== Q1a WIN RATE by month (fee-free signal quality, |z|>=0.05) =====")
    print("breakeven direction wr at ~0.50 entry (hold) ~= 51.8%")
    g = dev.filter(pl.col("absz") >= 0.05)
    t = (g.group_by("mo").agg(pl.len().alias("n"), pl.col("win").mean().round(4).alias("wr"),
                              pl.col("ask").mean().round(3).alias("ask"))
          .sort("mo"))
    for r in t.iter_rows(named=True):
        print(f"  {r['mo']}: n={r['n']:>4} wr {r['wr']:.1%} ask~{r['ask']}")

    print("\n===== Q1b POOLED significance, hold_pure (does 5x n clear t>=3?) =====")
    for zg in (0.05, 0.15, 0.30):
        base = dev.filter(pl.col("absz") >= zg)
        for cap in (0.53, 0.60, 0.70):
            v = pnl_hold(base, cap); m = np.isfinite(v)
            if m.sum() < 100:
                continue
            wr = base.filter(pl.Series(m))["win"].mean()
            star = "  <-- SURVIVOR" if np.nanmean(v[m]) > 0 and tstat(v[m]) >= 3.0 else ""
            print(f"  |z|>={zg} cap{cap}: n={m.sum():>5} wr {wr:.1%} "
                  f"${np.nanmean(v[m]):+.4f}/tr t={tstat(v[m]):+.2f}{star}")

    print("\n===== placebo: t0=-1.0 should be ~flat/negative (mechanism check) =====")
    pl_ = df.filter((pl.col("date") <= DEV_HI) & (pl.col("t0") == -1.0) & (pl.col("absz") >= 0.05))
    v = pnl_hold(pl_, 0.60); m = np.isfinite(v)
    print(f"  t0=-1.0 |z|>=.05 cap0.60: n={m.sum()} wr {pl_.filter(pl.Series(m))['win'].mean():.1%} "
          f"${np.nanmean(v[m]):+.4f}/tr t={tstat(v[m]):+.2f}")

    # ---------- Q2 Option B: walk-forward win-rate model ----------
    print("\n===== Q2 WALK-FORWARD MODEL (expanding month folds, lift win rate) =====")
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    d = dev.sort("date")
    months = sorted(d["mo"].unique().to_list())
    X = d.select(FEATS).to_numpy().astype(np.float64)
    y = d["win"].to_numpy().astype(int)
    mo = d["mo"].to_numpy()
    proba = np.full(len(y), np.nan)
    for k in range(2, len(months)):
        tr = np.isin(mo, months[:k]); te = mo == months[k]
        if tr.sum() < 800 or te.sum() == 0:
            continue
        m = lgb.LGBMClassifier(n_estimators=400, num_leaves=31, learning_rate=0.03,
                               min_child_samples=80, subsample=0.8, verbose=-1)
        m.fit(X[tr], y[tr])
        proba[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(proba)
    auc = roc_auc_score(y[ok], proba[ok]) if ok.sum() else float("nan")
    print(f"  OOS n={ok.sum()}, AUC={auc:.4f} (0.50=no skill); baseline wr {y[ok].mean():.1%}")
    dm = d.with_columns(pl.Series("p", proba)).filter(pl.col("p").is_not_null())
    for thr in (0.52, 0.54, 0.56, 0.58):
        sel = dm.filter(pl.col("p") >= thr)
        if len(sel) < 100:
            print(f"  p>={thr}: n<100"); continue
        v = pnl_hold(sel, 0.70); mm = np.isfinite(v)
        star = "  <-- SURVIVOR" if np.nanmean(v[mm]) > 0 and tstat(v[mm]) >= 3.0 else ""
        print(f"  model p>={thr}: n={mm.sum():>5} wr {sel['win'].mean():.1%} "
              f"${np.nanmean(v[mm]):+.4f}/tr t={tstat(v[mm]):+.2f}{star}")

    if len(fresh):
        print("\n===== FRESH Jul6-8 (OOS, no bar) =====")
        v = pnl_hold(fresh.filter(pl.col("absz") >= 0.05), 0.60); m = np.isfinite(v)
        if m.sum():
            print(f"  hold_pure |z|>=.05 cap0.60: n={m.sum()} wr "
                  f"{fresh.filter(pl.col('absz')>=0.05).filter(pl.Series(m))['win'].mean():.1%} "
                  f"${np.nanmean(v[m]):+.3f}/tr total ${np.nansum(v[m]):+.1f}")
    print("\nNIX_SCALP6 DONE")


if __name__ == "__main__":
    main()
