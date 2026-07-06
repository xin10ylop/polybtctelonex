"""Consolidate raw per-market Telonex parquets into compact daily research files.

Storage design (measured on 2026-06-15, full raw day = ~1.5 GB):
  - quotes   -> BBO PRICE-CHANGE rows only, full time resolution, float32.
                (96% of raw quote updates are size-only jitter; prices keep
                full fidelity, sizes are as-of the last price change.)  ~6 MB/day
  - book_snapshot_25 -> cost-to-fill curves + depth aggregates on a 250ms grid
                inside [wts-900s, wts+dur+30s]. 250ms matches the minimum
                decision latency simulated in backtests.               ~29 MB/day
  - trades   -> full resolution, float32.                               ~6 MB/day
  - onchain_fills -> full economics, wallets hashed.                   ~18 MB/day
  - crypto_prices -> full resolution.                                  ~1.3 MB/day

Known fidelity trade-offs (accepted, documented):
  - book sizes/depth are 250ms-stale at most; BBO prices are exact.
  - maker fill simulation uses the full-res trades tape (exact) + BBO prices.

Output: data/processed/daily/{family}/{channel}/{date}.parquet
Raw per-market files are deleted after consolidation iff --rm-raw (bulk mode);
they are re-downloadable at any time (unlimited plan).
"""
from __future__ import annotations

import glob
import os
import re
import shutil

import numpy as np
import polars as pl

NOTIONALS = (50.0, 200.0, 1000.0, 5000.0)
FAMILY_RE = re.compile(r"^(btc-updown-(?:5m|15m|4h))-(\d+)_(Up|Down)\.parquet$")
DURATION = {"5m": 300, "15m": 900, "4h": 14400}
GRID_US = 250_000  # 250ms book grid
PRE_S, POST_S = 900, 30  # keep [wts-900, wts+dur+30]


def _family_of(slug_prefix: str) -> str:
    return slug_prefix.rsplit("-", 1)[-1]


def list_raw(channel: str, date: str) -> list[tuple[str, str, int, str]]:
    out = []
    for p in glob.glob(f"data/raw/telonex/{channel}/{date}/*.parquet"):
        m = FAMILY_RE.match(os.path.basename(p))
        if m:
            out.append((p, _family_of(m.group(1)), int(m.group(2)), m.group(3)))
    return out


def _write(by_family: dict[str, list[pl.DataFrame]], channel: str, date: str) -> None:
    for family, dfs in by_family.items():
        out = f"data/processed/daily/{family}/{channel}/{date}.parquet"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pl.concat(dfs).sort("wts", "timestamp_us").write_parquet(out, compression="zstd")


def consolidate_quotes(date: str) -> None:
    by_family: dict[str, list[pl.DataFrame]] = {}
    for path, family, wts, outcome in list_raw("quotes", date):
        if outcome != "Up":
            continue  # Down books are exact mirrors (verified 2026-06-15)
        df = (
            pl.read_parquet(path, columns=["timestamp_us", "local_timestamp_us",
                                           "bid_price", "bid_size", "ask_price", "ask_size"])
            .with_columns(pl.col("bid_price", "ask_price", "bid_size", "ask_size").cast(pl.Float32))
            .sort("timestamp_us")
        )
        chg = (pl.col("bid_price").diff().fill_null(1) != 0) | (pl.col("ask_price").diff().fill_null(1) != 0)
        df = df.filter(chg).with_columns(pl.lit(wts, dtype=pl.Int64).alias("wts"))
        by_family.setdefault(family, []).append(df)
    _write(by_family, "quotes", date)


def consolidate_trades(date: str) -> None:
    by_family: dict[str, list[pl.DataFrame]] = {}
    for path, family, wts, outcome in list_raw("trades", date):
        if outcome != "Up":
            continue
        df = (
            pl.read_parquet(path, columns=["timestamp_us", "local_timestamp_us",
                                           "price", "size", "side"])
            .with_columns(pl.col("price", "size").cast(pl.Float32))
            .with_columns(pl.lit(wts, dtype=pl.Int64).alias("wts"))
        )
        by_family.setdefault(family, []).append(df)
    _write(by_family, "trades", date)


def consolidate_fills(date: str) -> None:
    by_family: dict[str, list[pl.DataFrame]] = {}
    for path, family, wts, outcome in list_raw("onchain_fills", date):
        raw = pl.read_parquet(path)
        # schema evolution: pre-fee-era files (e.g. 2025-11-15) have no taker_fee
        # or outcome_id columns — fees genuinely didn't exist yet.
        fee_col = (pl.col("taker_fee").cast(pl.Float64) if "taker_fee" in raw.columns
                   else pl.lit(0.0, dtype=pl.Float64)).alias("taker_fee")
        oid_col = (pl.col("outcome_id") if "outcome_id" in raw.columns
                   else pl.lit(None, dtype=pl.UInt8)).alias("outcome_id")
        df = raw.select(
            pl.col("block_timestamp_us").alias("timestamp_us"),
            pl.col("maker").hash().alias("maker_h"),
            pl.col("taker").hash().alias("taker_h"),
            pl.col("maker_side").cast(pl.String),
            pl.col("taker_side").cast(pl.String),
            pl.col("mirrored"),
            oid_col,
            pl.col("amount").cast(pl.Float64),
            pl.col("price").cast(pl.Float64),
            fee_col,
            pl.lit(wts, dtype=pl.Int64).alias("wts"),
            pl.lit(outcome).alias("token"),
        )
        by_family.setdefault(family, []).append(df)
    _write(by_family, "fills", date)


