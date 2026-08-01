"""Does a touch-size CEILING improve nix2? (the S2 cross-repo hypothesis)

nix2 has a floor on resting ask size (min_touch_usd) and NO ceiling. The S2
research repo measured the opposite end: large resting asks are INFORMED
(-2.4c/share in the >=250-share bucket) and it refuses them outright
(skip_ask_above=500). paper2's own forward record points the same way -- its
q_imb<-0.05 gate deliberately seeks ask-heavy books and returned a 50.0% win
rate vs paper1's 53.8%.

This reconstructs nix2's actual rule over history and asks whether capping
touch size would have helped, with an honest train/val split so the answer
is a pre-registration candidate rather than a sweep argmax.

Rule reconstruction (matches bot/live/nix2_live.py):
  T0    = wts - 0.5s  (decision), signal from Binance 1s klines
  g     = ln(close(T0-0.15s) / close(T0-1.15s)) * 1e4   -> on the 1s grid,
          close(wts-1) / close(wts-2)
  sigma = std(1s log returns over prior 300s) * sqrt(300) * 1e4
  z     = g / sigma ;  side = up if g>0 else down
  gates : ask in [0.44, 0.4999],  |z| in [0.05, 0.40),  touch >= stake
  fill  : at the touch ; hold to resolution ; fee 0.07*p*(1-p) per share

Quote convention: the tape carries the UP token's book, so the DOWN side's
ask is the complement of the UP bid (same resting order, other side).

  .venv/bin/python src/nix_touchsize.py
"""
from __future__ import annotations

import glob
import math
import os

import polars as pl

WIN = "data/processed/windows.parquet"
KL = "data/processed/binance/klines_1s"
QU = "data/processed/daily/5m/quotes"
ASK_MIN, ASK_MAX = 0.44, 0.4999
Z_MIN, Z_MAX = 0.05, 0.40
STAKE, FEE = 10.0, 0.07


def sigma_bp(px: dict[int, float], t: int) -> float | None:
    """std of 1s log returns over the 300s before t-5, * sqrt(300) * 1e4."""
    base = t - 5
    rets = []
    prev = px.get(base - 300)
    for s in range(base - 299, base + 1):
        cur = px.get(s)
        if cur and prev and prev > 0:
            rets.append(math.log(cur / prev))
        if cur:
            prev = cur
    if len(rets) < 30:
        return None
    m = sum(rets) / len(rets)
    v = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(v) * math.sqrt(300) * 1e4


