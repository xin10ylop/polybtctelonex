"""Scalp pass 2 (2026-07-11) — the user's reframed questions, each scored
against ITS OWN breakeven with real money simulation.

  Q1 "will price jump to entry+4c within x seconds?"  -> touched_x models,
      x in {10,30,60,120,300}; trade = taker51 entry at open-10s, resting
      +4c TP, taker exit at open+x if unfilled (x=300: hold to resolution).
  Q2 "which side will go up?" (resolution direction)  -> win model.
      Breakeven at 51c taker entry + fees: 52.76% accuracy. 55% = +$0.44/tr.
  Q3 "will my side's token reprice up right after open?" -> drift_15s model
      (diagnostic: is the crowd's first repricing predictable at all?).

NEW features this pass (never tried on the scalp before), all strictly <= T
(availability timestamps, Binance shifted 150ms):
  - Binance MICROSTRUCTURE: taker-flow imbalance 1/3/10/30s, trade count,
    short returns 1/3/10s (not just 60/300s momentum), 1s-grid vol.
  - CHAINLINK ANCHOR: last broadcast price vs live Binance (basis_bp),
    anchor staleness, oracle tick rate — nix1's proven-real ingredients.
  - BOOK DYNAMICS: current mid/spread, BBO price-change rate 30s.
Plus the existing stores (flow/book imbalances, 15m market, prior windows).
Side-relative signing: down-side rows flip every directional feature, so one
model learns "signal aligned with my side" on 2x the sample.

Walk-forward LGBM, 6 expanding date folds, folds 1-5 OOS. BTC 5m mining era
(<=2026-05-12; the 90 days with feature stores). Output: stdout report +
results/nix_scalp2.parquet (rows + labels + OOS probabilities).
"""
from __future__ import annotations

import datetime as dt
import glob
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
BLAT = 150_000
TP_DELTA = 0.04
MAX_ENTRY = 0.51
STAKE = 10.0
XS = (10, 30, 60, 120, 300)
MINE_END = "2026-05-12"

DIRECTIONAL = ["flow_imb_10s", "flow_imb_30s", "flow_imb_60s", "flow_net_30s",
               "flow_open_imb", "big_imb_30s", "q_imb", "depth_imb",
               "xtf15_vel60", "b_imb_1s", "b_imb_3s", "b_imb_10s", "b_imb_30s",
               "b_ret_1s", "b_ret_3s", "b_ret_10s", "b_ret_60s", "b_ret_300s",
               "basis_bp"]
MIRROR01 = ["xtf15_mid", "prior_live_mid", "prior2_up", "cur_mid"]
UNSIGNED = ["nprints_30s", "xtf15_t_rem", "b_vol_300s", "b_ntr_10s",
            "anchor_age_s", "cl_rate_60s", "cur_spread", "bbo_chg_30s",
            "hour", "dow", "entry_px"]
FEATS = DIRECTIONAL + MIRROR01 + UNSIGNED


def _last(ts: np.ndarray, t: int) -> int:
    return int(np.searchsorted(ts, t, "right")) - 1


