"""Phase 0.3 — one-day pipeline validation (2026-06-15).

Downloads ONE UTC day of data for all btc-updown-5m windows on that day
(trades/quotes/book_snapshot_25/onchain_fills, Up token; Down token for a
mirror-test sample; a few 15m/4h markets; crypto_prices for the day and the
next day so the last window's close tick exists). Then validates schemas,
reconstructs window outcomes from the Chainlink feed, and reconciles against
metadata result_id. Prints a compact summary; details to logs/phase0_oneday.log.
"""
from __future__ import annotations

import collections
import datetime as dt
import random
import sys

import polars as pl

sys.path.insert(0, "src")
import telonex_dl as tdl

DAY = "2026-06-15"
NEXT = "2026-06-16"
RAW = "data/raw/telonex"
LOG = open("logs/phase0_oneday.log", "a")


def log(*a):
    print(*a, file=LOG, flush=True)
    print(*a, flush=True)


def day_markets(prefix: str, step: int) -> pl.DataFrame:
    d0 = int(dt.datetime.fromisoformat(DAY + "T00:00:00+00:00").timestamp())
    lf = pl.scan_parquet(f"{RAW}/polymarket_markets.parquet")
    return (
        lf.filter(pl.col("slug").str.contains(rf"^{prefix}-(\d+)$"))
        .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("wts"))
        .filter((pl.col("wts") >= d0) & (pl.col("wts") < d0 + 86400))
        .select("slug", "wts", "market_id", "asset_id_0", "asset_id_1",
                "outcome_0", "outcome_1", "result_id", "status")
        .sort("wts")
        .collect()
    )


def build_tasks() -> list[tdl.Task]:
    tasks = [
        tdl.Task("crypto_prices", DAY, f"{RAW}/crypto_prices/{DAY}/btcusd.parquet", asset_id="btcusd"),
        tdl.Task("crypto_prices", NEXT, f"{RAW}/crypto_prices/{NEXT}/btcusd.parquet", asset_id="btcusd"),
    ]
    m5 = day_markets("btc-updown-5m", 300)
    log(f"5m markets on {DAY}: {len(m5)}")
    for r in m5.iter_rows(named=True):
        for ch in ("trades", "quotes", "book_snapshot_25", "onchain_fills"):
            tasks.append(tdl.Task(ch, DAY, f"{RAW}/{ch}/{DAY}/{r['slug']}_Up.parquet",
                                  slug=r["slug"], outcome="Up"))
    # mirror-test sample: Down tokens for 10 random windows (quotes + book)
    rng = random.Random(42)
    for r in rng.sample(list(m5.iter_rows(named=True)), 10):
        for ch in ("quotes", "book_snapshot_25"):
            tasks.append(tdl.Task(ch, DAY, f"{RAW}/{ch}/{DAY}/{r['slug']}_Down.parquet",
                                  slug=r["slug"], outcome="Down"))
    # a few 15m and 4h markets for schema sanity
    for prefix, step in (("btc-updown-15m", 900), ("btc-updown-4h", 14400)):
        m = day_markets(prefix, step)
        for r in list(m.iter_rows(named=True))[:3]:
            for ch in ("trades", "quotes"):
                tasks.append(tdl.Task(ch, DAY, f"{RAW}/{ch}/{DAY}/{r['slug']}_Up.parquet",
                                      slug=r["slug"], outcome="Up"))
    return tasks


def download() -> None:
    tasks = build_tasks()
    log(f"total download tasks: {len(tasks)}")
    counts: collections.Counter = collections.Counter()
    sizes: collections.defaultdict = collections.defaultdict(int)

    def on_result(res: tdl.Result):
        counts[res.status] += 1
        sizes[res.task.channel] += res.bytes
        if res.status == "error":
            log(f"ERROR {res.task.channel} {res.task.slug or res.task.asset_id}: {res.detail}")

    t0 = dt.datetime.now()
    tdl.run(tasks, concurrency=8, on_result=on_result)
    took = (dt.datetime.now() - t0).total_seconds()
    log(f"downloaded in {took:.0f}s: {dict(counts)}")
    for ch, b in sorted(sizes.items()):
        log(f"  {ch}: {b/1e6:.1f} MB")


def validate() -> None:
    # --- schemas ---
    for ch in ("trades", "quotes", "book_snapshot_25", "onchain_fills"):
        files = list(__import__("glob").glob(f"{RAW}/{ch}/{DAY}/*.parquet"))
        if not files:
            log(f"{ch}: NO FILES")
            continue
        df = pl.read_parquet(files[0])
        log(f"\n{ch}: {len(files)} files; sample schema ({files[0].split('/')[-1]}):")
        log("  " + ", ".join(f"{n}:{t}" for n, t in df.schema.items()))
        log(f"  rows in sample: {len(df)}")
    cp = pl.read_parquet(f"{RAW}/crypto_prices/{DAY}/btcusd.parquet")
    log(f"\ncrypto_prices schema: " + ", ".join(f"{n}:{t}" for n, t in cp.schema.items()))
    log(f"crypto_prices rows on {DAY}: {len(cp)}")

    # --- outcome reconstruction vs result_id ---
    cp2 = pl.concat([cp, pl.read_parquet(f"{RAW}/crypto_prices/{NEXT}/btcusd.parquet")])
    m5 = day_markets("btc-updown-5m", 300)
    ts_cols = [c for c in cp2.columns if c.endswith("timestamp_us") or c == "timestamp_us"]
    price_col = "price" if "price" in cp2.columns else [c for c in cp2.columns if "price" in c][0]
    for tcol in ts_cols:
        s = cp2.sort(tcol)
        t = s[tcol].to_numpy()
        p = s[price_col].to_numpy()
        import numpy as np
        wts = m5["wts"].to_numpy() * 1_000_000
        i_open = np.searchsorted(t, wts, side="left")
        i_close = np.searchsorted(t, wts + 300_000_000, side="left")
        ok = (i_open < len(t)) & (i_close < len(t))
        opens, closes = p[np.clip(i_open, 0, len(t)-1)], p[np.clip(i_close, 0, len(t)-1)]
        up_wins = closes > opens
        # result_id: index of winning outcome; outcome_0 = Up
        actual_up = (m5["result_id"] == "0").to_numpy()
        match = (up_wins == actual_up) & ok
        log(f"\n[{tcol}] outcome match: {match.sum()}/{ok.sum()} "
            f"({100*match.sum()/max(ok.sum(),1):.2f}%)  ties(close==open): {(closes==opens).sum()}")

    # --- mirror test: Up vs Down quotes ---
    import glob as g
    downs = g.glob(f"{RAW}/quotes/{DAY}/*_Down.parquet")
    mism = []
    for dpath in downs:
        upath = dpath.replace("_Down", "_Up")
        try:
            du, dd = pl.read_parquet(upath), pl.read_parquet(dpath)
        except Exception:
            continue
        tcol = "local_timestamp_us" if "local_timestamp_us" in du.columns else du.columns[0]
        j = du.sort(tcol).join_asof(dd.sort(tcol), on=tcol, strategy="backward", suffix="_d")
        j = j.drop_nulls(subset=["bid_price_d"]) if "bid_price_d" in j.columns else j
        if "bid_price" in j.columns and "ask_price_d" in j.columns:
            err = (j["bid_price"] - (1 - j["ask_price_d"])).abs().mean()
            mism.append(err)
    if mism:
        log(f"\nmirror test (mean |up_bid - (1-down_ask)|) over {len(mism)} windows: "
            f"{sum(mism)/len(mism):.5f}")


if __name__ == "__main__":
    download()
    validate()
    LOG.close()
