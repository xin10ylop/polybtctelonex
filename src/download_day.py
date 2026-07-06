"""Download + consolidate ONE UTC day of BTC up/down data. Bulk worker unit.

Usage: python src/download_day.py YYYY-MM-DD [--rm-raw] [--concurrency N]

Downloads, for every btc-updown market whose WINDOW falls on that UTC date:
  - 5m/15m/4h: trades, quotes, book_snapshot_25, onchain_fills (Up token only;
    Down books are exact mirrors — verified 2026-06-15)
  - hourly ET-named markets (era ended 2026-04-06): quotes only
  - crypto_prices (btcusd) when the date is >= 2026-04-02
then consolidates into data/processed/daily/ and (with --rm-raw) deletes raw.

Resumable at two levels: consolidated outputs make the whole day a no-op
(marker file), and raw files already on disk are skipped by telonex_dl.
"""
from __future__ import annotations

import collections
import datetime as dt
import os
import sys

import polars as pl

sys.path.insert(0, os.path.dirname(__file__))
import consolidate
import telonex_dl as tdl

RAW = "data/raw/telonex"
MARKETS = f"{RAW}/polymarket_markets.parquet"
CRYPTO_PRICES_FROM = "2026-04-02"
HOURLY_RE = r"^bitcoin-up-or-down-[a-z]+-\d+(-\d+)?-?(am|pm)-et$"
CHANNELS = ("trades", "quotes", "book_snapshot_25", "onchain_fills")


def day_bounds(date: str) -> tuple[int, int]:
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    return d0, d0 + 86400


def build_tasks(date: str) -> list[tdl.Task]:
    d0, d1 = day_bounds(date)
    lf = pl.scan_parquet(MARKETS)
    tasks: list[tdl.Task] = []

    for fam, prefix in (("5m", "btc-updown-5m"), ("15m", "btc-updown-15m"),
                        ("4h", "btc-updown-4h")):
        m = (
            lf.filter(pl.col("slug").str.contains(rf"^{prefix}-(\d+)$"))
            .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("wts"))
            .filter((pl.col("wts") >= d0) & (pl.col("wts") < d1))
            .select("slug", "wts", *[f"{c}_from" for c in CHANNELS])
            .collect()
        )
        for r in m.iter_rows(named=True):
            for ch in CHANNELS:
                if not r[f"{ch}_from"]:
                    continue  # no data for this channel per metadata
                tasks.append(tdl.Task(ch, date, f"{RAW}/{ch}/{date}/{r['slug']}_Up.parquet",
                                      slug=r["slug"], outcome="Up"))

    # hourly ET-named markets: window = [end-3600, end); quotes only
    h = (
        lf.filter(pl.col("slug").str.contains(HOURLY_RE))
        .with_columns((pl.col("end_date_us") // 1_000_000).alias("end_s"))
        .filter((pl.col("end_s") - 3600 >= d0) & (pl.col("end_s") - 3600 < d1))
        .select("slug", "end_s", "outcome_0", "quotes_from")
        .collect()
    )
    for r in h.iter_rows(named=True):
        if not r["quotes_from"] or r["outcome_0"] not in ("Up", "Down"):
            continue
        wts = int(r["end_s"]) - 3600
        out = "Up" if r["outcome_0"] == "Up" or "Up" in (r["outcome_0"],) else r["outcome_0"]
        tasks.append(tdl.Task("quotes", date,
                              f"{RAW}/quotes/{date}/btc-updown-1h-{wts}_Up.parquet",
                              slug=r["slug"], outcome="Up"))

    if date >= CRYPTO_PRICES_FROM:
        tasks.append(tdl.Task("crypto_prices", date,
                              f"{RAW}/crypto_prices/{date}/btcusd.parquet",
                              asset_id="btcusd"))
    return tasks


def process_day(date: str, rm_raw: bool = False, concurrency: int = 8) -> dict:
    marker = f"data/processed/daily/.done_{date}"
    if os.path.exists(marker):
        return {"date": date, "skipped": True}
    tasks = build_tasks(date)
    counts: collections.Counter = collections.Counter()
    nbytes = 0
    errors: list[str] = []

    def on_result(res: tdl.Result):
        nonlocal nbytes
        counts[res.status] += 1
        nbytes += res.bytes
        if res.status == "error":
            errors.append(f"{res.task.channel}/{res.task.slug or res.task.asset_id}: {res.detail}")

    t0 = dt.datetime.now()
    tdl.run(tasks, concurrency=concurrency, on_result=on_result)
    dl_s = (dt.datetime.now() - t0).total_seconds()
    if errors:
        raise RuntimeError(f"{date}: {len(errors)} download errors; first: {errors[:3]}")
    consolidate.consolidate_day(date, rm_raw=rm_raw)
    cons_s = (dt.datetime.now() - t0).total_seconds() - dl_s
    open(marker, "w").write(f"{dt.datetime.now(dt.UTC).isoformat()} tasks={len(tasks)} bytes={nbytes}\n")
    return {"date": date, "tasks": len(tasks), "ok": counts["ok"], "exists": counts["exists"],
            "missing": counts["missing"], "raw_mb": round(nbytes / 1e6, 1),
            "dl_s": round(dl_s), "cons_s": round(cons_s)}


if __name__ == "__main__":
    date = sys.argv[1]
    stats = process_day(date, rm_raw="--rm-raw" in sys.argv)
    print(stats)
