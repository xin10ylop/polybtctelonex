"""Phase 0.4b — bulk Binance BTC/USDT history from data.binance.vision.

1s klines + aggTrades daily zips -> compact parquet in data/processed/binance/.
Resumable (skips existing parquet). Background job.

Usage: nohup .venv/bin/python src/bulk_binance.py > logs/bulk_binance.log 2>&1 &
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

START = dt.date(2025, 10, 1)
END = dt.date(2026, 7, 5)

KL_COLS = ["open_time_us", "open", "high", "low", "close", "volume", "close_time_us",
           "quote_volume", "n_trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
AT_COLS = ["agg_id", "price", "qty", "first_id", "last_id", "ts_us", "is_buyer_maker", "best_match"]


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
    raise RuntimeError(f"failed: {url}")


def do_klines(date: str) -> bool:
    out = f"data/processed/binance/klines_1s/{date}.parquet"
    if os.path.exists(out):
        return True
    raw = fetch_zip_csv("https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/"
                        f"BTCUSDT-1s-{date}.zip")
    if raw is None:
        return False
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=KL_COLS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    (df.select(
        pl.col("open_time_us").cast(pl.Int64),
        pl.col("open", "high", "low", "close").cast(pl.Float64),
        pl.col("volume", "taker_buy_volume").cast(pl.Float32),
        pl.col("n_trades").cast(pl.Int32),
    ).write_parquet(out, compression="zstd"))
    return True


def do_aggtrades(date: str) -> bool:
    out = f"data/processed/binance/aggTrades/{date}.parquet"
    if os.path.exists(out):
        return True
    raw = fetch_zip_csv("https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/"
                        f"BTCUSDT-aggTrades-{date}.zip")
    if raw is None:
        return False
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=AT_COLS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    (df.select(
        pl.col("ts_us").cast(pl.Int64),
        pl.col("price").cast(pl.Float64),
        pl.col("qty").cast(pl.Float32),
        pl.col("is_buyer_maker").cast(pl.Boolean),
    ).write_parquet(out, compression="zstd"))
    return True


def main() -> None:
    day = START
    misses = []
    while day <= END:
        date = day.isoformat()
        ok_k = do_klines(date)
        ok_a = do_aggtrades(date)
        if not (ok_k and ok_a):
            misses.append(date)
        if day.day == 1:
            print(f"{date} reached", flush=True)
        day += dt.timedelta(days=1)
    print("BINANCE DONE; missing days:", misses, flush=True)


if __name__ == "__main__":
    main()
