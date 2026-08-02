"""ETHUSDT 1s klines from data.binance.vision, matching the BTC layout.

Needed because every local price series is BTCUSDT, so the Kalshi ETH 15m
question (KXETH15M, settled on CF Benchmarks' ETHUSD_RTI) could not be tested
at all — the signal had nothing to be computed from.

Same conventions as src/bulk_binance.py: daily zips -> compact parquet,
resumable (skips existing), so it can be re-run or backgrounded safely.

  nohup .venv/bin/python src/bulk_eth.py > logs/bulk_eth.log 2>&1 &
"""
from __future__ import annotations

import datetime as dt
import io
import os
import sys
import time
import urllib.request
import zipfile

import polars as pl

# Kalshi archive runs 2026-05-02..2026-07-30; fetch that plus a warm-up margin
# for the 300s volatility window at the first boundary of each day.
START = dt.date(2026, 5, 1)
END = dt.date(2026, 7, 31)
OUT = "data/processed/binance/eth_klines_1s"

KL_COLS = ["open_time_us", "open", "high", "low", "close", "volume", "close_time_us",
           "quote_volume", "n_trades", "taker_buy_volume", "taker_buy_quote_volume",
           "ignore"]


def fetch_zip_csv(url: str) -> bytes | None:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
                return z.read(z.namelist()[0])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    return None


def do_day(date: str) -> str:
    out = f"{OUT}/{date}.parquet"
    if os.path.exists(out):
        return "skip"
    raw = fetch_zip_csv("https://data.binance.vision/data/spot/daily/klines/ETHUSDT/1s/"
                        f"ETHUSDT-1s-{date}.zip")
    if raw is None:
        return "404"
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=KL_COLS)
    os.makedirs(OUT, exist_ok=True)
    (df.select(
        pl.col("open_time_us").cast(pl.Int64),
        pl.col("open", "high", "low", "close").cast(pl.Float64),
        pl.col("volume", "taker_buy_volume").cast(pl.Float32),
        pl.col("n_trades").cast(pl.Int32),
    ).write_parquet(out, compression="zstd"))
    return "ok"


def main() -> None:
    d, n_ok, n_skip, n_miss = START, 0, 0, 0
    while d <= END:
        r = do_day(d.isoformat())
        n_ok += r == "ok"; n_skip += r == "skip"; n_miss += r == "404"
        if r == "ok" and n_ok % 10 == 0:
            print(f"  {d} ... {n_ok} fetched", flush=True)
        d += dt.timedelta(days=1)
    print(f"DONE eth klines_1s: {n_ok} fetched, {n_skip} already present, "
          f"{n_miss} unavailable")


if __name__ == "__main__":
    main()
