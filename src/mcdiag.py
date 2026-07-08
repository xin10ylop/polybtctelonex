"""Multi-coin gate diagnostic — is any coin's 5m family still in April-state?

For every resolved 5m window of each coin on the diagnostic day: the best
ask on the WINNING token as-of T+250ms (T = close-3s), from raw quotes.
BTC's July baseline: ~0.98-0.99 (gate shut). A coin showing 0.90-0.95
medians has the food our frozen machine eats. Also: final-30s print count
(activity) and the winner-ask share below 0.98 / 0.95.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")

DATE = "2026-07-06"


def main() -> None:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    d0 = int(dt.datetime.fromisoformat(DATE + "T00:00:00+00:00").timestamp())
    for coin in ("eth", "sol", "xrp", "bnb", "doge", "hype"):
        ud = (m.filter(pl.col("slug").str.contains(rf"^{coin}-updown-5m-\d+$").fill_null(False))
               .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("w"))
               .filter((pl.col("w") >= d0) & (pl.col("w") < d0 + 86400)))
        res = {int(r["w"]): r["result_id"] for r in ud.iter_rows(named=True)}
        asks, prints = [], []
        for p in sorted(glob.glob(f"data/raw/telonex/mcdiag/{coin}/quotes/*_Up.parquet")):
            w = int(os.path.basename(p).split("_")[0])
            rid = res.get(w)
            if rid not in ("0", "1"):
                continue
            q = pl.read_parquet(p, columns=["local_timestamp_us", "bid_price", "ask_price"]) \
                .sort("local_timestamp_us")
            T = (w + 297) * 1_000_000 + 250_000
            k = q.filter(pl.col("local_timestamp_us") <= T).tail(1)
            if k.is_empty():
                continue
            bid = float(k["bid_price"][0]) if k["bid_price"][0] is not None else np.nan
            ask = float(k["ask_price"][0]) if k["ask_price"][0] is not None else np.nan
            wask = ask if rid == "0" else (1 - bid if np.isfinite(bid) else np.nan)
            if np.isfinite(wask):
                asks.append(wask)
            tp = p.replace("/quotes/", "/trades/")
            if os.path.exists(tp):
                t = pl.read_parquet(tp, columns=["local_timestamp_us"])
                n30 = len(t.filter(pl.col("local_timestamp_us") >= (w + 270) * 1_000_000))
                prints.append(n30)
        if not asks:
            print(f"{coin}: no data")
            continue
        a = np.array(asks)
        print(f"{coin}-5m {DATE}: windows {len(a)} | winner-ask@T-3s: "
              f"median {np.median(a):.3f} q25 {np.percentile(a, 25):.3f} "
              f"| share<0.98: {(a < 0.98).mean():.0%} <0.95: {(a < 0.95).mean():.0%} "
              f"| final-30s prints median {np.median(prints) if prints else 0:.0f}")


if __name__ == "__main__":
    main()
