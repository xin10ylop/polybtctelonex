"""NIX4 JOB A — BTC deep probability pass on the committed feature stores.

Pre-registered (reports/nix4_prereg.md). Splits identical to the main study:
TRAIN days <= 2026-03-19, VAL 2026-03-20..2026-05-12 (stores end before the
spent HOLDOUT). Model zoo is selected on TRAIN ONLY via day-blocked purged CV;
the winner walks forward through VAL with weekly refits + trailing-tail
isotonic calibration. Strategy sims (the user's pre-open 51c->55c maker scalp
+ intra-window taker entries) run on top of p-hat with date-correct fees,
bracketed entry fills (conservative $50 book-walk / optimistic top-of-book),
and strict trade-through maker exits.

Also emits the "probability frontier": required accuracy of the scalp
structure vs achieved out-of-sample accuracy at every abstention level.

Usage: nohup .venv/bin/python src/nix4_btc_deep.py > logs/nix4_btc_deep.log 2>&1 &
"""
from __future__ import annotations

import glob
import math
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees

TRAIN_END = "2026-03-19"
VAL_END = "2026-05-12"
PRE_OFF = [-30, -10, -3]
INTRA_OFF = {"5m": [60, 120, 180, 240, 270], "15m": [180, 300, 540, 780, 840]}
TAUS = [0.50, 0.52, 0.55, 0.60, 0.65]
BANDS = [0.47, 0.48, 0.49, 0.50, 0.51, 0.52, 0.53]
TARGETS = [0.03, 0.04, 0.05]
MARGINS = [0.0, 0.01, 0.02, 0.03]
REFIT_EVERY = 7
ISO_TAIL_DAYS = 10

ZOO = ([("logit", {"C": c}) for c in (0.1, 1.0)]
       + [("lgbm", {"num_leaves": nl, "min_child_samples": mc})
          for nl in (15, 31, 63) for mc in (100, 400)])


def load_fam(fam: str) -> pl.DataFrame:
    def load_dir(d):
        parts = []
        for f in sorted(glob.glob(f"results/{d}/{fam}/*.parquet")):
            date = os.path.basename(f)[:10]
            parts.append(pl.read_parquet(f).with_columns(pl.lit(date).alias("date")))
        return pl.concat(parts, how="diagonal") if parts else None

    df = load_dir("features")
    for d in ("exec", "maker", "xtf", "nixflow", "preopen"):
        o = load_dir(d)
        if o is not None:
            df = df.join(o.drop("date"), on=["wts", "t_offset"], how="left")
    rates = {date: fees.params(date, fam)[0] for date in df["date"].unique().to_list()}
    df = df.join(pl.DataFrame({"date": list(rates), "rate": list(rates.values())}),
                 on="date", how="left")
    return df.sort("date", "wts", "t_offset")


def feat_cols(df: pl.DataFrame) -> list[str]:
    drop = {"wts", "t_offset", "up_won", "date", "rate", "max_tpx_after",
            "min_tpx_after"}
    drop |= {c for c in df.columns if c.startswith(("l250_", "l1s_", "l3s_",
                                                    "buy_exhaust", "sell_exhaust"))}
    return [c for c in df.columns
            if c not in drop and df[c].dtype in (pl.Float32, pl.Float64,
                                                 pl.Int64, pl.Int32, pl.Boolean)]


