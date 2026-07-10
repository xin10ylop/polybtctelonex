"""NIX4 JOB B — Binance-only multi-coin direction study (pre-registered).

For every UTC 5m/15m window boundary, build features strictly before the
window open from Binance 1s klines (own coin + BTC lead), walk-forward by
day, and measure how predictable the window's direction is: accuracy, AUC,
Brier, calibration, abstention curves. Diagnostic only — no PM prices here.
Per-window p-hat saved to results/nix4/bdir_preds_{fam}.parquet for later
joining against Polymarket books (JOB C).

Fixed hyperparameters (no tuning => no selection bias to deflate).

Usage: nohup .venv/bin/python src/nix4_binance_dir.py > logs/nix4_bdir.log 2>&1 &
Resumable: per-day feature parquets in data/processed/nix4_bdir/.
"""
from __future__ import annotations

import datetime as dt
import io
import os
import sys
import time
import urllib.request
import zipfile

import numpy as np
import polars as pl

SYMS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT",
        "xrp": "XRPUSDT", "bnb": "BNBUSDT", "doge": "DOGEUSDT"}
D0, D1 = dt.date(2026, 4, 1), dt.date(2026, 7, 9)
DATES = [(D0 + dt.timedelta(days=i)).isoformat()
         for i in range((D1 - D0).days + 1)]
FAMS = {"5m": 300, "15m": 900}
KL = ["open_time", "open", "high", "low", "close", "volume", "close_time",
      "qvol", "count", "tb_vol", "tb_qvol", "ignore"]
HORIZONS = [5, 15, 60, 300, 900, 3600]
MIN_TRAIN_DAYS = 21


def klines_rich(sym: str, date: str) -> str | None:
    out = f"data/processed/nix4_bdir/klines/{sym}/{date}.parquet"
    if os.path.exists(out):
        return out
    url = (f"https://data.binance.vision/data/spot/daily/klines/{sym}/1s/"
           f"{sym}-1s-{date}.zip")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
                raw = z.read(z.namelist()[0])
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    else:
        return None
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=KL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ot = pl.col("open_time").cast(pl.Int64)
    # epoch units vary across binance dumps (ms vs us)
    unit = df["open_time"].cast(pl.Int64).max()
    ot_us = ot * 1000 if unit < 2_000_000_000_000 else ot
    (df.select(ot_us.alias("ot_us"),
               pl.col("close").cast(pl.Float64),
               pl.col("volume").cast(pl.Float64),
               pl.col("count").cast(pl.Int64, strict=False).fill_null(0),
               pl.col("tb_vol").cast(pl.Float64))
       .sort("ot_us").write_parquet(out, compression="zstd"))
    return out


def load3(sym: str, date: str):
    """day-1 .. day+1 concatenated (trailing 1h features + next-window target)."""
    d = dt.date.fromisoformat(date)
    parts = []
    for dd in (d - dt.timedelta(days=1), d, d + dt.timedelta(days=1)):
        p = klines_rich(sym, dd.isoformat())
        if p:
            parts.append(pl.read_parquet(p))
    if not parts:
        return None
    return pl.concat(parts).sort("ot_us")


