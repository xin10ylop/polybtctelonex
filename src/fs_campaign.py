"""NIX4 JOB C — streaming per-window x per-offset FEATURE STORE harvester.

For every coin (btc/eth/sol/xrp/bnb/doge) x family (5m/15m) x window x decision
offset, samples: PM book state (BBO + $5/$50/$200 walk both sides + 5c depth),
PM tape (signed flow, vwap, prints, and the post-offset max/min traded price
for maker-exit sims), Binance tick features (multi-horizon returns, realized
vol) for the coin AND for BTC (cross-coin lead), Chainlink anchor state
(delta-from-open, basis vs Binance, broadcast delay, sigma, generalized z),
and the concurrent other-timeframe market's book (cross-timeframe features).

One parquet per coin-family-day in results/fs/, committed+pushed daily
(rollback-proof streaming, same pattern as mc_campaign). Raw data deleted
after each day. Memory-safe: each raw book parquet is read once and only the
~25 requested decision-time rows are kept.

INTEGRITY: BTC days 2026-05-13..2026-07-05 are the spent HOLDOUT — never
harvested (Rule 2). Coins have no holdout constraint. Splits pre-registered
in reports/nix4_prereg.md: TRAIN Apr2-May31 / VAL Jun / FRESH Jul 6+.

Usage: nohup .venv/bin/python src/fs_campaign.py > logs/fs_campaign.log 2>&1 &
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

sys.path.insert(0, "src")
import telonex_dl as tdl
from consolidate import _walk_curves
from mc_campaign import binance_aggtrades, load_ticks

COINS = ["btc", "eth", "sol", "xrp", "bnb", "doge"]
FAMS = {"5m": 300, "15m": 900}
OFFS = {
    "5m": [-60, -30, -10, -5, -3, -1, 1, 3, 5, 10, 30, 60, 120, 180, 240,
           270, 285, 290, 295, 297, 299],
    "15m": [-60, -30, -10, -5, -3, -1, 1, 3, 5, 10, 30, 60, 120, 300, 600,
            750, 840, 870, 885, 890, 895, 897, 899],
}
D0, D1 = dt.date(2026, 4, 2), dt.date(2026, 7, 9)
DATES = [(D0 + dt.timedelta(days=i)).isoformat()
         for i in range((D1 - D0).days + 1)]
BTC_HOLDOUT = ("2026-05-13", "2026-07-05")   # never harvested for btc
LAT = 250_000       # fill/book latency us
BLAT = 150_000      # binance feed latency us
NOTIONALS = (5.0, 50.0, 200.0)
BOOK_COLS = (["local_timestamp_us"]
             + [f"{s}_{k}_{i}" for s in ("bid", "ask")
                for k in ("price", "size") for i in range(25)])


def sh(cmd: str) -> int:
    return subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)


def push(msg: str) -> None:
    sh("git add results/fs reports/fs_campaign_notes.md 2>/dev/null")
    if sh(f'git commit -m "{msg}" >/dev/null 2>&1') != 0:
        return
    for i in range(4):
        if sh("git push -u origin HEAD") == 0:
            return
        time.sleep(2 ** (i + 1))
    print("PUSH FAILED", flush=True)


def note(line: str) -> None:
    print(line, flush=True)
    os.makedirs("reports", exist_ok=True)
    with open("reports/fs_campaign_notes.md", "a") as f:
        f.write(line + "\n")


class BookSet:
    """Sampled book state of one coin-family-day: for each market, ONLY the
    rows nearest the requested decision timestamps are kept in memory."""

    def __init__(self, coin: str, fam: str, date: str,
                 queries: dict[int, np.ndarray]):
        self.samples: dict[int, tuple] = {}
        bp = [f"bid_price_{i}" for i in range(25)]
        bs = [f"bid_size_{i}" for i in range(25)]
        ap = [f"ask_price_{i}" for i in range(25)]
        asz = [f"ask_size_{i}" for i in range(25)]
        for w, ts in queries.items():
            p = (f"data/raw/telonex/book_snapshot_25/{date}/"
                 f"{coin}-updown-{fam}-{w}_Up.parquet")
            if not os.path.exists(p):
                continue
            try:
                df = pl.read_parquet(p, columns=BOOK_COLS).sort("local_timestamp_us")
            except Exception:
                continue
            if df.is_empty():
                continue
            lts = df["local_timestamp_us"].to_numpy()
            ts = np.sort(np.unique(ts))
            idx = np.searchsorted(lts, ts + LAT, "right") - 1
            ok = idx >= 0
            idxc = np.clip(idx, 0, len(lts) - 1)
            sub = df[idxc.tolist()]
            P_a = sub.select(ap).to_numpy().astype(np.float64)
            S_a = sub.select(asz).to_numpy().astype(np.float64)
            P_b = sub.select(bp).to_numpy().astype(np.float64)
            S_b = sub.select(bs).to_numpy().astype(np.float64)
            buy = _walk_curves(P_a, S_a, NOTIONALS)
            sell = _walk_curves(P_b, S_b, NOTIONALS)
            cols = {
                "bid": np.where(ok, P_b[:, 0], np.nan),
                "ask": np.where(ok, P_a[:, 0], np.nan),
                "bsz": np.where(ok, S_b[:, 0], np.nan),
                "asz": np.where(ok, S_a[:, 0], np.nan),
                "age_ms": np.where(ok, (ts + LAT - lts[idxc]) / 1000.0, np.nan),
                "bdep5": np.where(ok, np.nansum(
                    np.where(P_b >= P_b[:, [0]] - 0.05, S_b, 0), axis=1), np.nan),
                "adep5": np.where(ok, np.nansum(
                    np.where(P_a <= P_a[:, [0]] + 0.05, S_a, 0), axis=1), np.nan),
            }
            for N in NOTIONALS:
                cols[f"b{int(N)}"] = np.where(ok, buy[N][0], np.nan)
                cols[f"s{int(N)}"] = np.where(ok, sell[N][0], np.nan)
            self.samples[w] = (ts, cols)

    def get(self, w: int, ts_arr: np.ndarray) -> dict | None:
        if w not in self.samples:
            return None
        ts, cols = self.samples[w]
        pos = np.searchsorted(ts, ts_arr)
        pos = np.clip(pos, 0, len(ts) - 1)
        good = ts[pos] == ts_arr
        out = {}
        for k, v in cols.items():
            out[k] = np.where(good, v[pos], np.nan)
        return out


class TapeSet:
    def __init__(self, coin: str, fam: str, date: str):
        self.coin, self.fam, self.date = coin, fam, date

    def sample(self, w: int, ts: np.ndarray, close_us: int) -> dict:
        n = len(ts)
        cols = {k: np.full(n, np.nan) for k in
                ("last_px", "vwap", "npr30", "sf10", "sf30", "sf60",
                 "max_after", "min_after")}
        p = (f"data/raw/telonex/trades/{self.date}/"
             f"{self.coin}-updown-{self.fam}-{w}_Up.parquet")
        if not os.path.exists(p):
            return cols
        try:
            df = pl.read_parquet(p, columns=["local_timestamp_us", "price",
                                             "size", "side"]) \
                   .sort("local_timestamp_us")
        except Exception:
            return cols
        if df.is_empty():
            return cols
        lts = df["local_timestamp_us"].to_numpy()
        px = df["price"].to_numpy().astype(np.float64)
        sz = df["size"].to_numpy().astype(np.float64)
        sgn = np.where(df["side"].cast(pl.String).to_numpy() == "buy", 1.0, -1.0)
        notion = px * sz
        cum_n = np.concatenate([[0.0], np.cumsum(notion)])
        cum_s = np.concatenate([[0.0], np.cumsum(sz)])
        cum_f = np.concatenate([[0.0], np.cumsum(sgn * notion)])
        iend = int(np.searchsorted(lts, close_us, "right"))
        for k, t in enumerate(ts):
            i = int(np.searchsorted(lts, t + LAT, "right"))
            if i > 0:
                cols["last_px"][k] = px[i - 1]
                if cum_s[i] > 0:
                    cols["vwap"][k] = cum_n[i] / cum_s[i]
            for hz, key in ((10, "sf10"), (30, "sf30"), (60, "sf60")):
                j = int(np.searchsorted(lts, t + LAT - hz * 1_000_000, "left"))
                cols[key][k] = cum_f[i] - cum_f[j]
            j30 = int(np.searchsorted(lts, t + LAT - 30 * 1_000_000, "left"))
            cols["npr30"][k] = i - j30
            if iend > i:
                cols["max_after"][k] = px[i:iend].max()
                cols["min_after"][k] = px[i:iend].min()
        return cols


class BinanceDay:
    """tick returns via searchsorted; realized vol via per-second series."""

    def __init__(self, bts: np.ndarray, blog: np.ndarray, d0: int):
        self.bts, self.blog = bts, blog
        sec = (np.arange(d0 - 3700, d0 + 86400 + 2) * 1_000_000)
        idx = np.searchsorted(bts, sec, "right") - 1
        ok = idx >= 0
        ps = np.where(ok, blog[np.clip(idx, 0, len(blog) - 1)], np.nan)
        self.sec0 = d0 - 3700
        d = np.diff(ps)
        d = np.nan_to_num(d, nan=0.0)
        self.cumsq = np.concatenate([[0.0], np.cumsum(d * d)])

    def feats(self, ts_arr: np.ndarray, prefix: str) -> dict:
        out = {}
        idx = np.searchsorted(self.bts, ts_arr - BLAT, "right") - 1
        ok = idx >= 0
        now = np.where(ok, self.blog[np.clip(idx, 0, len(self.blog) - 1)], np.nan)
        for hz in (1, 5, 15, 60, 300, 900):
            j = np.searchsorted(self.bts, ts_arr - BLAT - hz * 1_000_000,
                                "right") - 1
            ok2 = ok & (j >= 0)
            out[f"{prefix}r{hz}"] = np.where(
                ok2, now - self.blog[np.clip(j, 0, len(self.blog) - 1)], np.nan)
        s = (ts_arr // 1_000_000).astype(np.int64) - self.sec0
        s = np.clip(s, 1, len(self.cumsq) - 1)
        for hz in (60, 300):
            s0 = np.clip(s - hz, 0, len(self.cumsq) - 1)
            var = (self.cumsq[s] - self.cumsq[s0]) / hz
            out[f"{prefix}rv{hz}"] = np.sqrt(np.maximum(var, 0.0))
        return out


def chainlink_feats(w: int, dur: int, ts_arr, ct, sv, clog, bts, blog) -> dict:
    n = len(ts_arr)
    out = {k: np.full(n, np.nan) for k in
           ("cl_do", "cl_r60", "basis_bp", "cl_delay", "sigma", "z")}
    i_open = np.searchsorted(ct, w * 1_000_000, "left")
    open_ok = i_open < len(ct)
    for k, T in enumerate(ts_arr):
        kb = int(np.searchsorted(sv, T, "right")) - 1
        if kb < 0:
            continue
        out["cl_delay"][k] = (T - ct[kb]) / 1e6
        j60 = int(np.searchsorted(ct, ct[kb] - 60_000_000, "left"))
        if j60 <= kb:
            out["cl_r60"][k] = clog[kb] - clog[j60]
        j0 = int(np.searchsorted(ct, ct[kb] - 300_000_000, "left"))
        if kb - j0 >= 30:
            rets = np.diff(clog[j0:kb + 1])
            dts = np.diff(ct[j0:kb + 1]) / 1e6
            sig = np.std(rets / np.sqrt(np.maximum(dts, 1e-3)))
            if np.isfinite(sig) and sig > 0:
                out["sigma"][k] = sig
        b2 = -1
        if bts is not None:
            b1 = int(np.searchsorted(bts, ct[kb] + BLAT, "right")) - 1
            b2 = int(np.searchsorted(bts, T - BLAT, "right")) - 1
            if b1 >= 0 and b2 > b1:
                out["basis_bp"][k] = (blog[b2] - clog[kb]) * 1e4
        if open_ok and T >= (w * 1_000_000) and sv[i_open] <= T:
            nowcast = clog[kb]
            if bts is not None and b2 >= 0:
                b1 = int(np.searchsorted(bts, ct[kb] + BLAT, "right")) - 1
                if b1 >= 0 and b2 > b1:
                    nowcast = clog[kb] + blog[b2] - blog[b1]
            delta = nowcast - clog[i_open]
            out["cl_do"][k] = delta
            rem = max(dur - (T / 1e6 - w), 0.5)
            if np.isfinite(out["sigma"][k]) and out["sigma"][k] > 0:
                out["z"][k] = delta / (out["sigma"][k] * math.sqrt(rem))
    return out


def process_day(date: str, subs: dict) -> bool:
    done_marker = f"results/fs/.done_{date}"
    if os.path.exists(done_marker):
        return False
    btc_skip = BTC_HOLDOUT[0] <= date <= BTC_HOLDOUT[1]
    coins = [c for c in COINS if not (c == "btc" and btc_skip)]
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    tasks, meta_by = [], {}
    for coin in coins:
        for fam in FAMS:
            sub = subs[(coin, fam)].filter(
                (pl.col("w") >= d0) & (pl.col("w") < d0 + 86400)) \
                .rename({"w": "wts"}).sort("wts")
            meta_by[(coin, fam)] = sub
            for r in sub.iter_rows(named=True):
                for ch in ("book_snapshot_25", "trades"):
                    tasks.append(tdl.Task(channel=ch, date=date,
                        out_path=(f"data/raw/telonex/{ch}/{date}/"
                                  f"{coin}-updown-{fam}-{r['wts']}_Up.parquet"),
                        asset_id=r["asset_id_0"]))
        cp_out = f"data/processed/coin_prices/{coin}usd/{date}.parquet"
        if not os.path.exists(cp_out):
            tasks.append(tdl.Task(channel="crypto_prices", date=date,
                                  out_path=cp_out, asset_id=coin + "usd"))
    res = tdl.run(tasks, concurrency=10)
    err = [r for r in res if r.status == "error"]
    if err:
        note(f"FS {date}: {len(err)} download errors, skipping ({err[0].detail})")
        return False
    ticks = {c: load_ticks((c + "usdt").upper(), date) for c in coins}
    btc_bt, btc_blog = ticks.get("btc", (None, None))
    if btc_bt is None:
        btc_bt, btc_blog = load_ticks("BTCUSDT", date)
    os.makedirs("results/fs", exist_ok=True)
    for coin in coins:
        cpp = f"data/processed/coin_prices/{coin}usd/{date}.parquet"
        cp = pl.read_parquet(cpp).sort("timestamp_us") if os.path.exists(cpp) else None
        if cp is None or cp.is_empty():
            note(f"FS {date} {coin}: no chainlink feed, skipped")
            continue
        ct = cp["timestamp_us"].to_numpy()
        sv = cp["server_timestamp_us"].to_numpy()
        clog = np.log(cp["price"].to_numpy().astype(np.float64))
        bt, blog = ticks.get(coin, (None, None))
        if bt is None:
            note(f"FS {date} {coin}: no binance ticks, skipped")
            continue
        bin_own = BinanceDay(bt, blog, d0)
        bin_btc = (BinanceDay(btc_bt, btc_blog, d0)
                   if (coin != "btc" and btc_bt is not None) else None)
        # ---- build query map: own offsets + cross-fam sample times ----
        queries: dict[str, dict[int, list]] = {f: {} for f in FAMS}
        for fam, dur in FAMS.items():
            meta = meta_by.get((coin, fam))
            if meta is None or meta.is_empty():
                continue
            offs = np.array(OFFS[fam])
            other = "15m" if fam == "5m" else "5m"
            odur = FAMS[other]
            for r in meta.iter_rows(named=True):
                w = r["wts"]
                ts_arr = (w + offs) * 1_000_000
                queries[fam].setdefault(w, []).extend(ts_arr.tolist())
                for T in ts_arr:
                    ow = int((T // 1_000_000) // odur * odur)
                    queries[other].setdefault(ow, []).append(int(T))
        books = {f: BookSet(coin, f, date,
                            {w: np.array(v) for w, v in queries[f].items()})
                 for f in FAMS}
        tapes = {f: TapeSet(coin, f, date) for f in FAMS}
        for fam, dur in FAMS.items():
            meta = meta_by.get((coin, fam))
            if meta is None or meta.is_empty():
                continue
            outcome = {r["wts"]: r["result_id"] for r in meta.iter_rows(named=True)}
            offs = np.array(OFFS[fam])
            other = "15m" if fam == "5m" else "5m"
            odur = FAMS[other]
            rows = []
            for r in meta.iter_rows(named=True):
                w, rid = r["wts"], r["result_id"]
                if rid not in ("0", "1"):
                    continue
                ts_arr = (w + offs) * 1_000_000
                bk = books[fam].get(w, ts_arr)
                if bk is None:
                    continue
                tp = tapes[fam].sample(w, ts_arr, (w + dur) * 1_000_000)
                bf = bin_own.feats(ts_arr, "b_")
                xf = bin_btc.feats(ts_arr, "x_") if bin_btc is not None else {}
                cl = chainlink_feats(w, dur, ts_arr, ct, sv, clog, bt, blog)
                xtf_bid = np.full(len(offs), np.nan)
                xtf_ask = np.full(len(offs), np.nan)
                xtf_trem = np.full(len(offs), np.nan)
                for k, T in enumerate(ts_arr):
                    ow = int((T // 1_000_000) // odur * odur)
                    ob = books[other].get(ow, np.array([T]))
                    if ob is not None:
                        xtf_bid[k] = ob["bid"][0]
                        xtf_ask[k] = ob["ask"][0]
                        xtf_trem[k] = ow + odur - T / 1_000_000
                prev = outcome.get(w - dur)
                for k in range(len(offs)):
                    row = {"date": date, "coin": coin, "fam": fam, "wts": w,
                           "toff": int(offs[k]), "up_won": rid == "0",
                           "prev_up": (prev == "0") if prev in ("0", "1") else None,
                           "hour": (w % 86400) // 3600,
                           "xtf_bid": xtf_bid[k], "xtf_ask": xtf_ask[k],
                           "xtf_trem": xtf_trem[k]}
                    for src in (bk, tp, bf, xf, cl):
                        for kk, vv in src.items():
                            row[kk] = (float(vv[k])
                                       if np.isfinite(vv[k]) else None)
                    rows.append(row)
            if rows:
                out = f"results/fs/{coin}-{fam}/{date}.parquet"
                os.makedirs(os.path.dirname(out), exist_ok=True)
                df = pl.DataFrame(rows, infer_schema_length=None)
                df = df.with_columns([pl.col(c).cast(pl.Float32)
                                      for c in df.columns
                                      if df[c].dtype == pl.Float64])
                df.write_parquet(out, compression="zstd")
        del books, tapes
    for ch in ("book_snapshot_25", "trades"):
        shutil.rmtree(f"data/raw/telonex/{ch}/{date}", ignore_errors=True)
    for coin in coins:
        p = f"data/processed/binance/aggTrades_{(coin+'usdt').upper()}/{date}.parquet"
        if os.path.exists(p):
            os.remove(p)
    open(done_marker, "w").write("done\n")
    fams_out = glob.glob(f"results/fs/*/{date}.parquet")
    nrow = sum(pl.read_parquet(f).height for f in fams_out)
    note(f"FS {date}: {nrow} rows across {len(fams_out)} coin-fams")
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
    for date in DATES:
        if process_day(date, subs):
            push(f"fs harvest: {date}")
    push("fs harvest: final")
    note("FS CAMPAIGN DONE")


if __name__ == "__main__":
    main()