def make_model(kind: str, prm: dict):
    if kind == "logit":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(max_iter=1000, **prm))
    from lightgbm import LGBMClassifier
    return LGBMClassifier(n_estimators=300, learning_rate=0.05, subsample=0.8,
                          colsample_bytree=0.8, verbosity=-1, random_state=7, **prm)


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def cv_select(df: pl.DataFrame, feats: list[str], tag: str) -> tuple[str, dict]:
    """day-blocked 5-fold purged CV on TRAIN; returns winning zoo entry."""
    tr = df.filter(pl.col("date") <= TRAIN_END)
    days = sorted(tr["date"].unique().to_list())
    blocks = np.array_split(np.array(days), 5)
    X = tr.select([pl.col(c).cast(pl.Float64) for c in feats]).to_numpy()
    y = tr["up_won"].to_numpy().astype(int)
    dates = tr["date"].to_numpy()
    best, best_ll = None, np.inf
    for kind, prm in ZOO:
        lls = []
        for b in blocks:
            embargo = set(b)  # +- 1 day purge
            for d in (b[0], b[-1]):
                i = days.index(d)
                for j in (i - 1, i + 1):
                    if 0 <= j < len(days):
                        embargo.add(days[j])
            te_m = np.isin(dates, b)
            tr_m = ~np.isin(dates, list(embargo))
            m = make_model(kind, prm)
            Xtr = X[tr_m]
            fin = ~np.isnan(Xtr).all(axis=1)
            try:
                m.fit(Xtr, y[tr_m])
                p = m.predict_proba(X[te_m])[:, 1]
                lls.append(logloss(y[te_m], p))
            except Exception as e:
                lls.append(np.inf)
        ll = float(np.mean(lls))
        print(f"  CV {tag} {kind} {prm}: logloss {ll:.5f}", flush=True)
        if ll < best_ll:
            best, best_ll = (kind, prm), ll
    print(f"  CV {tag} WINNER: {best} ({best_ll:.5f})", flush=True)
    return best


def wf_predict(df: pl.DataFrame, feats: list[str], kind: str, prm: dict) -> np.ndarray:
    """walk-forward p-hat: TRAIN gets 5-fold day-block OOF; VAL gets weekly
    expanding refits, isotonic fitted on the trailing ISO_TAIL_DAYS of train."""
    from sklearn.isotonic import IsotonicRegression
    X = df.select([pl.col(c).cast(pl.Float64) for c in feats]).to_numpy()
    y = df["up_won"].to_numpy().astype(int)
    dates = df["date"].to_numpy()
    days = sorted(set(dates.tolist()))
    tr_days = [d for d in days if d <= TRAIN_END]
    va_days = [d for d in days if d > TRAIN_END]
    p_out = np.full(len(df), np.nan)
    # TRAIN OOF
    for b in np.array_split(np.array(tr_days), 5):
        te_m = np.isin(dates, b)
        tr_m = np.isin(dates, [d for d in tr_days if d not in set(b)])
        m = make_model(kind, prm)
        m.fit(X[tr_m], y[tr_m])
        p_out[te_m] = m.predict_proba(X[te_m])[:, 1]
    # VAL walk-forward
    for i0 in range(0, len(va_days), REFIT_EVERY):
        chunk = va_days[i0:i0 + REFIT_EVERY]
        hist = tr_days + va_days[:i0]
        fit_days, tail = hist[:-ISO_TAIL_DAYS], hist[-ISO_TAIL_DAYS:]
        m = make_model(kind, prm)
        fit_m = np.isin(dates, fit_days)
        m.fit(X[fit_m], y[fit_m])
        tail_m = np.isin(dates, tail)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
        iso.fit(m.predict_proba(X[tail_m])[:, 1], y[tail_m])
        te_m = np.isin(dates, chunk)
        p_out[te_m] = iso.predict(m.predict_proba(X[te_m])[:, 1])
    return p_out