def day_features(coin: str, date: str, btc: pl.DataFrame | None) -> pl.DataFrame | None:
    k = load3(SYMS[coin], date)
    if k is None:
        return None
    ot = k["ot_us"].to_numpy()
    close = k["close"].to_numpy()
    lc = np.log(close)
    vol = k["volume"].to_numpy()
    cnt = k["count"].to_numpy().astype(np.float64)
    tb = k["tb_vol"].to_numpy()
    if btc is not None:
        bot = btc["ot_us"].to_numpy()
        blc = np.log(btc["close"].to_numpy())
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    rows = []
    for fam, dur in FAMS.items():
        for w in range(d0, d0 + 86400, dur):
            t_us = w * 1_000_000
            i = np.searchsorted(ot, t_us, "left") - 1   # last candle CLOSED < w
            if i < 3700:
                continue
            j_end = np.searchsorted(ot, (w + dur) * 1_000_000, "left") - 1
            if j_end <= i or j_end >= len(ot):
                continue
            row = {"coin": coin, "fam": fam, "date": date, "wts": w,
                   "up": bool(lc[j_end] >= lc[i]),
                   "hour": (w % 86400) // 3600, "dow": (w // 86400 + 4) % 7}
            ok = True
            for h in HORIZONS:
                ih = np.searchsorted(ot, (w - h) * 1_000_000, "left") - 1
                if ih < 0:
                    ok = False
                    break
                row[f"r_{h}"] = lc[i] - lc[ih]
            if not ok:
                continue
            for h in (60, 300, 900):
                ih = np.searchsorted(ot, (w - h) * 1_000_000, "left") - 1
                seg = np.diff(lc[ih:i + 1])
                row[f"rv_{h}"] = float(np.std(seg)) if len(seg) > 5 else None
            i60 = np.searchsorted(ot, (w - 60) * 1_000_000, "left") - 1
            i300 = np.searchsorted(ot, (w - 300) * 1_000_000, "left") - 1
            i3600 = np.searchsorted(ot, (w - 3600) * 1_000_000, "left") - 1
            v60 = vol[i60:i].sum()
            v3600 = vol[i3600:i].sum()
            row["vol_z60"] = float(v60 / (v3600 / 60.0 + 1e-12))
            row["ntr_60"] = float(cnt[i60:i].sum())
            row["tbr_60"] = float(tb[i60:i].sum() / (v60 + 1e-12))
            v300 = vol[i300:i].sum()
            row["tbr_300"] = float(tb[i300:i].sum() / (v300 + 1e-12))
            if btc is not None:
                bi = np.searchsorted(bot, t_us, "left") - 1
                ok = bi >= 3700
                if ok:
                    for h in (15, 60, 300, 900):
                        bih = np.searchsorted(bot, (w - h) * 1_000_000, "left") - 1
                        row[f"btc_r_{h}"] = blc[bi] - blc[bih]
                    bseg = np.diff(blc[np.searchsorted(bot, (w - 300) * 1_000_000, "left") - 1: bi + 1])
                    row["btc_rv_300"] = float(np.std(bseg)) if len(bseg) > 5 else None
            rows.append(row)
    return pl.DataFrame(rows) if rows else None


def harvest() -> None:
    os.makedirs("data/processed/nix4_bdir/feat", exist_ok=True)
    for date in DATES:
        out = f"data/processed/nix4_bdir/feat/{date}.parquet"
        if os.path.exists(out):
            continue
        btc = load3(SYMS["btc"], date)
        parts = []
        for coin in SYMS:
            f = day_features(coin, date, btc if coin != "btc" else btc)
            if f is not None:
                parts.append(f)
        if parts:
            pl.concat(parts, how="diagonal").write_parquet(out, compression="zstd")
            print(f"feat {date}: {sum(len(p) for p in parts)} rows", flush=True)
        else:
            pl.DataFrame({"date": [date]}).write_parquet(out)
            print(f"feat {date}: EMPTY", flush=True)


def walk_forward(df: pl.DataFrame, feats: list[str], fam: str) -> pl.DataFrame:
    from lightgbm import LGBMClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    df = df.filter(pl.col("fam") == fam).sort("date", "wts")
    days = sorted(df["date"].unique().to_list())
    coins = sorted(df["coin"].unique().to_list())
    df = df.with_columns(pl.col("coin").cast(pl.Enum(coins)).to_physical()
                         .alias("coin_id"))
    X_all = df.select(feats + ["coin_id"]).to_numpy().astype(np.float64)
    y_all = df["up"].to_numpy().astype(int)
    date_arr = df["date"].to_numpy()
    preds_lgb = np.full(len(df), np.nan)
    preds_log = np.full(len(df), np.nan)
    for di in range(MIN_TRAIN_DAYS, len(days)):
        d = days[di]
        tr = date_arr < d
        te = date_arr == d
        if te.sum() == 0:
            continue
        Xtr, ytr = X_all[tr], y_all[tr]
        fin = np.isfinite(Xtr).all(axis=1)
        Xtr, ytr = Xtr[fin], ytr[fin]
        Xte = X_all[te]
        fin_te = np.isfinite(Xte).all(axis=1)
        lgb = LGBMClassifier(n_estimators=300, learning_rate=0.05,
                             num_leaves=31, min_child_samples=200,
                             subsample=0.8, colsample_bytree=0.8,
                             verbosity=-1, random_state=7)
        lgb.fit(Xtr, ytr)
        p = np.full(te.sum(), np.nan)
        p[fin_te] = lgb.predict_proba(Xte[fin_te])[:, 1]
        preds_lgb[te] = p
        sc = StandardScaler().fit(Xtr)
        lr = LogisticRegression(C=1.0, max_iter=1000)
        lr.fit(sc.transform(Xtr), ytr)
        p2 = np.full(te.sum(), np.nan)
        p2[fin_te] = lr.predict_proba(sc.transform(Xte[fin_te]))[:, 1]
        preds_log[te] = p2
        if di % 10 == 0:
            print(f"  wf {fam} {d} ({di}/{len(days)})", flush=True)
    return df.with_columns(pl.Series("p_lgb", preds_lgb),
                           pl.Series("p_log", preds_log))


def report(out: pl.DataFrame, fam: str, lines: list[str]) -> None:
    from sklearn.metrics import roc_auc_score
    sub = out.filter(pl.col("p_lgb").is_not_null() & pl.col("p_lgb").is_not_nan())
    lines.append(f"\n### fam={fam}  (n={len(sub)}, days>{MIN_TRAIN_DAYS})")
    for model in ("p_lgb", "p_log"):
        lines.append(f"\nmodel {model}:")
        for coin in ["ALL"] + sorted(sub["coin"].unique().to_list()):
            s = sub if coin == "ALL" else sub.filter(pl.col("coin") == coin)
            if len(s) < 50:
                continue
            y = s["up"].to_numpy().astype(int)
            p = s[model].to_numpy()
            acc = float(((p > 0.5) == y).mean())
            auc = float(roc_auc_score(y, p)) if 0 < y.mean() < 1 else float("nan")
            brier = float(np.mean((p - y) ** 2))
            conf = np.abs(p - 0.5)
            q = np.quantile(conf, 0.8)
            top = conf >= q
            acc_top = float(((p[top] > 0.5) == y[top]).mean())
            mean_p_top = float(np.mean(np.maximum(p[top], 1 - p[top])))
            lines.append(
                f"  {coin:4s}: n={len(s):6d} acc={acc:.4f} auc={auc:.4f} "
                f"brier={brier:.4f} | top20% conf: acc={acc_top:.4f} "
                f"(claimed {mean_p_top:.3f})")
        # monthly stability, pooled
        for m in sorted(set(d[:7] for d in sub["date"].to_list())):
            s = sub.filter(pl.col("date").str.starts_with(m))
            y = s["up"].to_numpy().astype(int)
            p = s[model].to_numpy()
            lines.append(f"    {m}: n={len(s):5d} acc={((p>0.5)==y).mean():.4f}")
        # calibration deciles
        y = sub["up"].to_numpy().astype(int)
        p = sub[model].to_numpy()
        lines.append("    calibration (decile: pred -> realized):")
        qs = np.quantile(p, np.linspace(0, 1, 11))
        for k in range(10):
            m_ = (p >= qs[k]) & (p <= qs[k + 1])
            if m_.sum() > 20:
                lines.append(f"      {p[m_].mean():.3f} -> {y[m_].mean():.3f} (n={m_.sum()})")


def main() -> None:
    harvest()
    files = sorted(__import__("glob").glob("data/processed/nix4_bdir/feat/*.parquet"))
    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal")
    df = df.filter(pl.col("wts").is_not_null())
    feats = [c for c in df.columns
             if c.split("_")[0] in ("r", "rv", "btc", "vol", "ntr", "tbr")
             or c in ("hour", "dow")]
    print("features:", feats, flush=True)
    lines = ["# NIX4 JOB B — Binance-only direction study (walk-forward)",
             f"windows: {len(df)}, {DATES[0]}..{DATES[-1]}",
             "breakeven reference: taker at mid 0.51 needs p>=0.5275 (r=0.07)"]
    os.makedirs("results/nix4", exist_ok=True)
    for fam in FAMS:
        out = walk_forward(df, feats, fam)
        out.select("coin", "fam", "date", "wts", "up", "p_lgb", "p_log") \
           .write_parquet(f"results/nix4/bdir_preds_{fam}.parquet",
                          compression="zstd")
        report(out, fam, lines)
    open("reports/nix4_bdir.md", "w").write("\n".join(lines) + "\n")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
