"""Maximal direction/path-prediction pass for the pre-open scalp (2026-07-11).

The user's demand: find WHICH SIDE to buy (and which windows to skip) using
everything at once — order book, taker flow, the concurrent 15m market, the
still-resolving prior window, Binance momentum & volatility, time of day.

Two prediction targets, walk-forward LightGBM (expanding 5-fold by date,
nothing in-fold ever seen in training):
  A) DIRECTION: P(window closes Up) at open-10s. Trade the argmax side's
     scalp only when confidence exceeds a threshold. Breakeven needs ~53%
     realized accuracy on traded windows.
  B) TP-HIT (new target, path property): P(the +4c limit fills before the
     stop). Breakeven for the 10s-stop shape: 77.8% TP rate; for hold: 92.8%.

Features per window at t=-10s (all strictly pre-open, availability-safe):
  book/flow: q_imb, depth_imb, flow_imb_{10,30,60}s, flow_net_30s,
             flow_open_imb, nprints_30s, big_imb_30s        (results/nixflow)
  15m market: xtf15_mid, xtf15_vel60, xtf15_t_rem           (results/xtf)
  prior windows: prior_live_mid, prior2_up                  (results/preopen)
  binance: bret_60s, bret_300s, vol_300s (1s-grid)          (aggTrades)
  clock: hour (UTC), day-of-week

Also: stratified expectancy tables (hour/vol/prior/15m-agreement) and a
compounding simulation ($5 doubling ladder, max 4 rungs, reset on loss) on
the best OOS slice. Output: stdout report + results/nix_scalp_ml.parquet.
"""
from __future__ import annotations

import datetime as dt
import glob
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")

FEATS = ["q_imb", "depth_imb", "flow_imb_10s", "flow_imb_30s", "flow_imb_60s",
         "flow_net_30s", "flow_open_imb", "nprints_30s", "big_imb_30s",
         "xtf15_mid", "xtf15_vel60", "xtf15_t_rem", "prior_live_mid",
         "prior2_up", "bret_60s", "bret_300s", "vol_300s", "hour", "dow"]


def binance_cols(dates: list[str]) -> pl.DataFrame:
    rows = []
    for date in dates:
        try:
            bn = pl.read_parquet(f"data/processed/binance/aggTrades/{date}.parquet").sort("ts_us")
        except FileNotFoundError:
            continue
        bt = bn["ts_us"].to_numpy()
        blog = np.log(bn["price"].to_numpy().astype(np.float64))
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        secs = (d0 + np.arange(86401)) * 1_000_000
        idx = np.searchsorted(bt, secs, "right") - 1
        lp = np.where(idx >= 0, blog[np.maximum(idx, 0)], np.nan)
        for w in range(d0, d0 + 86400, 300):
            i = w - d0  # second index of open; decision at open-10s
            j = i - 10
            if j - 300 < 0:
                continue
            seg = lp[j - 300:j + 1]
            r = np.diff(seg)
            rows.append({"wts": w, "bret_60s": float(lp[j] - lp[j - 60]),
                         "bret_300s": float(lp[j] - lp[j - 300]),
                         "vol_300s": float(np.nanstd(r))})
    return pl.DataFrame(rows)