def scalp_sim(df: pl.DataFrame, fam: str) -> pl.DataFrame:
    """the user's strategy: pre-open entry <= band, maker exit +target,
    hold to expiry if unfilled. Vectorized over all rows; configs aggregate."""
    out = []
    for conv in ("cons", "opt"):
        if conv == "cons":
            up_entry = pl.col("l250_buy_avgpx_50")
            dn_entry = 1 - pl.col("l250_sell_avgpx_50")
        else:
            up_entry = pl.col("pm_ask")
            dn_entry = 1 - pl.col("pm_bid")
        for tau in TAUS:
            side_up = pl.col("p_hat") >= tau
            side_dn = (1 - pl.col("p_hat")) >= tau
            side = pl.when(side_up).then(1).when(side_dn).then(-1).otherwise(0)
            entry = pl.when(side == 1).then(up_entry).when(side == -1) \
                      .then(dn_entry).otherwise(None)
            win = pl.when(side == 1).then(pl.col("up_won")) \
                    .when(side == -1).then(~pl.col("up_won")).otherwise(None)
            mx = pl.when(side == 1).then(pl.col("max_tpx_after")) \
                   .otherwise(1 - pl.col("min_tpx_after"))
            for tgt in TARGETS:
                limit = entry + tgt
                fill_exit = mx >= limit + 0.01
                sh = 5.0 / entry
                fee = sh * pl.col("rate") * entry * (1 - entry)
                pnl = pl.when(fill_exit).then(sh * tgt - fee) \
                        .otherwise(sh * win.cast(pl.Float64) - 5.0 - fee)
                for band in BANDS:
                    ok = (side != 0) & entry.is_finite() & (entry > 0.03) \
                         & (entry <= band) & (limit < 0.99)
                    for off in PRE_OFF:
                        sub = df.filter((pl.col("t_offset") == off) & ok)
                        if sub.is_empty():
                            continue
                        g = sub.select(
                            pnl.alias("pnl"), win.alias("win"),
                            fill_exit.alias("fx"), pl.col("date"), pl.col("split"))
                        for split in ("TRAIN", "VAL"):
                            s = g.filter(pl.col("split") == split)
                            if s.is_empty():
                                continue
                            x = s["pnl"].drop_nulls().to_numpy()
                            if len(x) < 2:
                                continue
                            t = x.mean() / x.std(ddof=1) * math.sqrt(len(x)) \
                                if x.std(ddof=1) > 0 else float("nan")
                            gp = x[x > 0].sum()
                            gl = -x[x < 0].sum()
                            out.append({
                                "fam": fam, "family": "scalp", "conv": conv,
                                "tau": tau, "tgt": tgt, "band": band,
                                "off": off, "split": split, "n": len(x),
                                "mean": float(x.mean()), "t": float(t),
                                "pf": float(gp / gl) if gl > 0 else float("inf"),
                                "wr": float(s["win"].drop_nulls().mean()),
                                "fill_rate": float(s["fx"].drop_nulls().mean()),
                                "total": float(x.sum()),
                            })
    return pl.DataFrame(out)


def taker_sim(df: pl.DataFrame, fam: str) -> pl.DataFrame:
    out = []
    for conv in ("cons", "opt"):
        if conv == "cons":
            up_entry = pl.col("l250_buy_avgpx_50")
            dn_entry = 1 - pl.col("l250_sell_avgpx_50")
        else:
            up_entry = pl.col("pm_ask")
            dn_entry = 1 - pl.col("pm_bid")
        side = pl.when(pl.col("p_hat") >= 0.5).then(1).otherwise(-1)
        p_side = pl.when(side == 1).then(pl.col("p_hat")).otherwise(1 - pl.col("p_hat"))
        entry = pl.when(side == 1).then(up_entry).otherwise(dn_entry)
        win = pl.when(side == 1).then(pl.col("up_won")).otherwise(~pl.col("up_won"))
        sh = 5.0 / entry
        fee = sh * pl.col("rate") * entry * (1 - entry)
        ev = p_side - entry - pl.col("rate") * entry * (1 - entry)
        pnl = sh * win.cast(pl.Float64) - 5.0 - fee
        for mrg in MARGINS:
            ok = entry.is_finite() & (entry > 0.03) & (entry < 0.97) & (ev >= mrg)
            for off in INTRA_OFF[fam]:
                sub = df.filter((pl.col("t_offset") == off) & ok)
                if sub.is_empty():
                    continue
                g = sub.select(pnl.alias("pnl"), win.alias("win"),
                               pl.col("date"), pl.col("split"))
                for split in ("TRAIN", "VAL"):
                    s = g.filter(pl.col("split") == split)
                    x = s["pnl"].drop_nulls().to_numpy()
                    if len(x) < 2:
                        continue
                    t = x.mean() / x.std(ddof=1) * math.sqrt(len(x)) \
                        if x.std(ddof=1) > 0 else float("nan")
                    gp = x[x > 0].sum()
                    gl = -x[x < 0].sum()
                    out.append({"fam": fam, "family": "taker", "conv": conv,
                                "tau": None, "tgt": None, "band": None,
                                "off": off, "split": split, "n": len(x),
                                "mean": float(x.mean()), "t": float(t),
                                "pf": float(gp / gl) if gl > 0 else float("inf"),
                                "wr": float(s["win"].drop_nulls().mean()),
                                "fill_rate": None, "total": float(x.sum()),
                                "margin": mrg})
    return pl.DataFrame(out)


