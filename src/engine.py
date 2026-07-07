"""Phase 3 backtest engine.

Loads per-family matrices: every column of the feature / exec / maker stores
reshaped to 2D arrays [n_windows x n_offsets]. A strategy config is evaluated
as pure numpy over these arrays — one trade max per window.

Execution realism (Hard Rule 3):
  - taker fills = real book-walk average prices as-of decision time + latency
    (results/exec, latencies 250ms/1s/3s), notional-bucketed 50/200/1000/5000
  - maker fills = conservative strict trade-through via max/min_tpx_after
  - date-correct fees from src/fees (per-window rate array)
  - long-down positions priced via the Up-token mirror (1 - px)

Config dict:
  family: "5m" | "15m"
  offset: decision t_offset (must be in features.OFFSETS[family])
  entry:  list of (feature, op, threshold) ANDed;  op in {">", "<"}
  side:   "up" | "down" | "sign:<feature>"  (long-up if feature > 0 else down)
  exit:   ("hold",) | ("taker", exit_offset) | ("maker", delta_cents)
  notional: 50 | 200 | 1000 | 5000
  latency: "l250" | "l1s" | "l3s"
"""
from __future__ import annotations

import glob
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
from features import OFFSETS

TRAIN_END = "2026-03-19"  # configs/split.json


class Matrix:
    def __init__(self, family: str):
        self.family = family
        self.offsets = OFFSETS[family]
        self.off_idx = {o: i for i, o in enumerate(self.offsets)}
        f = pl.concat([pl.read_parquet(p) for p in
                       sorted(glob.glob(f"results/features/{family}/*.parquet"))])
        e = pl.concat([pl.read_parquet(p) for p in
                       sorted(glob.glob(f"results/exec/{family}/*.parquet"))])
        m = pl.concat([pl.read_parquet(p) for p in
                       sorted(glob.glob(f"results/maker/{family}/*.parquet"))])
        df = f.join(e, on=["wts", "t_offset"], how="left") \
              .join(m, on=["wts", "t_offset"], how="left") \
              .sort("wts", "t_offset")
        # keep only windows with a full offset set and a known outcome
        n_off = len(self.offsets)
        counts = df.group_by("wts").len().filter(pl.col("len") == n_off)
        df = df.join(counts.select("wts"), on="wts", how="inner")
        df = df.filter(pl.col("up_won").is_not_nan())
        wts = df["wts"].to_numpy()
        self.uw = np.unique(wts)
        self.n = len(self.uw)
        self.cols: dict[str, np.ndarray] = {}
        for c in df.columns:
            if c in ("wts", "t_offset"):
                continue
            self.cols[c] = df[c].to_numpy().astype(np.float64).reshape(self.n, n_off)
        self.up_won = self.cols["up_won"][:, 0]
        # per-window fee rate and train/val split membership
        import datetime as dt
        dates = np.array([dt.datetime.fromtimestamp(int(w), dt.UTC).strftime("%Y-%m-%d")
                          for w in self.uw])
        udates = sorted(set(dates))
        rate_map = {d: fees.params(d, family)[0] for d in udates}
        self.fee_rate = np.array([rate_map[d] for d in dates])
        self.is_train = dates <= TRAIN_END

    def col(self, name: str, offset: int) -> np.ndarray:
        return self.cols[name][:, self.off_idx[offset]]


def _fee(shares, px, rate):
    return shares * rate * px * (1.0 - px)


def evaluate(M: Matrix, cfg: dict) -> dict:
    off = cfg["offset"]
    N = cfg["notional"]
    lat = cfg.get("latency", "l250")
    # --- entry mask ---
    mask = np.ones(M.n, dtype=bool)
    for feat, op, thr in cfg["entry"]:
        v = M.col(feat, off)
        mask &= (v > thr) if op == ">" else (v < thr)
        mask &= np.isfinite(v)
    # --- side ---
    side = cfg["side"]
    if side == "up":
        dir_up = np.ones(M.n, dtype=bool)
    elif side == "down":
        dir_up = np.zeros(M.n, dtype=bool)
    else:
        sv = M.col(side.split(":", 1)[1], off)
        dir_up = sv > 0
        mask &= np.isfinite(sv) & (sv != 0)
    # --- entry price (token space: up token for longs, down token = mirror) ---
    buy = M.col(f"{lat}_buy_avgpx_{N}", off)
    sell = M.col(f"{lat}_sell_avgpx_{N}", off)
    entry_px = np.where(dir_up, buy, 1.0 - sell)
    mask &= np.isfinite(entry_px) & (entry_px > 0.005) & (entry_px < 0.995)
    if cfg.get("no_exhaust", True):
        ex = np.where(dir_up, M.col(f"buy_exhaust_{N}", off),
                      M.col(f"sell_exhaust_{N}", off))
        mask &= ex < 0.5
    shares = N / np.maximum(entry_px, 1e-9)
    win = np.where(dir_up, M.up_won, 1.0 - M.up_won)
    fee_in = _fee(shares, entry_px, M.fee_rate)
    hold_pnl = shares * win - N - fee_in

    kind = cfg["exit"][0]
    if kind == "hold":
        pnl = hold_pnl
    elif kind == "taker":
        e_off = cfg["exit"][1]
        xs = M.col(f"{lat}_sell_avgpx_{N}", e_off)
        xb = M.col(f"{lat}_buy_avgpx_{N}", e_off)
        exit_px = np.where(dir_up, xs, 1.0 - xb)  # token exit price
        can = np.isfinite(exit_px)
        fee_out = _fee(shares, np.nan_to_num(exit_px, nan=0.5), M.fee_rate)
        taker_pnl = shares * (exit_px - entry_px) - fee_in - fee_out
        pnl = np.where(can, taker_pnl, hold_pnl)
    elif kind == "maker":
        delta = cfg["exit"][1] / 100.0
        L = entry_px + delta  # token-space sell limit
        mx = M.col("max_tpx_after", off)
        mn = M.col("min_tpx_after", off)
        # token trade prices: up = raw tape; down = 1 - tape (mirror)
        filled = np.where(dir_up, mx > L, (1.0 - mn) > L)
        filled &= np.isfinite(np.where(dir_up, mx, mn)) & (L < 0.995)
        maker_pnl = shares * delta - fee_in  # sold at L, maker leg fee-free
        pnl = np.where(filled, maker_pnl, hold_pnl)
    else:
        raise ValueError(kind)

    out = {"config": cfg, "n_total": int(mask.sum())}
    for split, sel in (("train", M.is_train & mask), ("val", (~M.is_train) & mask)):
        p = pnl[sel]
        n = len(p)
        if n == 0:
            out[split] = {"n": 0}
            continue
        mu, sd = float(p.mean()), float(p.std(ddof=1)) if n > 1 else 0.0
        t = mu / (sd / np.sqrt(n)) if sd > 0 else 0.0
        wins, losses = p[p > 0].sum(), -p[p < 0].sum()
        cum = np.cumsum(p)
        dd = float((np.maximum.accumulate(cum) - cum).max()) if n else 0.0
        out[split] = {"n": n, "pnl": round(float(p.sum()), 2),
                      "mean": round(mu, 4), "t": round(float(t), 2),
                      "pf": round(float(wins / losses), 3) if losses > 0 else float("inf"),
                      "wr": round(float((p > 0).mean()), 4),
                      "maxdd": round(dd, 2)}
    return out
