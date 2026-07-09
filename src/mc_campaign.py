"""NIXULTIMATE 3.0 — rollback-proof STREAMING multicoin campaign.

The container can be reclaimed and restored from a stale snapshot at any
time; only pushed commits survive. So this campaign never accumulates data:
for each day it downloads the six coins' 5m/15m books+tape, runs the FROZEN
machine (nix1 gates, zero retuning) plus a full gate monitor on every
resolved window, writes one small parquet of per-window rows to results/mc/
(tracked), commits+pushes every N days, and deletes the day's data. A
relaunch after rollback resumes from the last PUSHED day marker.

Per-window row (even when no trade fires): z, fair, winner-ask, predicted-
side ask, EV, top-of-book price/size (for the $5 sizing check), Binance-vs-
anchor basis, and the frozen machine's trade outcome two ways (book-walk
fill, tape-validated fill). Signal feeds: coin's own Chainlink broadcast
(anchor, server_ts) + coin's Binance 1s klines (nowcast leg; HYPE has none
-> anchor-only, expected to fail like BTC broadcast-only did).

Order: 2026-07-06 FIRST (ETH audit anchor: mcdiag measured ~4 tape-validated
trades ~+$3.97 at $5), then 07-07, then Apr 2 -> Jul 5 chronologically.
Resolution reconciliation (coin feed vs result_id) logged for the first
days; on-chain implied fee rate spot-checked on 3 dates.

Usage: nohup .venv/bin/python src/mc_campaign.py > logs/mc_campaign.log 2>&1 &
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import polars as pl
from scipy.stats import norm

sys.path.insert(0, "src")
import consolidate
import fees
import telonex_dl as tdl
from multicoin_bulk import binance_klines


def binance_aggtrades(sym: str, date: str) -> str | None:
    """Tick-level nowcast feed (A/B test: candles cost the brain ~1/3 of its
    edge on BTC — the live bot trades on ticks, so the sim must too).
    Downloaded per day, DELETED by process_day cleanup (too big to keep)."""
    import io
    import urllib.request
    import zipfile
    out = f"data/processed/binance/aggTrades_{sym}/{date}.parquet"
    if os.path.exists(out):
        return out
    url = (f"https://data.binance.vision/data/spot/daily/aggTrades/{sym}/"
           f"{sym}-aggTrades-{date}.zip")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
                raw = z.read(z.namelist()[0])
            break
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(2 ** attempt)
    else:
        return None
    cols = ["agg_id", "price", "qty", "first_id", "last_id", "ts_us",
            "is_buyer_maker", "best_match"]
    df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=cols)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    (df.select(pl.col("ts_us").cast(pl.Int64),
               pl.col("price").cast(pl.Float64))
       .write_parquet(out, compression="zstd"))
    return out


def load_ticks(sym: str, date: str):
    p = binance_aggtrades(sym, date)
    if p is None:
        return None, None
    t = pl.read_parquet(p).sort("ts_us")
    ts = t["ts_us"].to_numpy().astype(np.int64)
    if len(ts) and ts.max() < 2_000_000_000_000:   # ms epoch -> us
        ts = ts * 1000
    return ts, np.log(t["price"].to_numpy().astype(np.float64))

# HYPE excluded (user, 2026-07-09): not on Binance spot -> no 150ms tick feed,
# so it can only run anchor-only (measured negative, like BTC broadcast-only).
COINS = ["eth", "sol", "xrp", "bnb", "doge"]
FAMS = [("5m", 300), ("15m", 900)]
DATES = (["2026-07-06", "2026-07-07"] +
         [(dt.date(2026, 4, 2) + dt.timedelta(days=i)).isoformat()
          for i in range((dt.date(2026, 7, 5) - dt.date(2026, 4, 2)).days + 1)])
FEECHECK_DATES = {"2026-07-06", "2026-04-15", "2026-06-15"}
RESCHECK_DATES = {"2026-07-06", "2026-04-02"}
Z_THR = 1.5
EV_MARGIN = 0.02
BLAT = 150_000
FILL_LAT = 250_000
STAKE = 5.0
PUSH_EVERY = 2


def sh(cmd: str) -> int:
    return subprocess.call(cmd, shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def push(msg: str) -> None:
    sh("git add results/mc reports/mc_campaign_notes.md 2>/dev/null")
    if sh(f'git commit -m "{msg}" >/dev/null 2>&1') != 0:
        return
    for i in range(4):
        if sh("git push -u origin claude/polymarket-btc-strategy-ys9coc") == 0:
            return
        time.sleep(2 ** (i + 1))
    print("PUSH FAILED after retries", flush=True)


def note(line: str) -> None:
    print(line, flush=True)
    os.makedirs("reports", exist_ok=True)
    with open("reports/mc_campaign_notes.md", "a") as f:
        f.write(line + "\n")


def load_klines(sym: str, date: str):
    p = f"data/processed/binance/klines_1s_{sym}/{date}.parquet"
    if not os.path.exists(p):
        return None, None
    k = pl.read_parquet(p).sort("open_time_us")
    ot = k["open_time_us"].to_numpy().astype(np.int64)
    if ot.max() < 2_000_000_000_000:          # ms epoch -> us
        ot = ot * 1000
    bt = ot + 1_000_000                        # close time of each 1s candle
    blog = np.log(k["close"].to_numpy().astype(np.float64))
    return bt, blog


def machine_day(date: str, coin: str, fam: str, dur: int, meta: pl.DataFrame,
                cp: pl.DataFrame, bt, blog) -> list[dict]:
    """Frozen nix1 machine + gate monitor over one coin-family-day."""
    famkey = f"{coin}-{fam}"
    bpath = f"data/processed/daily/{famkey}/bookcurves/{date}.parquet"
    tpath = f"data/processed/daily/{famkey}/trades/{date}.parquet"
    if not os.path.exists(bpath):
        return []
    b = pl.read_parquet(bpath).sort("wts", "local_timestamp_us")
    tr = (pl.read_parquet(tpath).sort("wts", "local_timestamp_us")
          if os.path.exists(tpath) else None)
    ct = cp["timestamp_us"].to_numpy()
    sv = cp["server_timestamp_us"].to_numpy()
    clog = np.log(cp["price"].to_numpy().astype(np.float64))
    bw = b["wts"].to_numpy()
    bts = b["local_timestamp_us"].to_numpy()
    b_buy = b["buy_avgpx_50"].to_numpy().astype(np.float64)
    b_sell = b["sell_avgpx_50"].to_numpy().astype(np.float64)
    bid0 = b["bid_p0"].to_numpy().astype(np.float64)
    ask0 = b["ask_p0"].to_numpy().astype(np.float64)
    asz0 = b["ask_s0"].to_numpy().astype(np.float64)
    bsz0 = b["bid_s0"].to_numpy().astype(np.float64)
    if tr is not None:
        tw = tr["wts"].to_numpy()
        tts = tr["local_timestamp_us"].to_numpy()
        tpx = tr["price"].to_numpy().astype(np.float64)
    rate = fees.params(date, fam)[0]
    toff = dur - 3
    rows = []
    for r_ in meta.iter_rows(named=True):
        w_ = r_["wts"]
        rid = r_["result_id"]
        if rid not in ("0", "1"):
            continue
        up_won = rid == "0"
        row = {"date": date, "coin": coin, "fam": fam, "wts": int(w_),
               "up_won": up_won, "z": None, "fair": None, "ask": None,
               "wask": None, "ev": None, "basis_bp": None, "tob_ask": None,
               "tob_usd": None, "gate": "none", "fill": None, "pnl": None,
               "fill_tape": None, "pnl_tape": None}
        rows.append(row)
        T = (w_ + toff) * 1_000_000
        # book state as-of T+latency (always recorded: gate monitor)
        lo = np.searchsorted(bw, w_, "left")
        hi = np.searchsorted(bw, w_, "right")
        if hi <= lo:
            row["gate"] = "nobook"
            continue
        kk = np.searchsorted(bts[lo:hi], T + FILL_LAT, "right") - 1
        if kk < 0:
            row["gate"] = "nobook"
            continue
        j = lo + kk
        wask = ask0[j] if up_won else (1 - bid0[j])          # winner's best ask
        if np.isfinite(wask):
            row["wask"] = round(float(wask), 4)
        # signal
        i_open = np.searchsorted(ct, w_ * 1_000_000, "left")
        if i_open >= len(ct) or sv[i_open] > T:
            row["gate"] = "nofeed"
            continue
        j0 = np.searchsorted(ct, (w_ - 300) * 1_000_000, "left")
        if i_open - j0 < 30:
            row["gate"] = "nosigma"
            continue
        rets = np.diff(clog[j0:i_open])
        dts = np.diff(ct[j0:i_open]) / 1e6
        sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
        if not (np.isfinite(sig) and sig > 0):
            row["gate"] = "nosigma"
            continue
        kb = np.searchsorted(sv, T, "right") - 1
        if kb < i_open:
            row["gate"] = "nofeed"
            continue
        if bt is not None:
            b1 = np.searchsorted(bt, ct[kb] + BLAT, "right") - 1
            b2 = np.searchsorted(bt, T - BLAT, "right") - 1
            if b1 < 0 or b2 <= b1:
                row["gate"] = "nofeed"
                continue
            delta = clog[kb] + blog[b2] - blog[b1] - clog[i_open]
            row["basis_bp"] = round(float(blog[b2] - clog[kb]) * 1e4, 1)
        else:                                   # HYPE: anchor-only variant
            delta = clog[kb] - clog[i_open]
        z = delta / (sig * math.sqrt(3))
        fair = norm.cdf(abs(z))
        dir_up = z > 0
        row["z"] = round(float(z), 2)
        row["fair"] = round(float(fair), 4)
        ask = b_buy[j] if dir_up else 1 - b_sell[j]
        tob = ask0[j] if dir_up else (1 - bid0[j])
        tsz = asz0[j] if dir_up else bsz0[j]
        if np.isfinite(tob):
            row["tob_ask"] = round(float(tob), 4)
            row["tob_usd"] = round(float(tob * tsz), 2) if np.isfinite(tsz) else None
        if not (np.isfinite(ask) and 0.02 < ask < 0.995):
            row["gate"] = "noask"
            continue
        row["ask"] = round(float(ask), 4)
        ev = fair - ask - rate * ask * (1 - ask)
        row["ev"] = round(float(ev), 4)
        if abs(z) < Z_THR:
            row["gate"] = "z"
            continue
        if ev < EV_MARGIN:
            row["gate"] = "ev"
            continue
        row["gate"] = "pass"
        win = 1.0 if (dir_up == up_won) else 0.0
        sh_ = STAKE / ask
        row["fill"] = round(float(ask), 4)
        row["pnl"] = round(float(sh_ * win - STAKE - sh_ * rate * ask * (1 - ask)), 4)
        if tr is not None:                       # tape-validated variant
            tlo = np.searchsorted(tw, w_, "left")
            thi = np.searchsorted(tw, w_, "right")
            stt = tts[tlo:thi]
            sp = tpx[tlo:thi]
            tok = sp if dir_up else 1 - sp
            m1 = np.searchsorted(stt, T + FILL_LAT, "left")
            m2 = np.searchsorted(stt, T + FILL_LAT + 1_500_000, "right")
            pr = tok[m1:m2]
            okm = pr <= ask + 0.01 if len(pr) else np.array([False])
            if okm.any():
                fillpx = max(ask, float(pr[okm].min()))
                sh2 = STAKE / fillpx
                row["fill_tape"] = round(fillpx, 4)
                row["pnl_tape"] = round(
                    float(sh2 * win - STAKE - sh2 * rate * fillpx * (1 - fillpx)), 4)
    return rows


def rescheck(date: str, coin: str, fam: str, meta: pl.DataFrame, cp: pl.DataFrame) -> None:
    ct = cp["timestamp_us"].to_numpy()
    px = cp["price"].to_numpy().astype(np.float64)
    dur = 300 if fam == "5m" else 900
    n_ok = n = 0
    for r_ in meta.iter_rows(named=True):
        w_, rid = r_["wts"], r_["result_id"]
        if rid not in ("0", "1"):
            continue
        i0 = np.searchsorted(ct, w_ * 1_000_000, "left")
        i1 = np.searchsorted(ct, (w_ + dur) * 1_000_000, "left")
        if i1 >= len(ct) or i0 >= len(ct):
            continue
        pred = "0" if px[i1] >= px[i0] else "1"
        n += 1
        n_ok += pred == rid
    if n:
        note(f"RESCHECK {coin}-{fam} {date}: {n_ok}/{n} = {n_ok / n:.1%}")


def feecheck(date: str, meta_by: dict) -> None:
    for coin in ("eth", "sol"):
        meta = meta_by.get((coin, "5m"))
        if meta is None or meta.is_empty():
            continue
        rs, tasks = [], []
        for r_ in meta.head(3).iter_rows(named=True):
            out = f"data/raw/telonex/fees_tmp/{coin}_{r_['wts']}.parquet"
            tasks.append(tdl.Task(channel="onchain_fills", date=date,
                                  out_path=out, asset_id=r_["asset_id_0"]))
        tdl.run(tasks, concurrency=4)
        for p in glob.glob(f"data/raw/telonex/fees_tmp/{coin}_*.parquet"):
            try:
                f = pl.read_parquet(p)
                if "taker_fee" not in f.columns:   # column exists only Apr28+
                    continue
                f = f.with_columns(
                    pl.col("price").cast(pl.Float64, strict=False),
                    pl.col("amount").cast(pl.Float64, strict=False),
                    pl.col("taker_fee").cast(pl.Float64, strict=False).fill_null(0.0))
                f = f.filter((pl.col("taker_fee") > 0) & (pl.col("price") > 0.03)
                             & (pl.col("price") < 0.97) & (pl.col("amount") > 0))
                if f.is_empty():
                    continue
                r = (f["taker_fee"] /
                     (f["amount"] * f["price"] * (1 - f["price"]))).median()
                if r is not None:
                    rs.append(float(r))
            except Exception:
                pass
        shutil.rmtree("data/raw/telonex/fees_tmp", ignore_errors=True)
        if rs:
            imp = float(np.median(rs))
            reg = fees.params(date, "5m")[0]
            flag = "OK" if abs(imp - reg) < 0.006 else "MISMATCH!"
            note(f"FEECHECK {coin}-5m {date}: implied r={imp:.4f} regime={reg} {flag}")


def process_day(date: str, subs: dict) -> bool:
    out = f"results/mc/{date}.parquet"
    if os.path.exists(out):
        return False
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    tasks = []
    meta_by = {}
    for (coin, fam), df in subs.items():
        sub = df.filter((pl.col("w") >= d0) & (pl.col("w") < d0 + 86400)) \
                .rename({"w": "wts"}).sort("wts")
        meta_by[(coin, fam)] = sub
        for r in sub.iter_rows(named=True):
            for ch in ("book_snapshot_25", "trades"):
                tasks.append(tdl.Task(channel=ch, date=date,
                    out_path=(f"data/raw/telonex/{ch}/{date}/"
                              f"{coin}-updown-{fam}-{r['wts']}_Up.parquet"),
                    asset_id=r["asset_id_0"]))
    for coin in COINS:
        sym = coin + "usd"
        cp_out = f"data/processed/coin_prices/{sym}/{date}.parquet"
        if not os.path.exists(cp_out):
            tasks.append(tdl.Task(channel="crypto_prices", date=date,
                                  out_path=cp_out, asset_id=sym))
    res = tdl.run(tasks, concurrency=10)
    err = [r for r in res if r.status == "error"]
    if err:
        note(f"{date}: {len(err)} download errors, skipping day ({err[0].detail})")
        return False
    consolidate.consolidate_trades(date)
    consolidate.consolidate_books(date, final_only=30)
    for ch in ("book_snapshot_25", "trades"):
        shutil.rmtree(f"data/raw/telonex/{ch}/{date}", ignore_errors=True)
    all_rows = []
    for coin in COINS:
        sym = coin + "usd"
        cpp = f"data/processed/coin_prices/{sym}/{date}.parquet"
        if not os.path.exists(cpp):
            continue
        cp = pl.read_parquet(cpp).sort("timestamp_us")
        if cp.is_empty():
            continue
        sym = (coin + "usdt").upper()
        bt, blog = load_ticks(sym, date)       # tick-level (A/B-validated)
        if bt is None:                         # no 150ms ticks -> skip this
            note(f"{date} {coin}: no aggTrades ticks, coin SKIPPED (no candle fallback)")
            continue
        for fam, dur in FAMS:
            meta = meta_by.get((coin, fam))
            if meta is None or meta.is_empty():
                continue
            all_rows += machine_day(date, coin, fam, dur, meta, cp, bt, blog)
            if date in RESCHECK_DATES:
                rescheck(date, coin, fam, meta, cp)
    if date in FEECHECK_DATES:
        feecheck(date, meta_by)
    os.makedirs("results/mc", exist_ok=True)
    if all_rows:
        pl.DataFrame(all_rows).write_parquet(out, compression="zstd")
    else:
        pl.DataFrame({"date": [date]}).write_parquet(out)
    # cleanup the day's consolidated coin data (results are the durable record)
    for coin in COINS:
        for fam, _ in FAMS:
            for ch in ("bookcurves", "trades", "quotes"):
                p = f"data/processed/daily/{coin}-{fam}/{ch}/{date}.parquet"
                if os.path.exists(p):
                    os.remove(p)
        p = f"data/processed/binance/aggTrades_{(coin + 'usdt').upper()}/{date}.parquet"
        if os.path.exists(p):
            os.remove(p)                      # ~40MB/coin-day: too big to keep
    tr_rows = [r for r in all_rows if r["gate"] == "pass"]
    tape_pnl = sum(r["pnl_tape"] for r in tr_rows if r["pnl_tape"] is not None)
    note(f"{date}: windows {len(all_rows)}, pass {len(tr_rows)}, "
         f"tape pnl ${tape_pnl:+.2f}")
    if date == "2026-07-06":
        eth = [r for r in tr_rows
               if r["coin"] == "eth" and r["fam"] == "5m" and r["pnl_tape"] is not None]
        s = sum(r["pnl_tape"] for r in eth)
        ok = 2 <= len(eth) <= 7 and 2.0 <= s <= 6.5
        note(f"AUDIT eth-5m Jul6: {len(eth)} tape trades ${s:+.2f} "
             f"(benchmark ~4/+$3.97) -> {'PASS' if ok else 'FAIL — INVESTIGATE'}")
    return True


def main() -> None:
    m = pl.read_parquet("data/raw/telonex/polymarket_markets.parquet")
    subs = {}
    for coin in COINS:
        for fam, _ in FAMS:
            subs[(coin, fam)] = (
                m.filter(pl.col("slug").str.contains(rf"^{coin}-updown-{fam}-\d+$")
                         .fill_null(False))
                .with_columns(pl.col("slug").str.extract(r"(\d+)$", 1)
                              .cast(pl.Int64).alias("w")))
    done_since_push = 0
    for date in DATES:
        if process_day(date, subs):
            done_since_push += 1
        if done_since_push >= PUSH_EVERY:
            push(f"mc campaign: through {date}")
            done_since_push = 0
    push("mc campaign: final")
    note("CAMPAIGN DONE")


if __name__ == "__main__":
    main()