def frontier(df: pl.DataFrame, fam: str, lines: list[str]) -> None:
    """required vs achieved accuracy for the scalp structure, VAL only."""
    va = df.filter((pl.col("split") == "VAL") & (pl.col("t_offset") == -10))
    lines.append(f"\n### Probability frontier — fam {fam} (offset -10s, VAL)")
    # calibration of p_hat
    p = va["p_hat"].to_numpy()
    y = va["up_won"].to_numpy().astype(int)
    m = np.isfinite(p)
    p, y = p[m], y[m]
    acc = ((p > 0.5) == y).mean()
    lines.append(f"p-hat: n={len(p)}, acc={acc:.4f}, "
                 f"deciles pred->realized:")
    qs = np.quantile(p, np.linspace(0, 1, 11))
    for k in range(10):
        mm = (p >= qs[k]) & (p <= qs[k + 1])
        if mm.sum() > 20:
            lines.append(f"  {p[mm].mean():.3f} -> {y[mm].mean():.3f} (n={mm.sum()})")
    # abstention curve
    conf = np.abs(p - 0.5)
    lines.append("abstention: trade top-X% confidence -> directional accuracy")
    for q in (1.0, 0.5, 0.2, 0.1, 0.05):
        thr = np.quantile(conf, 1 - q)
        mm = conf >= thr
        if mm.sum() > 20:
            lines.append(f"  top {q:4.0%}: acc={(((p>0.5)==y)[mm]).mean():.4f} (n={mm.sum()})")
    # empirical required accuracy: blind both sides at band 0.51, tgt 0.04
    for conv, upc, dnc in (("cons", "l250_buy_avgpx_50", "l250_sell_avgpx_50"),
                           ("opt", "pm_ask", "pm_bid")):
        req = []
        for side in (1, -1):
            e = va[upc].to_numpy() if side == 1 else 1 - va[dnc].to_numpy()
            w = y == 1 if side == 1 else y == 0
            mx = va["max_tpx_after"].to_numpy() if side == 1 \
                else 1 - va["min_tpx_after"].to_numpy()
            rate = va["rate"].to_numpy()
            okm = np.isfinite(e) & (e > 0.03) & (e <= 0.51) & np.isfinite(mx)
            sh = 5.0 / e
            fee = sh * rate * e * (1 - e)
            fx = mx >= e + 0.04 + 0.01
            pnl = np.where(fx, sh * 0.04 - fee, sh * w - 5.0 - fee)
            right = pnl[okm & w] if side == 1 else pnl[okm & w]
            wrong = pnl[okm & ~w]
            if len(right) > 20 and len(wrong) > 20:
                r_, w_ = right.mean(), wrong.mean()
                req.append((r_, w_, -w_ / (r_ - w_)))
        if req:
            r_, w_ = np.mean([a for a, _, _ in req]), np.mean([b for _, b, _ in req])
            lines.append(f"[{conv}] scalp@<=51c,+4c: E[pnl|right]={r_:+.3f} "
                         f"E[pnl|wrong]={w_:+.3f} -> required accuracy "
                         f"{-w_/(r_-w_):.1%} vs achieved {acc:.1%}")


