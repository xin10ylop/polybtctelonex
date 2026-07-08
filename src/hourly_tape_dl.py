"""NIXULTIMATE 2.0 data — hourly market trade tapes from Polymarket data-api.

The hourly 'Bitcoin Up or Down - {date} {hour} ET' series has NO Telonex tick
coverage, but the free data-api serves each market's complete print tape
(second-resolution timestamps, both tokens, side + size + price). This
downloads tapes for all resolved hourly markets in [START, END] and stores
one parquet per day keyed by the market's end_date (UTC).

Columns: end_us (window end), asset (token id), up_token (bool), side,
price, size, ts (unix s). Resumable; polite rate limiting.
Usage: nohup .venv/bin/python src/hourly_tape_dl.py > logs/hourly_tape.log 2>&1 &
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

import polars as pl

START = "2026-05-01"
END = "2026-07-08"
OUT = "data/processed/hourly/tape"
UA = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
      "Accept": "application/json"}


def fetch_tape(cid: str) -> list[dict] | None:
    """Full paginated tape, or None if the market stays unreachable."""
    rows = []
    for off in range(0, 20000, 500):
        url = (f"https://data-api.polymarket.com/trades?market={cid}"
               f"&limit=500&offset={off}")
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    t = json.load(r)
                break
            except Exception:
                time.sleep(3 * 2 ** attempt)
        else:
            print(f"  SKIP unreachable market {cid}", flush=True)
            return None
        rows += t
        if len(t) < 500:
            break
        time.sleep(0.15)
    return rows


def main() -> None:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    h = (m.filter(pl.col("slug").str.contains(r"^bitcoin-up-or-down-").fill_null(False))
          .filter(pl.col("result_id").is_in(["0", "1"]))
          .filter(pl.col("end_date_us").is_not_null()))
    h = h.with_columns((pl.col("end_date_us") // 1_000_000).alias("end_s"))
    h = h.with_columns(pl.from_epoch("end_s").dt.strftime("%Y-%m-%d").alias("day"))
    h = h.filter((pl.col("day") >= START) & (pl.col("day") <= END)).sort("end_s")
    os.makedirs(OUT, exist_ok=True)
    days = h.group_by("day").agg(pl.len()).sort("day")
    print(f"{len(h)} resolved hourly markets across {len(days)} days", flush=True)
    for day in days["day"]:
        out = f"{OUT}/{day}.parquet"
        if os.path.exists(out):
            continue
        sub = h.filter(pl.col("day") == day)
        recs = []
        for r in sub.iter_rows(named=True):
            tape = fetch_tape(r["market_id"])
            if tape is None:
                continue
            lo = r["end_s"] - 4200
            for x in tape:
                ts = int(x["timestamp"])
                if ts < lo or ts > r["end_s"] + 600:
                    continue
                recs.append({"end_us": int(r["end_date_us"]), "slug": r["slug"],
                             "result_id": r["result_id"],
                             "up_token": x["asset"] == r["asset_id_0"],
                             "side": x["side"], "price": float(x["price"]),
                             "size": float(x["size"]), "ts": ts})
            time.sleep(0.1)
        pl.DataFrame(recs, infer_schema_length=None).write_parquet(out)
        print(f"{day}: {len(sub)} markets, {len(recs)} prints", flush=True)
    print("HOURLY TAPE DONE", flush=True)


if __name__ == "__main__":
    main()
