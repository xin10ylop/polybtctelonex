"""Kalshi terminal snipe with REAL DEPTH — the test that decides it.

src/kalshi_snipe.py showed the edge exists at the touch, using 1-minute
candles that carry price but no size. That is exactly the gap that has killed
every promising result in this project, so it gets settled here against the
full-depth websocket book (bids/asks ladders, millisecond snapshots).

For each window we take the last book snapshot at or before T+840 (60s before
close) and WALK it for a target clip:

  lead UP   -> buy YES : walk the ask ladder upward from best_ask
  lead DOWN -> buy NO  : selling YES into the bid ladder, so walk bids
                         downward from best_bid; NO costs (1 - bid) per level

P&L uses the realised average fill price, not the touch, and charges Kalshi's
quadratic taker fee on it. Unfilled or partially filled clips are reported
honestly rather than assumed away.

  .venv/bin/python src/kalshi_depth.py BTC
  .venv/bin/python src/kalshi_depth.py ETH
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import statistics
import sys

import polars as pl


def walk(levels: list[tuple[float, float]], want: float, is_no: bool):
    """Walk a ladder for `want` contracts. Returns (avg_cost, filled).
    For NO, cost per contract at a bid level p is (1-p)."""
    spent = got = 0.0
    for p, sz in levels:
        if got >= want:
            break
        take = min(sz, want - got)
        spent += take * ((1 - p) if is_no else p)
        got += take
    return (spent / got if got else float("nan")), got


def main() -> None:
    coin = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    kld = ("data/processed/binance/eth_klines_1s" if coin == "ETH"
           else "data/processed/binance/klines_1s")

    idx = pl.concat([pl.read_parquet(f) for f in
                     sorted(glob.glob(f"data/kalshi/{coin}_settlement_index_*.parquet"))])
    idx = idx.with_columns(pl.col("price").cast(pl.Float64),
                           (pl.col("timestamp_us") // 1_000_000).alias("ts"))
    ref = dict(zip(idx["ts"].to_list(), idx["price"].to_list()))

    px: dict[int, float] = {}
    for f in sorted(glob.glob(f"{kld}/*.parquet")):
        day = f.split("/")[-1][:-8]
        if not ("2026-05" <= day <= "2026-06"):
            continue
        k = pl.read_parquet(f, columns=["open_time_us", "close"])
        px.update(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))

    MON = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
           "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

    def open_ts(m: str) -> int | None:
        """Window open from the ticker. MUST come from market_id, not the
        clock: Kalshi keeps quoting a market AFTER it closes, so a resolved
        market's post-close book (ask ~0.003) would otherwise be attributed to
        the NEXT window. Validated on 300 markets: every snapshot lands inside
        [T-60, T+960]. (ET is EDT for this May-Jul data.)"""
        try:
            q = m.split("-")[1]
            et = dt.datetime(2000 + int(q[:2]), MON[q[2:5]], int(q[5:7]),
                             int(q[7:9]), int(q[9:11]),
                             tzinfo=dt.timezone(dt.timedelta(hours=-4)))
            return int(et.timestamp()) - 900
        except Exception:
            return None

    # Two passes per file: the ladder columns are nested lists and blow memory
    # if the whole month is materialised (a single concat OOM'd at 15.9GB), so
    # pass 1 reads only the cheap columns to pick the exact rows we need.
    parts = []
    for f in sorted(glob.glob(f"data/kalshi/{coin}_15m_books_2026-0[56].parquet")):
        lite = pl.read_parquet(f, columns=["market_id", "timestamp_us"])
        lite = lite.with_columns((pl.col("timestamp_us") // 1_000_000).alias("ts"))
        tmap = {m: open_ts(m) for m in lite["market_id"].unique().to_list()}
        lite = lite.with_columns(
            pl.col("market_id").replace_strict(tmap, default=None).alias("T"))
        lite = lite.drop_nulls("T").filter(
            (pl.col("ts") <= pl.col("T") + 840) & (pl.col("ts") >= pl.col("T") + 780))
        if lite.height == 0:
            continue
        keep = lite.sort("ts").group_by("market_id").last()
        want = set(zip(keep["market_id"].to_list(), keep["timestamp_us"].to_list()))
        full = pl.read_parquet(f)
        full = full.filter(
            pl.struct(["market_id", "timestamp_us"]).map_elements(
                lambda r: (r["market_id"], r["timestamp_us"]) in want,
                return_dtype=pl.Boolean))
        full = full.with_columns((pl.col("timestamp_us") // 1_000_000).alias("ts"))
        full = full.with_columns(
            pl.col("market_id").replace_strict(tmap, default=None).alias("T"))
        parts.append(full.select("market_id", "ts", "T", "bids", "asks"))
        del lite, keep, full
    snap = pl.concat(parts) if parts else pl.DataFrame()
    bk = snap
    print(f"{coin}: {bk.height:,} book snapshots -> {snap.height:,} windows "
          f"with a quote at/before T+840")

    CLIPS = [100, 500, 1000, 5000]
    rows = {c: [] for c in CLIPS}
    stale = 0
    for T, ts, bids, asks in zip(snap["T"], snap["ts"], snap["bids"], snap["asks"]):
        K, st, s = ref.get(T), ref.get(T + 900), px.get(T + 840)
        if None in (K, st, s) or not K:
            continue
        if ts < T + 830:            # snapshot too old to represent T+840
            stale += 1
            continue
        lead = 1e4 * math.log(s / K)
        if lead == 0:
            continue
        up = lead > 0
        lv = ([(float(x["price"]), float(x["size"])) for x in asks] if up
              else [(float(x["price"]), float(x["size"])) for x in bids])
        lv.sort(key=lambda z: z[0], reverse=not up)   # cheapest NO = highest bid
        if not lv:
            continue
        won = up == (st > K)
        day = dt.datetime.utcfromtimestamp(T).strftime("%Y-%m-%d")
        for cl in CLIPS:
            avg, got = walk(lv, cl, is_no=not up)
            if got <= 0 or not (0 < avg < 1):
                rows[cl].append({"d": day, "lead": abs(lead), "filled": 0.0,
                                 "pnl": 0.0, "won": None, "px": None})
                continue
            fee = 0.07 * avg * (1 - avg)
            rows[cl].append({"d": day, "lead": abs(lead), "filled": got,
                             "pnl": got * ((1.0 if won else 0.0) - avg - fee),
                             "won": won, "px": avg})

    def rep(lab, rr, clip):
        f = [r for r in rr if r["filled"] > 0]
        if len(f) < 30:
            print(f"    {lab:<22} n={len(f)} (too few)")
            return
        p = [r["pnl"] for r in f]
        m = statistics.mean(p)
        sd = statistics.stdev(p)
        by: dict[str, list[float]] = {}
        for r in f:
            by.setdefault(r["d"], []).append(r["pnl"])
        dl = [statistics.mean(v) for v in by.values()]
        dtt = (statistics.mean(dl) / (statistics.stdev(dl) / math.sqrt(len(dl)))
               if len(dl) > 1 and statistics.stdev(dl) > 0 else float("nan"))
        fillrate = statistics.mean([r["filled"] for r in f]) / clip
        print(f"    {lab:<22} n={len(f):>5}  fill {fillrate:5.1%}  "
              f"win {100*sum(1 for r in f if r['won'])/len(f):6.2f}%  "
              f"avg px {statistics.mean([r['px'] for r in f]):.3f}  "
              f"${m:+8.2f}/trade  t={m/(sd/math.sqrt(len(p))):+5.2f}  "
              f"day-t={dtt:+5.2f}")

    print(f"  ({stale:,} windows dropped: no snapshot within 10s of T+840)\n")
    for cl in CLIPS:
        rr = [r for r in rows[cl] if r["lead"] >= 10]
        ds = sorted(set(r["d"] for r in rr))
        h = len(ds) // 2
        TR, VA = set(ds[:h]), set(ds[h:])
        print(f"  === clip {cl:,} contracts, |lead| >= 10bp ===")
        rep("TRAIN", [r for r in rr if r["d"] in TR], cl)
        rep("VAL", [r for r in rr if r["d"] in VA], cl)


if __name__ == "__main__":
    main()