def main() -> None:
    sc = pl.read_parquet("results/nix_scalp.parquet")
    sc = sc.filter(pl.col("date") <= "2026-05-12")     # mining era only
    dates = sorted(sc["date"].unique().to_list())

    def store(pattern, cols):
        df = pl.concat([pl.read_parquet(p) for p in sorted(glob.glob(pattern))])
        return df.filter(pl.col("t_offset") == -10).select(["wts"] + cols)

    feat = store("results/nixflow/5m/*.parquet",
                 ["q_imb", "depth_imb", "flow_imb_10s", "flow_imb_30s",
                  "flow_imb_60s", "flow_net_30s", "flow_open_imb",
                  "nprints_30s", "big_imb_30s"])
    feat = feat.join(store("results/xtf/5m/*.parquet",
                           ["xtf15_mid", "xtf15_vel60", "xtf15_t_rem"]),
                     on="wts", how="left")
    feat = feat.join(store("results/preopen/5m/*.parquet",
                           ["prior_live_mid", "prior2_up"]), on="wts", how="left")
    feat = feat.join(binance_cols(dates), on="wts", how="left")
    feat = feat.with_columns(
        ((pl.col("wts") % 86400) // 3600).alias("hour"),
        ((pl.col("wts") // 86400 + 4) % 7).alias("dow"))

    # per-window outcome (up_won) from any scalp row
    outc = (sc.group_by("wts").agg(pl.col("date").first(),
            (pl.col("side").first() == "up").alias("_s"),
            pl.col("outcome").first()).select("wts", "date"))
    upw = sc.filter(pl.col("side") == "up").group_by("wts").agg(
        pl.col("date").first(),
        ((pl.col("outcome") == "hold") | True).first())  # placeholder
    # reconstruct up_won: use hold rows (pnl>0 iff side won) — safer: from stop=-1 rows
    h = sc.filter(pl.col("stop") == -1).with_columns(
        pl.when(pl.col("outcome") == "hold")
          .then(pl.col("pnl") > 0)
          .otherwise(None).alias("side_won"))
    # windows where hold row exists and outcome=hold give side_won; tp rows don't.
    # simpler ground truth: majority — derive from tp/hold pnl signs per side
    gt = (h.filter(pl.col("side_won").is_not_null())
            .with_columns(pl.when(pl.col("side") == "up")
                          .then(pl.col("side_won"))
                          .otherwise(~pl.col("side_won")).alias("up_won"))
            .group_by("wts").agg(pl.col("up_won").first(), pl.col("date").first()))

    import lightgbm as lgb

    # ---------- A) DIRECTION ----------
    dset = gt.join(feat, on="wts", how="inner").sort("wts").drop_nulls(subset=["up_won"])
    X = dset.select(FEATS).to_numpy().astype(np.float64)
    y = dset["up_won"].to_numpy().astype(int)
    ds = dset["date"].to_numpy()
    folds = np.array_split(np.array(dates), 6)
    proba = np.full(len(y), np.nan)
    for k in range(1, 6):
        tr_dates = set(np.concatenate(folds[:k]))
        te_dates = set(folds[k])
        tr = np.isin(ds, list(tr_dates))
        te = np.isin(ds, list(te_dates))
        if tr.sum() < 500 or te.sum() == 0:
            continue
        m = lgb.LGBMClassifier(n_estimators=300, num_leaves=31, learning_rate=0.05,
                               min_child_samples=50, verbose=-1)
        m.fit(X[tr], y[tr])
        proba[te] = m.predict_proba(X[te])[:, 1]
    ok = np.isfinite(proba)
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(y[ok], proba[ok]) if ok.sum() else float("nan")
    print(f"A) DIRECTION walk-forward OOS: n={ok.sum()}, AUC={auc:.4f}")
    for thr in (0.52, 0.55, 0.60):
        sel = ok & (np.abs(proba - 0.5) >= (thr - 0.5))
        if sel.sum() == 0:
            print(f"   conf>={thr}: no windows"); continue
        pred = proba[sel] > 0.5
        acc = (pred == y[sel].astype(bool)).mean()
        print(f"   conf>={thr}: windows {sel.sum()}, direction accuracy {acc:.1%} "
              f"(breakeven ~53%)")

    # ---------- B) TP-HIT (10s stop, taker51 t-10) ----------
    rows = sc.filter((pl.col("entry") == "taker51") & (pl.col("t0") == -10)
                     & (pl.col("stop") == 10))
    rows = rows.join(feat, on="wts", how="inner").sort("wts")
    Xb = np.column_stack([rows.select(FEATS).to_numpy().astype(np.float64),
                          (rows["side"] == "up").to_numpy().astype(float)])
    yb = (rows["outcome"] == "tp").to_numpy().astype(int)
    pb = rows["pnl"].to_numpy()
    db = rows["date"].to_numpy()
    prob_b = np.full(len(yb), np.nan)
    for k in range(1, 6):
        tr = np.isin(db, list(set(np.concatenate(folds[:k]))))
        te = np.isin(db, list(set(folds[k])))
        if tr.sum() < 500 or te.sum() == 0:
            continue
        m = lgb.LGBMClassifier(n_estimators=300, num_leaves=31, learning_rate=0.05,
                               min_child_samples=50, verbose=-1)
        m.fit(Xb[tr], yb[tr])
        prob_b[te] = m.predict_proba(Xb[te])[:, 1]
    okb = np.isfinite(prob_b)
    aucb = roc_auc_score(yb[okb], prob_b[okb]) if okb.sum() else float("nan")
    print(f"\nB) TP-HIT (stop10) walk-forward OOS: n={okb.sum()}, AUC={aucb:.4f}, "
          f"base TP rate {yb[okb].mean():.1%} (breakeven 77.8%)")
    qs = np.nanquantile(prob_b[okb], [0.5, 0.8, 0.9, 0.95])
    for q, lbl in zip(qs, ["top50%", "top20%", "top10%", "top5%"]):
        sel = okb & (prob_b >= q)
        print(f"   {lbl}: n={sel.sum()}, realized TP {yb[sel].mean():.1%}, "
              f"mean pnl ${pb[sel].mean():+.3f}, total ${pb[sel].sum():+.0f}")

    # ---------- stratified expectancy (transparency) ----------
    print("\nSTRATA (taker51 t-10 stop10, mean pnl $/trade):")
    j = rows
    for col, cuts in (("hour", [0, 6, 12, 18, 24]), ("vol_300s", None),
                      ("prior_live_mid", None), ("xtf15_mid", None)):
        if cuts:
            lab = j.with_columns(pl.col(col).cut(cuts[1:-1]).alias("b"))
        else:
            v = j[col].drop_nulls()
            if len(v) == 0:
                continue
            qq = [v.quantile(x) for x in (0.25, 0.5, 0.75)]
            lab = j.with_columns(pl.col(col).cut(qq).alias("b"))
        t = lab.group_by("b").agg(pl.len().alias("n"),
                                  pl.col("pnl").mean().round(3).alias("mean$"))
        print(f"  {col}: ", t.sort("b").to_dicts())

    # ---------- compounding ----------
    print("\nCOMPOUNDING ($5 base, double after win, max 4 rungs, reset on loss)")
    seq = rows.sort(["date", "wts"])["pnl"].to_numpy() / 10.0  # per-$1 stake
    for label, edge in (("measured edge", 0.0), ("+3c hypothetical edge", 0.003)):
        bank, stake_mult, rung = 100.0, 1.0, 0
        base = 5.0
        for r in seq:
            pnl = (r + edge) * base * stake_mult
            bank += pnl
            if pnl > 0 and rung < 4:
                stake_mult *= 2; rung += 1
            else:
                stake_mult, rung = 1.0, 0
            if bank <= 0:
                bank = 0.0; break
        print(f"   {label}: $100 -> ${bank:,.0f} after {len(seq)} trades")
    pl.DataFrame({"proba_dir": proba[ok]}).write_parquet("results/nix_scalp_ml.parquet")
    print("\nNIX_SCALP_ML DONE")


if __name__ == "__main__":
    main()