def _walk_curves(prices: np.ndarray, sizes: np.ndarray, notionals=NOTIONALS):
    """For each snapshot row and $ notional: average fill price, shares filled,
    and whether the visible book was exhausted before the budget."""
    lvl_cost = np.nan_to_num(prices * sizes)
    lvl_sz = np.nan_to_num(sizes)
    cum_cost = np.cumsum(lvl_cost, axis=1)
    cum_sz = np.cumsum(lvl_sz, axis=1)
    n_rows, n_lvl = prices.shape
    rows = np.arange(n_rows)
    out = {}
    for N in notionals:
        full = cum_cost <= N
        cost_before = np.where(full, cum_cost, 0).max(axis=1)
        sz_before = np.where(full, cum_sz, 0).max(axis=1)
        idx = full.sum(axis=1)
        has_partial = idx < n_lvl
        idx_c = np.clip(idx, 0, n_lvl - 1)
        p_next = np.where(has_partial, prices[rows, idx_c], np.nan)
        s_next = np.where(has_partial, np.nan_to_num(sizes[rows, idx_c]), 0.0)
        remaining = N - cost_before
        extra = np.where(has_partial & (p_next > 0) & np.isfinite(p_next),
                         remaining / np.where(np.isfinite(p_next) & (p_next > 0), p_next, 1.0), 0.0)
        extra = np.minimum(extra, s_next)
        shares = sz_before + extra
        spent = cost_before + extra * np.nan_to_num(p_next)
        avg_px = np.where(shares > 0, spent / np.maximum(shares, 1e-12), np.nan)
        exhausted = spent < N * 0.999
        out[N] = (avg_px.astype(np.float32), shares.astype(np.float32), exhausted)
    return out


def consolidate_books(date: str) -> None:
    by_family: dict[str, list[pl.DataFrame]] = {}
    bid_p = [f"bid_price_{i}" for i in range(25)]
    bid_s = [f"bid_size_{i}" for i in range(25)]
    ask_p = [f"ask_price_{i}" for i in range(25)]
    ask_s = [f"ask_size_{i}" for i in range(25)]
    for path, family, wts, outcome in list_raw("book_snapshot_25", date):
        if outcome != "Up":
            continue
        dur = DURATION[family]
        lo = (wts - PRE_S) * 1_000_000
        hi = (wts + dur + POST_S) * 1_000_000
        df = (
            pl.read_parquet(path)
            .filter(pl.col("timestamp_us").is_between(lo, hi))
            .sort("timestamp_us")
        )
        if df.is_empty():
            continue
        # 250ms grid: last snapshot per bucket
        df = (df.with_columns((pl.col("timestamp_us") // GRID_US).alias("bucket"))
                .group_by("bucket").last().sort("timestamp_us").drop("bucket"))
        df = df.with_columns([pl.col(c).cast(pl.Float32) for c in bid_p + bid_s + ask_p + ask_s])
        ap, asz = df.select(ask_p).to_numpy(), df.select(ask_s).to_numpy()
        bp, bsz = df.select(bid_p).to_numpy(), df.select(bid_s).to_numpy()
        cols: dict = {"timestamp_us": df["timestamp_us"],
                      "local_timestamp_us": df["local_timestamp_us"],
                      "bid_p0": df["bid_price_0"], "bid_s0": df["bid_size_0"],
                      "ask_p0": df["ask_price_0"], "ask_s0": df["ask_size_0"]}
        for side, P, S in (("buy", ap, asz), ("sell", bp, bsz)):
            for N, (px, sh, ex) in _walk_curves(P, S).items():
                cols[f"{side}_avgpx_{int(N)}"] = np.round(px, 5)
                cols[f"{side}_shares_{int(N)}"] = np.round(sh, 2)
                cols[f"{side}_exhaust_{int(N)}"] = ex
        b0, a0 = bp[:, [0]], ap[:, [0]]
        cols["bid_depth_5c"] = np.nansum(np.where(bp >= b0 - 0.05, bsz, 0), axis=1).astype(np.float32)
        cols["ask_depth_5c"] = np.nansum(np.where(ap <= a0 + 0.05, asz, 0), axis=1).astype(np.float32)
        out_df = pl.DataFrame(cols).with_columns(pl.lit(wts, dtype=pl.Int64).alias("wts"))
        by_family.setdefault(family, []).append(out_df)
    _write(by_family, "bookcurves", date)


def consolidate_crypto_prices(date: str) -> None:
    src = f"data/raw/telonex/crypto_prices/{date}/btcusd.parquet"
    if not os.path.exists(src):
        return
    out = f"data/processed/daily/crypto_prices/{date}.parquet"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    (pl.read_parquet(src)
       .select("timestamp_us", "server_timestamp_us", "local_timestamp_us",
               pl.col("price").cast(pl.Float64))
       .sort("timestamp_us")
       .write_parquet(out, compression="zstd"))


def consolidate_day(date: str, rm_raw: bool = False) -> None:
    consolidate_quotes(date)
    consolidate_trades(date)
    consolidate_fills(date)
    consolidate_books(date)
    consolidate_crypto_prices(date)
    if rm_raw:
        for ch in ("quotes", "trades", "onchain_fills", "book_snapshot_25"):
            d = f"data/raw/telonex/{ch}/{date}"
            if os.path.isdir(d):
                shutil.rmtree(d)


if __name__ == "__main__":
    import sys
    consolidate_day(sys.argv[1], rm_raw="--rm-raw" in sys.argv)
    print("done", sys.argv[1])
