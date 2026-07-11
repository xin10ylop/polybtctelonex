"""Test the cheap+signal edge on ETH and SOL (2026-07-11).

The coin raw data was deleted by the streaming campaign, and its stored book
is final-30s only (wrong slice). So this re-downloads per day, consolidates the
FULL book (keeps the pre-open window), computes the SAME pre-open cheap+signal
rule as BTC (nix_scalp6/cheapsig), saves tiny rows, deletes the raw. Streaming
+ rollback-proof like the campaign.

Rule (frozen from BTC): T0 = boundary-0.5s. g = 1s coin-Binance return, z=g/sig
(sig = 1s-grid vol over prior 300s * sqrt(dur)). side=sign(g). Record the
signal-side pre-open ask + ToB depth + resolution. Analysis mirrors BTC:
cheap (ask<0.50) + |z|>=0.05, hold to resolution.

Output: results/coincs/{date}.parquet (date,coin,wts,g_bp,z,side,ask,tob_usd,win)
"""
from __future__ import annotations

import datetime as dt
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import consolidate
import telonex_dl as tdl
from mc_campaign import binance_aggtrades, load_ticks

COINS = [("eth", "ETHUSDT"), ("sol", "SOLUSDT")]
FAM, DUR = "5m", 300
BLAT = 150_000
LAT = 250_000
# recent dev window where BTC's edge was strongest (Apr 2 - May 12)
DATES = [(dt.date(2026, 4, 2) + dt.timedelta(days=i)).isoformat()
         for i in range((dt.date(2026, 5, 12) - dt.date(2026, 4, 2)).days + 1)]


def sh(cmd: str) -> int:
    return subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)


def push(msg: str) -> None:
    sh("git add results/coincs 2>/dev/null")
    if sh(f'git commit -m "{msg}" >/dev/null 2>&1') != 0:
        return
    for i in range(4):
        if sh("git push -u origin claude/polymarket-btc-strategy-ys9coc") == 0:
            return
        time.sleep(2 ** (i + 1))


def signal(bt, blog, T0):
    kbn = int(np.searchsorted(bt, T0 - BLAT, "right")) - 1
    kb1 = int(np.searchsorted(bt, T0 - BLAT - 1_000_000, "right")) - 1
    if kbn < 0 or kb1 < 0:
        return None
    g = (blog[kbn] - blog[kb1]) * 1e4
    base = T0 - 5_000_000
    grid = base - np.arange(300, -1, -1) * 1_000_000
    gi = np.searchsorted(bt, grid, "right") - 1
    gp = np.where(gi >= 0, blog[np.maximum(gi, 0)], np.nan)
    sig = float(np.nanstd(np.diff(gp))) * math.sqrt(float(DUR)) * 1e4
    if not (np.isfinite(sig) and sig > 0):
        return None
    return g, g / sig


def day_rows(date: str, subs: dict) -> list[dict]:
    rows = []
    for coin, sym in COINS:
        famkey = f"{coin}-{FAM}"
        bpath = f"data/processed/daily/{famkey}/bookcurves/{date}.parquet"
        if not os.path.exists(bpath):
            continue
        bt, blog = load_ticks(sym, date)
        if bt is None:
            continue
        b = pl.read_parquet(bpath).sort("wts", "local_timestamp_us")
        bw = b["wts"].to_numpy(); bts = b["local_timestamp_us"].to_numpy()
        bid0 = b["bid_p0"].to_numpy().astype(np.float64)
        ask0 = b["ask_p0"].to_numpy().astype(np.float64)
        asz0 = b["ask_s0"].to_numpy().astype(np.float64)
        bsz0 = b["bid_s0"].to_numpy().astype(np.float64)
        meta = subs.get((coin, FAM))
        if meta is None:
            continue
        for r_ in meta.iter_rows(named=True):
            w_ = r_["wts"]; rid = r_["result_id"]
            if rid not in ("0", "1"):
                continue
            up_won = rid == "0"
            T0 = w_ * 1_000_000 - 500_000
            sg = signal(bt, blog, T0)
            if sg is None:
                continue
            g, z = sg
            side = "up" if g > 0 else "down"
            lo = np.searchsorted(bw, w_, "left"); hi = np.searchsorted(bw, w_, "right")
            if hi <= lo:
                continue
            k = int(np.searchsorted(bts[lo:hi], T0 + LAT, "right")) - 1
            if k < 0:
                continue
            j = lo + k
            if side == "up":
                ask = ask0[j]; tusd = asz0[j] * ask0[j] if np.isfinite(asz0[j]) else None
            else:
                ask = 1 - bid0[j] if np.isfinite(bid0[j]) else np.nan
                tusd = bsz0[j] * (1 - bid0[j]) if np.isfinite(bsz0[j]) else None
            if not np.isfinite(ask):
                continue
            rows.append({"date": date, "coin": coin, "wts": int(w_),
                         "g_bp": round(g, 3), "z": round(z, 4), "side": side,
                         "win": int((side == "up") == up_won),
                         "ask": round(float(ask), 4),
                         "tob_usd": round(float(tusd), 1) if tusd else None})
    return rows


def process_day(date: str, subs: dict) -> bool:
    out = f"results/coincs/{date}.parquet"
    if os.path.exists(out):
        return False
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    tasks = []
    for (coin, fam), df in subs.items():
        sub = df.filter((pl.col("wts") >= d0) & (pl.col("wts") < d0 + 86400))
        for r in sub.iter_rows(named=True):
            tasks.append(tdl.Task(channel="book_snapshot_25", date=date,
                out_path=(f"data/raw/telonex/book_snapshot_25/{date}/"
                          f"{coin}-updown-{fam}-{r['wts']}_Up.parquet"),
                asset_id=r["asset_id_0"]))
    if not tasks:
        pl.DataFrame({"date": [date]}).write_parquet(out); return True
    res = tdl.run(tasks, concurrency=10)
    if [r for r in res if r.status == "error"]:
        print(f"{date}: download errors, skip", flush=True)
        shutil.rmtree(f"data/raw/telonex/book_snapshot_25/{date}", ignore_errors=True)
        return False
    consolidate.consolidate_books(date)  # FULL (keeps pre-open), not final_only
    shutil.rmtree(f"data/raw/telonex/book_snapshot_25/{date}", ignore_errors=True)
    for coin, sym in COINS:
        binance_aggtrades(sym, date)
    rows = day_rows(date, subs)
    os.makedirs("results/coincs", exist_ok=True)
    (pl.DataFrame(rows) if rows else pl.DataFrame({"date": [date]})).write_parquet(out)
    # cleanup
    for coin, _ in COINS:
        p = f"data/processed/daily/{coin}-{FAM}/bookcurves/{date}.parquet"
        if os.path.exists(p):
            os.remove(p)
        ap = f"data/processed/binance/aggTrades_{(coin+'usdt').upper()}/{date}.parquet"
        if os.path.exists(ap):
            os.remove(ap)
    return True


def main() -> None:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    subs = {}
    for coin, _ in COINS:
        subs[(coin, FAM)] = (
            m.filter(pl.col("slug").str.contains(rf"^{coin}-updown-{FAM}-\d+$").fill_null(False))
            .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1).cast(pl.Int64).alias("wts")))
    n = 0
    for date in DATES:
        if process_day(date, subs):
            n += 1
            push(f"coin cheapsig: {date}")
        print(date, flush=True)
    print("COIN_CHEAPSIG DONE")


if __name__ == "__main__":
    main()
