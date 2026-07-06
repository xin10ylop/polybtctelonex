"""Phase 0.5 — windows table: one row per market window.

open/close = FIRST crypto_prices tick (source `timestamp_us`) at/after the
window start/end boundary. Resolution rule (official market description,
verified 2026-07-06 + 288/288 reconstruction match on 2026-06-15):
    close >= open  ->  Up (result_id 0), else Down (result_id 1).

`shift_us` exists ONLY for the look-ahead unit test (shifts the price feed
forward so boundary lookups see future-shifted data; results must change).
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader

FAMILY_DUR = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
SLUG_PREFIX = {"5m": "btc-updown-5m", "15m": "btc-updown-15m", "4h": "btc-updown-4h"}
MARKETS = "data/raw/telonex/polymarket_markets.parquet"


def market_meta(family: str, d0: int, d1: int) -> pl.DataFrame:
    prefix = SLUG_PREFIX[family]
    return (
        pl.scan_parquet(MARKETS)
        .filter(pl.col("slug").str.contains(rf"^{prefix}-(\d+)$"))
        .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("wts"))
        .filter((pl.col("wts") >= d0) & (pl.col("wts") < d1))
        .select("slug", "wts", "market_id", "asset_id_0", "asset_id_1",
                "result_id", "status", "settled_at_us")
        .sort("wts")
        .collect()
    )


def build_windows(family: str, dates: list[str], holdout_final_run: bool = False,
                  shift_us: int = 0) -> pl.DataFrame:
    """Build the windows table for the given UTC dates."""
    dur = FAMILY_DUR[family]
    d0 = int(dt.datetime.fromisoformat(dates[0] + "T00:00:00+00:00").timestamp())
    d1 = int(dt.datetime.fromisoformat(dates[-1] + "T00:00:00+00:00").timestamp()) + 86400
    meta = market_meta(family, d0, d1)

    # price feed must extend one day past the end for last-window closes
    next_day = (dt.date.fromisoformat(dates[-1]) + dt.timedelta(days=1)).isoformat()
    cp_dates = dates + [next_day]
    try:
        cp = (loader.load_crypto_prices(cp_dates, holdout_final_run)
              .select("timestamp_us", "price").collect().sort("timestamp_us"))
    except FileNotFoundError:
        cp = None

    out = meta.with_columns(pl.lit(dur, dtype=pl.Int32).alias("duration"))
    if cp is not None and len(cp):
        t = cp["timestamp_us"].to_numpy() + shift_us
        p = cp["price"].to_numpy()
        wts_us = meta["wts"].to_numpy() * 1_000_000
        i_open = np.searchsorted(t, wts_us, side="left")
        i_close = np.searchsorted(t, wts_us + dur * 1_000_000, side="left")
        valid = (i_open < len(t)) & (i_close < len(t))
        opens = np.where(valid, p[np.clip(i_open, 0, len(t) - 1)], np.nan)
        closes = np.where(valid, p[np.clip(i_close, 0, len(t) - 1)], np.nan)
        recon = np.where(np.isnan(opens) | np.isnan(closes), None,
                         np.where(closes >= opens, "0", "1"))
        out = out.with_columns(
            pl.Series("open_chainlink", opens, dtype=pl.Float64),
            pl.Series("close_chainlink", closes, dtype=pl.Float64),
            pl.Series("outcome_reconstructed", recon, dtype=pl.String),
        )
    else:
        out = out.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("open_chainlink"),
            pl.lit(None, dtype=pl.Float64).alias("close_chainlink"),
            pl.lit(None, dtype=pl.String).alias("outcome_reconstructed"),
        )
    return out


def reconciliation_rate(w: pl.DataFrame) -> tuple[int, int]:
    """(n_match, n_comparable) between reconstructed outcome and result_id."""
    c = w.filter(pl.col("outcome_reconstructed").is_not_null()
                 & pl.col("result_id").is_in(["0", "1"]))
    return int((c["outcome_reconstructed"] == c["result_id"]).sum()), len(c)


if __name__ == "__main__":
    family, *dates = sys.argv[1:]
    w = build_windows(family, dates)
    m, n = reconciliation_rate(w)
    print(f"{family}: {len(w)} windows, outcome reconciliation {m}/{n}")