def day_rows(date: str, store: pl.DataFrame) -> list[dict]:
    try:
        tr = (loader.load_daily("5m", "trades", [date]).collect()
              .sort("wts", "timestamp_us"))
        b = (loader.load_daily("5m", "bookcurves", [date]).collect()
             .sort("wts", "timestamp_us"))
        q = (loader.load_daily("5m", "quotes", [date]).collect()
             .sort("wts", "local_timestamp_us"))
        bn = pl.read_parquet(
            f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
    except FileNotFoundError:
        return []
    cl = None
    clp = f"data/processed/daily/crypto_prices/{date}.parquet"
    if os.path.exists(clp):
        cl = pl.read_parquet(clp).sort("local_timestamp_us")
        cts = cl["local_timestamp_us"].to_numpy()
        cpx = cl["price"].to_numpy().astype(np.float64)

    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta("5m", d0, d0 + 86400)
    tw = tr["wts"].to_numpy();  tts = tr["timestamp_us"].to_numpy()
    tpx = tr["price"].to_numpy().astype(np.float64)
    bw = b["wts"].to_numpy();   bts = b["timestamp_us"].to_numpy()
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    bsz = b["bid_s0"].to_numpy().astype(np.float64)
    asz = b["ask_s0"].to_numpy().astype(np.float64)
    qw = q["wts"].to_numpy();   qts = q["local_timestamp_us"].to_numpy()
    qb = q["bid_price"].to_numpy().astype(np.float64)
    qa = q["ask_price"].to_numpy().astype(np.float64)

    bt = bn["ts_us"].to_numpy()
    bpx = bn["price"].to_numpy().astype(np.float64)
    blog = np.log(bpx)
    bqty = bn["qty"].to_numpy().astype(np.float64)
    bsgn = np.where(bn["is_buyer_maker"].to_numpy(), -1.0, 1.0)  # taker side
    cnet = np.concatenate([[0.0], np.cumsum(bsgn * bqty)])
    cgrs = np.concatenate([[0.0], np.cumsum(bqty)])
    rate = fees.params(date, "5m")[0]

    sd = store.filter(pl.col("t_offset") == -10) if store.height else store
    smap = {r["wts"]: r for r in sd.iter_rows(named=True)} if sd.height else {}

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
        qlo, qhi = np.searchsorted(qw, w_, "left"), np.searchsorted(qw, w_, "right")
        if bhi <= blo:
            continue
        seg_t, seg_p = tts[tlo:thi], tpx[tlo:thi]
        sb_t = bts[blo:bhi]

        def tob(T):
            k = _last(sb_t, T)
            if k < 0:
                return None
            j = blo + k
            return bid0[j], ask0[j], bsz[j], asz[j]

        # ---- shared (unsigned/up-frame) features at T0 ----
        f: dict = {}
        Tb = T0 - BLAT
        k2 = _last(bt, Tb)
        if k2 < 0:
            continue
        for lb in (1, 3, 10, 30):
            k1 = _last(bt, Tb - lb * 1_000_000)
            g = cgrs[k2 + 1] - cgrs[k1 + 1]
            f[f"b_imb_{lb}s"] = (cnet[k2 + 1] - cnet[k1 + 1]) / g if g > 0 else 0.0
        for lb in (1, 3, 10, 60, 300):
            k1 = _last(bt, Tb - lb * 1_000_000)
            f[f"b_ret_{lb}s"] = (blog[k2] - blog[k1]) * 1e4 if k1 >= 0 else np.nan
        f["b_ntr_10s"] = float(k2 - _last(bt, Tb - 10_000_000))
        grid = Tb - np.arange(300, -1, -1) * 1_000_000
        gi = np.searchsorted(bt, grid, "right") - 1
        gp = np.where(gi >= 0, blog[np.maximum(gi, 0)], np.nan)
        f["b_vol_300s"] = float(np.nanstd(np.diff(gp))) * 1e4
        if cl is not None:
            kc = _last(cts, T0)
            if kc >= 0:
                f["basis_bp"] = float(np.log(bpx[k2] / cpx[kc]) * 1e4)
                f["anchor_age_s"] = float((T0 - cts[kc]) / 1e6)
                f["cl_rate_60s"] = float(kc - _last(cts, T0 - 60_000_000))
            else:
                f["basis_bp"] = f["anchor_age_s"] = f["cl_rate_60s"] = np.nan
        else:
            f["basis_bp"] = f["anchor_age_s"] = f["cl_rate_60s"] = np.nan
        kq = _last(qts[qlo:qhi], T0)
        if kq >= 0:
            jq = qlo + kq
            f["cur_mid"] = (qb[jq] + qa[jq]) / 2.0
            f["cur_spread"] = qa[jq] - qb[jq]
        else:
            f["cur_mid"] = f["cur_spread"] = np.nan
        f["bbo_chg_30s"] = float(np.searchsorted(qts[qlo:qhi], T0, "right")
                                 - np.searchsorted(qts[qlo:qhi], T0 - 30_000_000, "right"))
        f["hour"] = (w_ % 86400) // 3600
        f["dow"] = (w_ // 86400 + 4) % 7
        st = smap.get(w_, {})
        for c in ("flow_imb_10s", "flow_imb_30s", "flow_imb_60s", "flow_net_30s",
                  "flow_open_imb", "nprints_30s", "big_imb_30s", "q_imb", "depth_imb"):
            f[c] = st.get(c, np.nan)
        f["xtf15_mid"] = st.get("xtf15_mid", np.nan)
        f["xtf15_vel60"] = st.get("xtf15_vel60", np.nan)
        f["xtf15_t_rem"] = st.get("xtf15_t_rem", np.nan)
        f["prior_live_mid"] = st.get("prior_live_mid", np.nan)
        f["prior2_up"] = st.get("prior2_up", np.nan)

        # drift labels (up frame): side-mid change open -> open+x
        q0 = tob(B)
        drifts = {}
        for xd in (5, 15, 30):
            q1 = tob(B + xd * 1_000_000)
            if q0 and q1 and all(np.isfinite([q0[0], q0[1], q1[0], q1[1]])):
                drifts[xd] = ((q1[0] + q1[1]) - (q0[0] + q0[1])) / 2.0
            else:
                drifts[xd] = np.nan

        for side in ("up", "down"):
            sgn = 1.0 if side == "up" else -1.0
            row = {"date": date, "wts": int(w_), "side": side,
                   "win": int((side == "up") == up_won)}
            for c in DIRECTIONAL:
                v = f.get(c, np.nan)
                row[c] = sgn * v if v is not None and np.isfinite(v) else np.nan
            for c in MIRROR01:
                v = f.get(c, np.nan)
                row[c] = (v if side == "up" else 1.0 - v) \
                    if v is not None and np.isfinite(v) else np.nan
            for c in UNSIGNED:
                if c != "entry_px":
                    row[c] = f.get(c, np.nan)
            for xd in (5, 15, 30):
                row[f"drift_{xd}s"] = (int(sgn * drifts[xd] > 0)
                                       if np.isfinite(drifts[xd]) else None)

            # ---- entry (user's shape: taker <= 51c at open-10s) ----
            qf = tob(T0 + LAT)
            feasible = False
            if qf is not None:
                bq, aq, bs_, as_ = qf
                a = aq if side == "up" else (1 - bq if np.isfinite(bq) else np.nan)
                adep = as_ * aq if side == "up" else bs_ * (1 - bq)
                if np.isfinite(a) and a <= MAX_ENTRY and adep >= STAKE:
                    feasible = True
            row["feasible"] = feasible
            row["entry_px"] = round(float(a), 4) if feasible else None
            if feasible:
                sh = STAKE / a
                fee_in = rate * a * (1 - a) * sh
                tp = a + TP_DELTA
                tok = seg_p if side == "up" else 1.0 - seg_p
                ifill = np.searchsorted(seg_t, T0 + LAT, "right")
                hits = np.nonzero(tok[ifill:] > tp)[0]
                tau = int(seg_t[ifill + hits[0]]) if len(hits) else None
                row["tau_s"] = round((tau - B) / 1e6, 2) if tau else None
                for x in XS:
                    cut = B + x * 1_000_000
                    touched = tau is not None and tau <= cut
                    row[f"touch_{x}"] = int(touched)
                    if touched:
                        pnl = sh * TP_DELTA - fee_in
                    elif x == 300:
                        pnl = sh * row["win"] - STAKE - fee_in
                    else:
                        qx = tob(cut + LAT)
                        if qx is None:
                            row[f"pnl_{x}"] = None
                            continue
                        bq, aq, _, _ = qx
                        xb = bq if side == "up" else (1 - aq if np.isfinite(aq) else np.nan)
                        if not np.isfinite(xb):
                            row[f"pnl_{x}"] = None
                            continue
                        pnl = sh * (xb - a) - fee_in - rate * xb * (1 - xb) * sh
                    row[f"pnl_{x}"] = round(float(pnl), 4)
            else:
                row["tau_s"] = None
                for x in XS:
                    row[f"touch_{x}"] = None
                    row[f"pnl_{x}"] = None
            rows.append(row)
    return rows


def build() -> pl.DataFrame:
    out = "results/nix_scalp2_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    dates = [d for d in loader.available_dates("5m", "trades") if d <= MINE_END]
    empty = pl.DataFrame({"wts": [], "t_offset": []})
    all_rows = []
    for date in dates:
        sp = f"results/nixflow/5m/{date}.parquet"
        store = pl.read_parquet(sp) if os.path.exists(sp) else empty
        for extra in (f"results/xtf/5m/{date}.parquet",
                      f"results/preopen/5m/{date}.parquet"):
            if os.path.exists(extra) and store.height:
                store = store.join(pl.read_parquet(extra), on=["wts", "t_offset"]
                                   if "t_offset" in pl.read_parquet_schema(extra)
                                   else ["wts"], how="left")
        all_rows += day_rows(date, store)
        print(date, flush=True)
    df = pl.DataFrame(all_rows, infer_schema_length=None)
    df.write_parquet(out)
    return df


def walk_forward(df: pl.DataFrame, target: str, feats: list[str]) -> np.ndarray:
    import lightgbm as lgb
    d = df.filter(pl.col(target).is_not_null())
    X = d.select(feats).to_numpy().astype(np.float64)
    y = d[target].to_numpy().astype(int)
    ds = d["date"].to_numpy()
    dates = np.array(sorted(set(ds)))
    folds = np.array_split(dates, 6)
    proba = np.full(len(y), np.nan)
    for k in range(1, 6):
        tr = np.isin(ds, np.concatenate(folds[:k]))
        te = np.isin(ds, folds[k])
        if tr.sum() < 500 or te.sum() == 0:
            continue
        m = lgb.LGBMClassifier(n_estimators=300, num_leaves=31,
                               learning_rate=0.05, min_child_samples=50,
                               verbose=-1)
        m.fit(X[tr], y[tr])
        proba[te] = m.predict_proba(X[te])[:, 1]
    return proba, d


def tstat(v: np.ndarray) -> float:
    v = v[np.isfinite(v)]
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))) if len(v) > 2 else float("nan")