def main() -> None:
    w = pl.read_parquet(WIN).filter(
        (pl.col("family") == "5m") & pl.col("result_id").is_not_null())
    kd = {os.path.basename(p)[:-8] for p in glob.glob(f"{KL}/*.parquet")}
    qd = {os.path.basename(p)[:-8] for p in glob.glob(f"{QU}/*.parquet")}
    dates = [d for d in sorted(set(w["date"].to_list())) if d in kd and d in qd]
    print(f"{len(dates)} days with both klines and quotes "
          f"({dates[0]} .. {dates[-1]})")

    trades = []
    for i, d in enumerate(dates):
        k = pl.read_parquet(f"{KL}/{d}.parquet", columns=["open_time_us", "close"])
        px = dict(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))
        q = pl.read_parquet(f"{QU}/{d}.parquet")
        day = w.filter(pl.col("date") == d)
        for wts, res in zip(day["wts"], day["result_id"]):
            T0 = wts * 1_000_000 - 500_000
            p_now, p_1s = px.get(wts - 1), px.get(wts - 2)
            if not p_now or not p_1s or p_1s <= 0:
                continue
            g = math.log(p_now / p_1s) * 1e4
            if g == 0:
                continue
            sg = sigma_bp(px, wts)
            if not sg or sg <= 0:
                continue
            z = g / sg
            if not (Z_MIN <= abs(z) < Z_MAX):
                continue
            side_up = g > 0
            # last quote strictly available at decision time
            sub = q.filter((pl.col("wts") == wts)
                           & (pl.col("local_timestamp_us") <= T0))
            if sub.height == 0:
                continue
            r = sub.tail(1)
            bp, bs = r["bid_price"][0], r["bid_size"][0]
            ap, asz = r["ask_price"][0], r["ask_size"][0]
            if side_up:
                ask, size = ap, asz
            else:                       # DOWN ask = complement of UP bid
                if bp is None:
                    continue
                ask, size = 1.0 - bp, bs
            if ask is None or size is None:
                continue
            if not (ASK_MIN <= ask <= ASK_MAX):
                continue
            touch = ask * size
            if touch < STAKE:
                continue
            won = (side_up == (int(res) == 0))
            sh = STAKE / ask
            pnl = sh * (1.0 if won else 0.0) - STAKE - FEE * ask * (1 - ask) * sh
            trades.append({"date": d, "pnl": pnl, "won": won,
                           "touch": touch, "ask": ask, "z": abs(z)})
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(dates)} days, {len(trades)} trades", flush=True)

    if not trades:
        print("no trades reconstructed")
        return
    n = len(trades)
    ds = sorted(set(t["date"] for t in trades))
    half = len(ds) // 2
    tr, va = set(ds[:half]), set(ds[half:])
    print(f"\nreconstructed {n} trades over {len(ds)} days "
          f"({n/len(ds):.1f}/day) -- live paper1 runs ~5.0/day")

    def rep(label, rows):
        if len(rows) < 20:
            print(f"  {label:<26} n={len(rows):>4}  (too few)")
            return None
        p = [r["pnl"] for r in rows]
        m = sum(p) / len(p)
        sd = math.sqrt(sum((x - m) ** 2 for x in p) / (len(p) - 1))
        t = m / (sd / math.sqrt(len(p)))
        wr = sum(1 for r in rows if r["won"]) / len(rows)
        print(f"  {label:<26} n={len(rows):>4}  wr {wr:6.2%}  "
              f"EV ${m:+.3f}  t={t:+5.2f}")
        return m

    print("\n=== baseline (no ceiling), by split ===")
    rep("TRAIN all", [t for t in trades if t["date"] in tr])
    rep("VAL   all", [t for t in trades if t["date"] in va])

    print("\n=== TRAIN: does a touch ceiling help? ===")
    best, best_ev = None, -9e9
    for cap in (25, 50, 100, 200, 400, 800, 1e9):
        ev = rep(f"TRAIN touch<=${cap:,.0f}",
                 [t for t in trades if t["date"] in tr and t["touch"] <= cap])
        if ev is not None and cap < 1e9 and ev > best_ev:
            best_ev, best = ev, cap
    print(f"\n  -> TRAIN picks ceiling ${best:,.0f}")

    print("\n=== VAL: does the TRAIN pick hold on unseen days? ===")
    base = rep("VAL no ceiling", [t for t in trades if t["date"] in va])
    pick = rep(f"VAL touch<=${best:,.0f}",
               [t for t in trades if t["date"] in va and t["touch"] <= best])
    if base is not None and pick is not None:
        print(f"\n  -> {'HOLDS' if pick > base else 'FAILS'}: "
              f"ceiling EV ${pick:+.3f} vs no-ceiling ${base:+.3f}")

    # cache the reconstruction so follow-up analysis is instant
    pl.DataFrame(trades).write_parquet("data/processed/nix2_recon.parquet")
    print("\n=== TRAIN: does a touch FLOOR help? (Q1 is the only -EV bucket) ===")
    bf, bf_ev = None, -9e9
    for flo in (10, 20, 25, 30, 40, 60):
        ev = rep(f"TRAIN touch>=${flo}",
                 [t for t in trades if t["date"] in tr and t["touch"] >= flo])
        if ev is not None and ev > bf_ev:
            bf_ev, bf = ev, flo
    print(f"\n  -> TRAIN picks floor ${bf}")
    print("\n=== VAL: does the TRAIN floor hold on unseen days? ===")
    b2 = rep("VAL floor $10 (current)",
             [t for t in trades if t["date"] in va and t["touch"] >= 10])
    p2 = rep(f"VAL floor ${bf}",
             [t for t in trades if t["date"] in va and t["touch"] >= bf])
    if b2 is not None and p2 is not None:
        print(f"\n  -> {'HOLDS' if p2 > b2 else 'FAILS'}: "
              f"floor ${bf} EV ${p2:+.3f} vs current ${b2:+.3f}")

    print("\n=== touch-size quartiles (all data, descriptive) ===")
    s = sorted(trades, key=lambda t: t["touch"])
    qn = len(s) // 4
    for i in range(4):
        c = s[i*qn:(i+1)*qn] if i < 3 else s[3*qn:]
        if c:
            rep(f"Q{i+1} ${c[0]['touch']:.0f}-${c[-1]['touch']:.0f}", c)


if __name__ == "__main__":
    main()
