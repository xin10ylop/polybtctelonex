"""NIXULTIMATE 3.0 bulk — six coins x {5m,15m}, Apr 2 - Jul 7 2026.

Downloads book_snapshot_25 + trades (Up tokens; mirrors exact) for
eth/sol/xrp/bnb/doge/hype updown markets, consolidates per date into
data/processed/daily/{coin}-{fam}/..., deletes raw, marker per date.
Also: per-coin Chainlink broadcast (crypto_prices channel, {sym}usd) to
data/processed/coin_prices/{sym}/{date}.parquet, and Binance 1s klines to
data/processed/binance/klines_1s_{SYM}/{date}.parquet (HYPE may 404 on
Binance — logged, not fatal; that coin then has no nowcast leg).

Resumable. Usage:
  nohup .venv/bin/python src/multicoin_bulk.py > logs/multicoin_bulk.log 2>&1 &
"""
from __future__ import annotations

import datetime as dt
import io
import os
import shutil
import sys
import time
import urllib.request
import zipfile

import polars as pl

sys.path.insert(0, "src")
import consolidate
import telonex_dl as tdl

COINS = ["eth", "sol", "xrp", "bnb", "doge", "hype"]
FAMS = ["5m", "15m"]
START, END = "2026-04-02", "2026-07-07"
KL = ["open_time_us", "open", "high", "low", "close", "volume",
      "close_time_us", "qv", "n", "tb", "tq", "ig"]


def binance_klines(sym: str, date: str) -> bool:
    out = f"data/processed/binance/klines_1s_{sym}/{date}.parquet"
    if os.path.exists(out):
        return True
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
                return False
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    else:
        return False
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=KL)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    (df.select(pl.col("open_time_us").cast(pl.Int64),
               pl.col("open", "close").cast(pl.Float64))
       .write_parquet(out, compression="zstd"))
    return True


def main() -> None:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    subs = {}
    for coin in COINS:
        for fam in FAMS:
            subs[(coin, fam)] = (
                m.filter(pl.col("slug").str.contains(rf"^{coin}-updown-{fam}-\d+$")
                         .fill_null(False))
                .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1)
                              .cast(pl.Int64).alias("w")))
    day = dt.date.fromisoformat(START)
    end = dt.date.fromisoformat(END)
    while day <= end:
        date = day.isoformat()
        marker = f"data/processed/daily/.mc_done_{date}"
        if os.path.exists(marker):
            day += dt.timedelta(days=1)
            continue
        d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
        tasks = []
        for (coin, fam), df in subs.items():
            sub = df.filter((pl.col("w") >= d0) & (pl.col("w") < d0 + 86400))
            for r in sub.iter_rows(named=True):
                for ch in ("book_snapshot_25", "trades"):
                    tasks.append(tdl.Task(channel=ch, date=date,
                        out_path=(f"data/raw/telonex/{ch}/{date}/"
                                  f"{coin}-updown-{fam}-{r['w']}_Up.parquet"),
                        asset_id=r["asset_id_0"]))
        # per-coin chainlink broadcast (small, direct to processed)
        for coin in COINS:
            sym = coin + "usd"
            out = f"data/processed/coin_prices/{sym}/{date}.parquet"
            if not os.path.exists(out):
                tasks.append(tdl.Task(channel="crypto_prices", date=date,
                                      out_path=out, asset_id=sym))
        res = tdl.run(tasks, concurrency=10)
        err = [r for r in res if r.status == "error"]
        if err:
            print(f"{date}: {len(err)} errors (will retry) {err[0].detail}", flush=True)
            day += dt.timedelta(days=1)
            continue
        consolidate.consolidate_trades(date)
        consolidate.consolidate_books(date)
        for ch in ("book_snapshot_25", "trades"):
            shutil.rmtree(f"data/raw/telonex/{ch}/{date}", ignore_errors=True)
        for coin in COINS:
            sym = (coin + "usdt").upper()
            if coin != "hype" or True:
                ok = binance_klines(sym, date)
                if not ok and coin == "hype":
                    pass  # HYPE not on Binance spot — expected
        ok_n = sum(r.status in ("ok", "exists") for r in res)
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, "w").close()
        print(f"{date}: {ok_n}/{len(tasks)} files", flush=True)
        day += dt.timedelta(days=1)
    print("MULTICOIN BULK DONE", flush=True)


if __name__ == "__main__":
    main()
