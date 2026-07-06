"""Phase 1 section 2 — lead-lag: Binance returns vs Chainlink feed vs
Polymarket odds, on a 250ms grid, with month-over-month lag decay.

For each date having the needed sources: build 250ms return series and
cross-correlate at lags -10s..+10s. Positive reported lag means the FIRST
series leads (its past returns correlate with the second's current returns).
Outputs results/phase1/leadlag_daily.parquet (per date) — the report
aggregates monthly. Section 2 pairs:
  binance->chainlink (needs crypto_prices, >=2026-04-02)
  binance->pm_odds  (5m windows, full history)
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader

GRID_US = 250_000
MAX_LAG = 40  # +-40 * 250ms = +-10s
OUT = "results/phase1/leadlag_daily.parquet"


def day_grid(date: str) -> tuple[int, int]:
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp() * 1e6)
    return d0, d0 + 86_400_000_000


def to_grid(ts_us: np.ndarray, val: np.ndarray, date: str) -> np.ndarray:
    """As-of series on the day's 250ms grid; NaN before first observation."""
    d0, d1 = day_grid(date)
    grid = np.arange(d0, d1, GRID_US)
    idx = np.searchsorted(ts_us, grid, side="right") - 1
    out = np.where(idx >= 0, val[np.clip(idx, 0, len(val) - 1)], np.nan)
    return out


def xcorr_returns(a: np.ndarray, b: np.ndarray, max_lag: int) -> tuple[np.ndarray, int]:
    """Cross-correlation of two aligned return series over +-max_lag steps.
    Returns (corr_by_lag, n_valid). corr[k] = corr(a[t-k], b[t]) for lag k."""
    valid = np.isfinite(a) & np.isfinite(b)
    lags = range(-max_lag, max_lag + 1)
    out = np.full(2 * max_lag + 1, np.nan)
    for i, k in enumerate(lags):
        if k >= 0:
            x, y = a[: len(a) - k if k else len(a)], b[k:]
        else:
            x, y = a[-k:], b[: len(b) + k]
        v = np.isfinite(x) & np.isfinite(y)
        if v.sum() < 1000:
            continue
        xs, ys = x[v], y[v]
        sx, sy = xs.std(), ys.std()
        if sx > 0 and sy > 0:
            out[i] = float(((xs - xs.mean()) * (ys - ys.mean())).mean() / (sx * sy))
    return out, int(valid.sum())


def binance_series(date: str) -> np.ndarray | None:
    p = f"data/processed/binance/aggTrades/{date}.parquet"
    if not os.path.exists(p):
        return None
    df = pl.read_parquet(p).sort("ts_us")
    return to_grid(df["ts_us"].to_numpy(), df["price"].to_numpy(), date)


def chainlink_series(date: str) -> np.ndarray | None:
    try:
        df = (loader.load_crypto_prices([date]).select("timestamp_us", "price")
              .collect().sort("timestamp_us"))
    except (FileNotFoundError, loader.HoldoutViolation):
        return None
    return to_grid(df["timestamp_us"].to_numpy(), df["price"].to_numpy(), date)


def pm_odds_series(date: str, family: str = "5m") -> np.ndarray | None:
    """UP mid across consecutive windows on the 250ms grid; NaN outside windows
    and across window boundaries (so returns never span two markets)."""
    try:
        q = (loader.load_daily(family, "quotes", [date])
             .select("wts", "timestamp_us", "bid_price", "ask_price")
             .drop_nulls().collect().sort("timestamp_us"))
    except (FileNotFoundError, loader.HoldoutViolation):
        return None
    if q.is_empty():
        return None
    d0, d1 = day_grid(date)
    grid = np.arange(d0, d1, GRID_US)
    out = np.full(len(grid), np.nan)
    dur_us = {"5m": 300, "15m": 900}[family] * 1_000_000
    for (wts,), g in q.group_by("wts"):
        g = g.sort("timestamp_us")
        t = g["timestamp_us"].to_numpy()
        mid = ((g["bid_price"] + g["ask_price"]) / 2).to_numpy().astype(np.float64)
        w0 = int(wts) * 1_000_000
        lo = np.searchsorted(grid, w0, side="left")
        hi = np.searchsorted(grid, w0 + dur_us, side="left")
        idx = np.searchsorted(t, grid[lo:hi], side="right") - 1
        seg = np.where(idx >= 0, mid[np.clip(idx, 0, len(mid) - 1)], np.nan)
        out[lo:hi] = seg
    return out


def analyze_date(date: str) -> list[dict]:
    rows = []
    b = binance_series(date)
    if b is None:
        return rows
    rb = np.diff(np.log(b))
    pairs = {}
    c = chainlink_series(date)
    if c is not None:
        pairs["binance->chainlink"] = np.diff(np.log(c))
    o = pm_odds_series(date)
    if o is not None:
        pairs["binance->pm_odds_5m"] = np.diff(o)  # odds are prices in [0,1]
    for name, rx in pairs.items():
        corr, n_valid = xcorr_returns(rb, rx, MAX_LAG)
        if np.all(np.isnan(corr)):
            continue
        k = int(np.nanargmax(np.abs(corr)))
        rows.append({"date": date, "pair": name, "n_valid": n_valid,
                     "best_lag_ms": (k - MAX_LAG) * 250,
                     "best_corr": round(float(corr[k]), 4),
                     "corr_at_0": round(float(corr[MAX_LAG]), 4),
                     "corr_curve": [round(float(x), 5) if np.isfinite(x) else None
                                    for x in corr]})
    return rows


def main() -> None:
    have = set()
    if os.path.exists(OUT):
        have = set(pl.read_parquet(OUT)["date"].to_list())
    dates = sorted({os.path.basename(p)[:-8]
                    for p in __import__("glob").glob("data/processed/binance/aggTrades/*.parquet")})
    rng = loader.holdout_range()
    if rng:
        dates = [d for d in dates if not (rng[0] <= d <= rng[1])]
    rows = []
    for d in dates:
        if d in have:
            continue
        rows += analyze_date(d)
    if rows:
        new = pl.DataFrame(rows)
        if os.path.exists(OUT):
            new = pl.concat([pl.read_parquet(OUT), new], how="diagonal")
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        new.write_parquet(OUT)
    print(f"leadlag: {len(rows)} new date-pairs analyzed")


if __name__ == "__main__":
    main()
