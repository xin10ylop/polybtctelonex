"""NIXULTIMATE 2.0 bulk — hourly market tick data, Oct 2025 -> Jul 2026.

The hourly 'Bitcoin Up or Down {hour} ET' series has FULL Telonex off-chain
coverage (books/quotes/trades) across the whole collection window; the
series renamed its slugs around Apr 6 (year added), which is why it looked
discontinued. Markets exist under both slug forms for some hours — we try
both asset ids per hour; 404s are free; if both return data the year-form
(newer) wins at consolidation time via file overwrite order.

Per UTC date: download quotes/trades/book_snapshot_25 for every hourly
market whose HOUR STARTS that date (Up token only — mirror verified exact
on 2026-06-15), saved under the synthetic raw name
  data/raw/telonex/{channel}/{date}/btc-updown-1h-{wts}_Up.parquet
so src/consolidate.py handles the 1h family unchanged; then consolidate the
date and delete raw. Resumable via data/processed/daily/1h markers.

Split discipline (pre-registered for the 1h family):
  TRAIN <= 2026-03-19 | VAL 2026-03-20..2026-05-12 | RESERVE 2026-05-13+
  (reserve stays sealed by the loader's holdout date guard; one-shot only)

Usage: nohup .venv/bin/python src/hourly_bulk.py > logs/hourly_bulk.log 2>&1 &
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sys

import polars as pl

sys.path.insert(0, "src")
import consolidate
import telonex_dl as tdl

CHANNELS = ["quotes", "trades", "book_snapshot_25"]
HOURLY_RE = re.compile(r"^bitcoin-up-or-down-.*(am|pm)-et$")
START, END = "2025-10-11", "2026-07-07"


def hourly_markets() -> pl.DataFrame:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    h = (m.filter(pl.col("slug").str.contains(HOURLY_RE.pattern).fill_null(False))
          .filter(pl.col("end_date_us").is_not_null())
          .with_columns(((pl.col("end_date_us") // 1_000_000) - 3600).alias("wts")))
    h = h.with_columns(pl.from_epoch("wts").dt.strftime("%Y-%m-%d").alias("day"),
                       # year-form slugs sort AFTER old-form for same wts
                       pl.col("slug").str.contains(r"-\d{4}-").alias("year_form"))
    return h.filter((pl.col("day") >= START) & (pl.col("day") <= END)) \
            .sort("wts", "year_form")


def process_date(date: str, markets: pl.DataFrame) -> str:
    marker = f"data/processed/daily/1h/.done_{date}"
    if os.path.exists(marker):
        return "done"
    sub = markets.filter(pl.col("day") == date)
    if sub.is_empty():
        return "empty"
    tasks = []
    for r in sub.iter_rows(named=True):
        for ch in CHANNELS:
            out = (f"data/raw/telonex/{ch}/{date}/"
                   f"btc-updown-1h-{r['wts']}_Up.parquet")
            # year-form rows come last in sort order -> their download task
            # runs later; existing file skip means FIRST successful form wins.
            tasks.append(tdl.Task(channel=ch, date=date, out_path=out,
                                  asset_id=r["asset_id_0"]))
    res = tdl.run(tasks, concurrency=8)
    ok = sum(r.status in ("ok", "exists") for r in res)
    err = [r for r in res if r.status == "error"]
    if err:
        # leave no marker: the date retries in full on the next run
        print(f"{date}: {len(err)} errors (will retry) e.g. {err[0].detail}",
              flush=True)
        return "errors"
    consolidate.consolidate_quotes(date)
    consolidate.consolidate_trades(date)
    consolidate.consolidate_books(date)
    for ch in CHANNELS:
        shutil.rmtree(f"data/raw/telonex/{ch}/{date}", ignore_errors=True)
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    open(marker, "w").close()
    return f"{ok}/{len(tasks)} files"


def main() -> None:
    mk = hourly_markets()
    print(f"{len(mk)} hourly market rows, {mk['day'].n_unique()} dates", flush=True)
    day = dt.date.fromisoformat(START)
    end = dt.date.fromisoformat(END)
    while day <= end:
        date = day.isoformat()
        try:
            info = process_date(date, mk)
            print(f"{date}: {info}", flush=True)
        except Exception as e:
            print(f"{date}: FAILED {type(e).__name__}: {str(e)[:150]}", flush=True)
        day += dt.timedelta(days=1)
    print("HOURLY BULK DONE", flush=True)


if __name__ == "__main__":
    main()
