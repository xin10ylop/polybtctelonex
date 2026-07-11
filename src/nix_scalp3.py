"""Scalp pass 3 (2026-07-11) — the user's gated-geometry hypothesis.

User's correction: he never lost the full $10 — unfilled sell limits were
market-sold ~10s after open. That changes the breakeven geometry per cell:
  taker51 + TP4 + stop10:   breakeven touch ~78% (tested: dead)
  maker50 (FEE-FREE entry) + stop: breakeven touch ~45-50%  <- NEVER TESTED
  GATED: pass-2 touch models lift touch 40.6% -> 58% in top decile.

Grid: entry {taker<=51c at open-10s, maker bid 50c resting from open-10s}
    x TP {+2,+3,+4,+6}c (limit rests from fill, pre-open touches count)
    x bail-out {5,10,20,30}s (taker sell at bid if TP unfilled)
Each cell gets its own walk-forward LGBM gate (features from pass 2, joined
on wts+side; side-relative signing makes every rule symmetric Up/Down).

HONESTY BAR (pre-declared): 32 cells x 2 slice depths = 64 looks. A cell
only counts as a candidate if its gated slice is positive with |t| >= 3.5
(Bonferroni at 64 looks); anything weaker is reported as noise. Any survivor
is a HYPOTHESIS for fresh-day validation, not a validated strategy.

Output: results/nix_scalp3_rows.parquet + stdout report.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
import loader
import windows as W

T0S = -10
LAT = 250_000
TPS = (0.02, 0.03, 0.04, 0.06)
STOPS = (5, 10, 20, 30)
MAX_ENTRY = 0.51
MAKER_PX = 0.50
STAKE = 10.0
MINE_END = "2026-05-12"


def day_rows(date: str) -> list[dict]:
    try:
        tr = (loader.load_daily("5m", "trades", [date]).collect()
              .sort("wts", "timestamp_us"))
        b = (loader.load_daily("5m", "bookcurves", [date]).collect()
             .sort("wts", "timestamp_us"))
    except FileNotFoundError:
        return []
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0, d0 + 86400)
    tw = tr["wts"].to_numpy(); tts = tr["timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy(); bts = b["timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        T0 = (w_ + T0S) * 1_000_000
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

        for side in ("up", "down"):
            tok = seg_p if side == "up" else 1.0 - seg_p
            row = {"date": date, "wts": int(w_), "side": side,
                   "win": int((side == "up") == up_won)}
            bq, aq = tob(T0 + LAT)
            t_px = aq if side == "up" else (1 - bq if np.isfinite(bq) else np.nan)
            row["t_ok"] = bool(np.isfinite(t_px) and t_px <= MAX_ENTRY)
            row["t_px"] = round(float(t_px), 4) if row["t_ok"] else None
            i0 = np.searchsorted(seg_t, T0, "left")
            iw = np.searchsorted(seg_t, B, "left")
            hit = np.nonzero(tok[i0:iw] < MAKER_PX)[0]
            row["m_ok"] = bool(len(hit))
            m_fill_t = int(seg_t[i0 + hit[0]]) if row["m_ok"] else None
            for tag, ok, px, ft in (("t", row["t_ok"], t_px, T0 + LAT),
                                    ("m", row["m_ok"], MAKER_PX, m_fill_t)):
                for d in TPS:
                    key = f"tau_{tag}_{int(d*100)}"
                    if not ok:
                        row[key] = None
                        continue
                    ifill = np.searchsorted(seg_t, ft, "right")
                    hits = np.nonzero(tok[ifill:] > px + d)[0]
                    row[key] = (round((int(seg_t[ifill + hits[0]]) - B) / 1e6, 2)
                                if len(hits) else None)
            for s in STOPS:
                bq, aq = tob(B + s * 1_000_000 + LAT)
                xb = bq if side == "up" else (1 - aq if np.isfinite(aq) else np.nan)
                row[f"bid_{s}"] = round(float(xb), 4) if np.isfinite(xb) else None
            rows.append(row)
    return rows


def build() -> pl.DataFrame:
    out = "results/nix_scalp3_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    all_rows = []
    for date in [d for d in loader.available_dates("5m", "trades") if d <= MINE_END]:
        all_rows += day_rows(date)
        print(date, flush=True)
    df = pl.DataFrame(all_rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


def main() -> None:
    from sklearn.metrics import roc_auc_score
    df = build()
    feat = pl.read_parquet("results/nix_scalp2_rows.parquet")
    FEATS = [c for c in feat.columns if c not in
             ("date", "wts", "side", "win", "feasible", "entry_px", "tau_s",
              "drift_5s", "drift_15s", "drift_30s")
             and not c.startswith(("touch_", "pnl_"))]
    df = df.join(feat.select(["wts", "side"] + FEATS), on=["wts", "side"], how="left")
    print(f"rows {len(df)}, taker-ok {df['t_ok'].sum()}, maker-ok {df['m_ok'].sum()}, "
          f"features {len(FEATS)}")

    import lightgbm as lgb
    dates = np.array(sorted(df["date"].unique().to_list()))
    folds = np.array_split(dates, 6)
    rate_of = {d: fees.params(d, "5m")[0] for d in dates}

    print(f"\n{'cell':<22}{'n':>6}{'base%':>7}{'AUC':>6} | ungated $/tr t | "
          f"top20% $/tr t touch% | top10% $/tr t touch%")
    survivors = []
    for tag, okc in (("t", "t_ok"), ("m", "m_ok")):
        for d in TPS:
            dc = int(d * 100)
            sub = df.filter(pl.col(okc))
            ds = sub["date"].to_numpy()
            tau = sub[f"tau_{tag}_{dc}"].cast(pl.Float64).to_numpy()
            px = (sub["t_px"].cast(pl.Float64).to_numpy() if tag == "t"
                  else np.full(len(sub), MAKER_PX))
            rt = np.array([rate_of[x] for x in ds])
            sh = STAKE / px
            fee_in = (rt * px * (1 - px) * sh) if tag == "t" else np.zeros(len(sub))
            X = sub.select(FEATS).to_numpy().astype(np.float64)
            for s in STOPS:
                xb = sub[f"bid_{s}"].cast(pl.Float64).to_numpy()
                touched = np.isfinite(tau) & (tau <= s)
                pnl = np.where(touched, sh * d - fee_in,
                               sh * (xb - px) - fee_in - rt * xb * (1 - xb) * sh)
                valid = touched | np.isfinite(xb)
                y = touched.astype(int)
                proba = np.full(len(y), np.nan)
                for k in range(1, 6):
                    trm = np.isin(ds, np.concatenate(folds[:k]))
                    tem = np.isin(ds, folds[k])
                    if trm.sum() < 500 or tem.sum() == 0:
                        continue
                    mdl = lgb.LGBMClassifier(n_estimators=300, num_leaves=31,
                                             learning_rate=0.05,
                                             min_child_samples=50, verbose=-1)
                    mdl.fit(X[trm], y[trm])
                    proba[tem] = mdl.predict_proba(X[tem])[:, 1]
                ok = np.isfinite(proba) & valid
                if ok.sum() < 1000:
                    continue
                auc = roc_auc_score(y[ok], proba[ok]) if 0 < y[ok].mean() < 1 else np.nan
                def stats(m):
                    v = pnl[m]
                    t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 30 else np.nan
                    return v.mean(), t, y[m].mean()
                mu0, t0, _ = stats(ok)
                line = (f"{tag}{'51' if tag=='t' else '50'}+{dc}c/stop{s:<3}"
                        f"{ok.sum():>7}{y[ok].mean()*100:>6.1f}%{auc:>6.3f} | "
                        f"${mu0:+.3f} {t0:+5.1f} |")
                for qq in (0.8, 0.9):
                    thr = np.nanquantile(proba[ok], qq)
                    m = ok & (proba >= thr)
                    mu, t, tc = stats(m)
                    line += f" ${mu:+.3f} {t:+5.1f} {tc*100:.0f}% |"
                    if mu > 0 and t >= 3.5:
                        survivors.append((tag, dc, s, qq, mu, t, int(m.sum())))
                print(line)

    print(f"\nSURVIVORS at pre-declared bar (positive, t>=3.5, 64 looks): "
          f"{len(survivors)}")
    for sv in survivors:
        print("  ", sv)
    print("\nNIX_SCALP3 DONE")


if __name__ == "__main__":
    main()
