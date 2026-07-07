"""Phase 3 family 9 — ML probability models with purged walk-forward CV.

For each family and feature set: LightGBM + logistic regression predicting
up_won from decision-time features. TRAIN statistics come from out-of-fold
predictions (5 expanding walk-forward folds, 1-day embargo); VAL uses a final
model fit on all TRAIN. Isotonic calibration fitted on OOF only. Decision
rule: taker-buy the side whose calibrated probability exceeds its book-walk
entry price by `margin` (fee-aware margins in the grid).

Output rows appended to results/grid_{family}_ml.parquet (leaderboard schema).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import polars as pl
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

sys.path.insert(0, "src")
from engine import Matrix, _fee
from grid import MINED_FEATURES

OFFS = {"5m": [30, 60, 150, 240], "15m": [60, 300, 660]}
FEATURE_SETS = {
    "pm_only": ["pm_mid", "pm_spread", "book_imb", "odds_vel_1s", "odds_vel_5s",
                "odds_vel_15s", "odds_vel_60s", "pm_vol_sofar", "dist_50",
                "prior_up", "streak"],
    "binance_only": ["bret_1s", "bret_5s", "bret_15s", "bret_60s", "bret_300s",
                     "ofi_10s", "ofi_60s", "intensity_60s", "vwap_dev_60s",
                     "rvol_60s", "rvol_300s"],
    "all": MINED_FEATURES + ["pm_mid", "hour", "dow"],
}
MARGINS = (0.02, 0.04, 0.07)
EMBARGO_S = 86_400


def flatten(M: Matrix, family: str):
    offs = OFFS[family]
    rows = []
    for o in offs:
        i = M.off_idx[o]
        d = {c: M.cols[c][:, i] for c in set(sum(FEATURE_SETS.values(), []))
             if c in M.cols}
        d["t_offset"] = np.full(M.n, o, dtype=np.float64)
        d["wts"] = M.uw.astype(np.float64)
        d["y"] = M.up_won
        d["buy"] = M.cols["l250_buy_avgpx_200"][:, i]
        d["sell"] = M.cols["l250_sell_avgpx_200"][:, i]
        d["is_train"] = M.is_train.astype(np.float64)
        d["fee_rate"] = M.fee_rate
        rows.append(pl.DataFrame(d))
    return pl.concat(rows)


def run_family(family: str) -> None:
    M = Matrix(family)
    df = flatten(M, family)
    df = df.filter(pl.col("buy").is_finite() & pl.col("sell").is_finite())
    out_rows = []
    tr = df.filter(pl.col("is_train") == 1).sort("wts")
    va = df.filter(pl.col("is_train") == 0).sort("wts")
    wts_tr = tr["wts"].to_numpy()
    folds = np.array_split(np.arange(len(tr)), 6)[1:]  # first block train-only

    for fs_name, feats in FEATURE_SETS.items():
        feats = [f for f in feats if f in df.columns] + ["t_offset"]
        Xtr = tr.select(feats).to_numpy()
        ytr = tr["y"].to_numpy()
        Xva = va.select(feats).to_numpy()
        for model_name in ("lgbm", "logit"):
            oof = np.full(len(tr), np.nan)
            for fold in folds:
                t0 = wts_tr[fold[0]] - EMBARGO_S
                fit_idx = np.where(wts_tr < t0)[0]
                if len(fit_idx) < 5000:
                    continue
                m = _fit(model_name, Xtr[fit_idx], ytr[fit_idx])
                oof[fold] = _pred(model_name, m, Xtr[fold])
            ok = np.isfinite(oof)
            if ok.sum() < 10000:
                continue
            iso = IsotonicRegression(out_of_bounds="clip").fit(oof[ok], ytr[ok])
            p_tr = np.full(len(tr), np.nan)
            p_tr[ok] = iso.predict(oof[ok])
            final = _fit(model_name, Xtr, ytr)
            p_va = iso.predict(_pred(model_name, final, Xva))
            for margin in MARGINS:
                stats = {}
                for split, d_, p_ in (("train", tr, p_tr), ("val", va, p_va)):
                    buy = d_["buy"].to_numpy(); sell = d_["sell"].to_numpy()
                    y = d_["y"].to_numpy(); rate = d_["fee_rate"].to_numpy()
                    w_ = d_["wts"].to_numpy()
                    long_m = np.isfinite(p_) & (p_ - buy > margin)
                    short_m = np.isfinite(p_) & ((1 - p_) - (1 - sell) > margin) & ~long_m
                    entry = np.where(long_m, buy, 1 - sell)
                    winv = np.where(long_m, y, 1 - y)
                    mask = long_m | short_m
                    # one trade per window: keep earliest offset
                    order = np.lexsort((d_["t_offset"].to_numpy(), w_))
                    seen = set(); keep = np.zeros(len(w_), dtype=bool)
                    for j in order:
                        if mask[j] and w_[j] not in seen:
                            keep[j] = True; seen.add(w_[j])
                    sel = keep
                    sh = 200.0 / np.maximum(entry, 1e-9)
                    pnl = (sh * winv - 200.0 - _fee(sh, entry, rate))[sel]
                    n = len(pnl)
                    if n == 0:
                        stats[split] = {"n": 0}; continue
                    mu, sd = pnl.mean(), pnl.std(ddof=1) if n > 1 else 0
                    cum = np.cumsum(pnl)
                    stats[split] = {"n": n, "pnl": round(float(pnl.sum()), 2),
                                    "mean": round(float(mu), 4),
                                    "t": round(float(mu / (sd / np.sqrt(n))) if sd > 0 else 0, 2),
                                    "pf": round(float(pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9)), 3),
                                    "wr": round(float((pnl > 0).mean()), 4),
                                    "maxdd": round(float((np.maximum.accumulate(cum) - cum).max()), 2)}
                row = {"idx": len(out_rows), "family": family, "latency": "l250",
                       "tag": f"ml_{model_name}_{fs_name}", "offset": -1,
                       "side": "model", "exit": json.dumps(["hold"]), "notional": 200,
                       "entry": json.dumps([["margin", ">", margin]])}
                for split in ("train", "val"):
                    for k, v in stats[split].items():
                        row[f"{split}_{k}"] = v
                out_rows.append(row)
                print(f"{family} {model_name}/{fs_name} m={margin}: "
                      f"train {stats['train']} | val {stats['val']}", flush=True)
    pl.DataFrame(out_rows, infer_schema_length=None).write_parquet(
        f"results/grid_{family}_ml.parquet")


def _fit(name, X, y):
    if name == "lgbm":
        return lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=31,
                                  subsample=0.8, colsample_bytree=0.8, verbose=-1,
                                  n_jobs=4).fit(np.nan_to_num(X), y)
    sc = StandardScaler().fit(np.nan_to_num(X))
    lr = LogisticRegression(max_iter=500).fit(sc.transform(np.nan_to_num(X)), y)
    return (sc, lr)


def _pred(name, m, X):
    if name == "lgbm":
        return m.predict_proba(np.nan_to_num(X))[:, 1]
    sc, lr = m
    return lr.predict_proba(sc.transform(np.nan_to_num(X)))[:, 1]


if __name__ == "__main__":
    run_family(sys.argv[1])