def main() -> None:
    from sklearn.metrics import roc_auc_score
    df = build()
    print(f"\nrows {len(df)}, feasible {df['feasible'].sum()}, "
          f"dates {df['date'].n_unique()}")

    print("\n========== Q2 DIRECTION (breakeven 52.76% at 51c) ==========")
    proba, d = walk_forward(df, "win", FEATS)
    ok = np.isfinite(proba)
    y = d["win"].to_numpy().astype(int)
    print(f"OOS n={ok.sum()}, AUC={roc_auc_score(y[ok], proba[ok]):.4f}")
    outd = d.with_columns(pl.Series("p_win", proba))
    for thr in (0.52, 0.55, 0.58, 0.60):
        sel = ok & (proba >= thr)
        if sel.sum() < 30:
            print(f"  p>={thr}: <30 rows"); continue
        acc = y[sel].mean()
        fe = outd.filter(pl.col("p_win") >= thr).filter(pl.col("feasible"))
        ph = fe["pnl_300"].drop_nulls().to_numpy()
        msg = (f", traded n={len(ph)} hold pnl ${ph.mean():+.3f}/tr t={tstat(ph):+.1f}"
               if len(ph) > 30 else "")
        print(f"  p>={thr}: n={sel.sum()}, realized wr {acc:.1%}{msg}")

    print("\n========== Q1 TOUCH +4c BY x SECONDS (feasible taker51 rows) ==========")
    fe = df.filter(pl.col("feasible"))
    for x in XS:
        proba, d = walk_forward(fe, f"touch_{x}", FEATS)
        ok = np.isfinite(proba)
        if ok.sum() < 500:
            print(f"x={x}: insufficient"); continue
        y = d[f"touch_{x}"].to_numpy().astype(int)
        pnl = d[f"pnl_{x}"].to_numpy().astype(np.float64)
        auc = roc_auc_score(y[ok], proba[ok])
        base = y[ok].mean()
        line = f"x={x:>3}s: base touch {base:.1%}, AUC {auc:.3f}"
        for qq, lbl in ((0.8, "top20%"), (0.9, "top10%")):
            thr = np.nanquantile(proba[ok], qq)
            sel = ok & (proba >= thr) & np.isfinite(pnl)
            if sel.sum() < 30:
                continue
            line += (f" | {lbl}: touch {y[sel].mean():.1%}, "
                     f"${np.nanmean(pnl[sel]):+.3f}/tr t={tstat(pnl[sel]):+.1f}")
        print(line)

    print("\n========== Q3 EARLY DRIFT (is the first repricing predictable?) ==========")
    for xd in (5, 15, 30):
        proba, d = walk_forward(df, f"drift_{xd}s", FEATS)
        ok = np.isfinite(proba)
        if ok.sum() < 500:
            continue
        y = d[f"drift_{xd}s"].to_numpy().astype(int)
        auc = roc_auc_score(y[ok], proba[ok])
        sel = ok & (np.abs(proba - 0.5) >= 0.05)
        acc = ((proba[sel] > 0.5) == y[sel].astype(bool)).mean() if sel.sum() > 30 else float("nan")
        print(f"drift_{xd}s: base {y[ok].mean():.1%}, AUC {auc:.3f}, "
              f"conf>=.55 slice n={sel.sum()} acc {acc:.1%}")

    # persist OOS direction probabilities with rows for later inspection
    proba, d = walk_forward(df, "win", FEATS)
    d.with_columns(pl.Series("p_win_oos", proba)).write_parquet(
        "results/nix_scalp2.parquet")
    print("\nNIX_SCALP2 DONE")


if __name__ == "__main__":
    main()