def main() -> None:
    os.makedirs("results/nix4", exist_ok=True)
    lines = ["# NIX4 JOB A — BTC deep probability pass"]
    all_res = []
    n_configs = 0
    for fam in ("5m", "15m"):
        print(f"=== {fam}: loading", flush=True)
        df = load_fam(fam)
        df = df.filter(pl.col("date") <= VAL_END)
        df = df.with_columns(
            pl.when(pl.col("date") <= TRAIN_END).then(pl.lit("TRAIN"))
            .otherwise(pl.lit("VAL")).alias("split"))
        feats = feat_cols(df)
        lines.append(f"\n## fam {fam}: {len(df)} rows, {len(feats)} features")
        print(f"{fam}: {len(df)} rows, {len(feats)} feats", flush=True)
        for tag, offs in (("preopen", PRE_OFF), ("intra", INTRA_OFF[fam])):
            sub = df.filter(pl.col("t_offset").is_in(offs))
            kind, prm = cv_select(sub, feats, f"{fam}-{tag}")
            lines.append(f"{tag}: zoo winner {kind} {prm} "
                         f"(selected on TRAIN CV only, M_zoo={len(ZOO)})")
            p = wf_predict(sub, feats, kind, prm)
            sub = sub.with_columns(pl.Series("p_hat", p))
            if tag == "preopen":
                res = scalp_sim(sub, fam)
                frontier(sub, fam, lines)
            else:
                res = taker_sim(sub, fam)
            if not res.is_empty():
                all_res.append(res)
                n_configs += res.filter(pl.col("split") == "VAL").height
        del df
    res = pl.concat(all_res, how="diagonal")
    res.write_parquet("results/nix4/btc_deep_grid.parquet")
    keys = ["fam", "family", "conv", "tau", "tgt", "band", "off"]
    if "margin" in res.columns:
        keys.append("margin")
    m_total = res.select(keys).unique().height
    bar = math.sqrt(2 * math.log(max(m_total, 2)))
    lines.append(f"\n## Judgment: M_A={m_total} configs, deflated bar t>={bar:.2f}")
    va = res.filter((pl.col("split") == "VAL") & (pl.col("n") >= 300))
    tr = res.filter(pl.col("split") == "TRAIN").rename({"t": "t_train", "mean": "mean_train"})
    va = va.join(tr.select(keys + ["t_train", "mean_train"]), on=keys, how="left")
    surv = va.filter((pl.col("t") >= bar) & (pl.col("pf") >= 1.15)
                     & (pl.col("t_train") > 0))
    lines.append(f"VAL configs with n>=300: {va.height}; "
                 f"SURVIVORS at deflated bar: {surv.height}")
    top = va.sort("t", descending=True).head(15)
    lines.append("\nTop-15 by VAL t (regardless of bar):\n```")
    for r in top.iter_rows(named=True):
        lines.append(
            f"{r['fam']} {r['family']} {r['conv']} off={r['off']} tau={r['tau']} "
            f"tgt={r['tgt']} band={r['band']} mrg={r.get('margin')} | "
            f"n={r['n']} ${r['mean']:+.3f}/tr t={r['t']:+.2f} pf={r['pf']:.2f} "
            f"wr={r['wr']:.0%} (train t={r['t_train']})")
    lines.append("```")
    if surv.height:
        lines.append("\nSURVIVORS:\n```")
        for r in surv.iter_rows(named=True):
            lines.append(str(r))
        lines.append("```")
    open("reports/nix4_btc_deep.md", "w").write("\n".join(lines) + "\n")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
