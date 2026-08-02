"""Re-test the nix2 rule on BTC 15m — properly powered this time.

The earlier verdict ("5m yes, 15m no") rested on t=2.45 vs t=0.48 over matched
dates. That was underpowered by construction: 15m has a third of 5m's windows
per day AND the sqrt(duration) law says its edge should be ~1/sqrt(3) = 58% as
large. Those two together predict a t roughly a third of 5m's — which is about
what was seen. A small t was therefore consistent with a REAL but weaker edge,
not with no edge.

We hold 214 days of 15m (2025-10-11 .. 2026-05-12, 20,492 windows) against
only 92 days of 5m, so 15m can be tested with comparable total power.

Rule (identical to bot/live/nix2_live.py, duration-adjusted):
  T0    = open - 0.5s
  g     = ln(close(T0-0.15s) / close(T0-1.15s)) * 1e4      (1s grid)
  sigma = std(1s log rets over prior 300s) * sqrt(DUR) * 1e4
  z     = g / sigma        <- z is the natural edge measure; scaling by
                              sqrt(DUR) is what makes 5m and 15m comparable
  gates : ask in [0.44, 0.4999], |z| in [0.05, 0.40), touch >= stake
  fill  : at the touch, hold to resolution
  fees  : DATE-CORRECT from windows.parquet fee_rate (Rule 3) — this period
          spans the 0 -> 0.0624 -> 0.072 -> 0.07 regime changes

  .venv/bin/python src/nix_15m.py [--family 15m] [--dur 900]
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import statistics

import polars as pl

WIN = "data/processed/windows.parquet"
KL = "data/processed/binance/klines_1s"
ASK_MIN, ASK_MAX = 0.44, 0.4999
Z_MIN, Z_MAX = 0.005, 0.40   # collect wide; the FROZEN 0.05 gate is applied in reporting
STAKE = 10.0


def sigma_bp(px: dict[int, float], t: int, dur: int) -> float | None:
    base = t - 5
    rets, prev = [], px.get(base - 300)
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
    return math.sqrt(v) * math.sqrt(dur) * 1e4


def report(label: str, rows: list[dict]) -> float | None:
    if len(rows) < 20:
        print(f"  {label:<28} n={len(rows):>5}  (too few)")
        return None
    p = [r["pnl"] for r in rows]
    m = statistics.mean(p)
    sd = statistics.stdev(p)
    t = m / (sd / math.sqrt(len(p)))
    wr = sum(1 for r in rows if r["won"]) / len(rows)
    # day-clustered t, the pre-registered basis
    by = {}
    for r in rows:
        by.setdefault(r["date"], []).append(r["pnl"])
    daily = [statistics.mean(v) for v in by.values()]
    dt = (statistics.mean(daily) / (statistics.stdev(daily) / math.sqrt(len(daily)))
          if len(daily) > 1 and statistics.stdev(daily) > 0 else float("nan"))
    print(f"  {label:<28} n={len(rows):>5}  wr {wr:6.2%}  EV ${m:+.3f}  "
          f"t={t:+5.2f}  day-t={dt:+5.2f}  ({len(by)}d)")
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="15m")
    ap.add_argument("--dur", type=int, default=900)
    args = ap.parse_args()

    w = pl.read_parquet(WIN).filter(
        (pl.col("family") == args.family) & pl.col("result_id").is_not_null())
    qdir = f"data/processed/daily/{args.family}/quotes"
    kd = {os.path.basename(p)[:-8] for p in glob.glob(f"{KL}/*.parquet")}
    qd = {os.path.basename(p)[:-8] for p in glob.glob(f"{qdir}/*.parquet")}
    dates = [d for d in sorted(set(w["date"].to_list())) if d in kd and d in qd]
    print(f"=== {args.family} (dur={args.dur}s): {len(dates)} days "
          f"{dates[0]} .. {dates[-1]} ===\n")

    trades = []
    for i, d in enumerate(dates):
        k = pl.read_parquet(f"{KL}/{d}.parquet", columns=["open_time_us", "close"])
        px = dict(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))
        q = pl.read_parquet(f"{qdir}/{d}.parquet")
        # pre-group quotes by window so we scan each file once, not per window
        groups = {wts: sub for (wts,), sub in q.group_by(["wts"])}
        day = w.filter(pl.col("date") == d)
        for wts, res, fee_rate in zip(day["wts"], day["result_id"],
                                      day["fee_rate"]):
            p_now, p_1s = px.get(wts - 1), px.get(wts - 2)
            if not p_now or not p_1s or p_1s <= 0:
                continue
            g = math.log(p_now / p_1s) * 1e4
            if g == 0:
                continue
            sg = sigma_bp(px, wts, args.dur)
            if not sg or sg <= 0:
                continue
            z = g / sg
            if not (Z_MIN <= abs(z) < Z_MAX):
                continue
            sub = groups.get(wts)
            if sub is None:
                continue
            sub = sub.filter(pl.col("local_timestamp_us") <= wts * 1_000_000 - 500_000)
            if sub.height == 0:
                continue
            r = sub.tail(1)
            side_up = g > 0
            if side_up:
                ask, size = r["ask_price"][0], r["ask_size"][0]
            else:                       # DOWN ask = complement of UP bid
                bp = r["bid_price"][0]
                if bp is None:
                    continue
                ask, size = 1.0 - bp, r["bid_size"][0]
            if ask is None or size is None or not (ASK_MIN <= ask <= ASK_MAX):
                continue
            if ask * size < STAKE:
                continue
            won = (side_up == (int(res) == 0))
            sh = STAKE / ask
            fee = (fee_rate if fee_rate is not None else 0.07)
            pnl = sh * (1.0 if won else 0.0) - STAKE - fee * ask * (1 - ask) * sh
            trades.append({"date": d, "pnl": pnl, "won": won, "z": abs(z),
                           "ask": ask, "touch": ask * size})
        if (i + 1) % 40 == 0:
            print(f"  ...{i+1}/{len(dates)} days, {len(trades)} trades", flush=True)

    if not trades:
        print("no trades reconstructed")
        return
    ds = sorted(set(t["date"] for t in trades))
    print(f"\nreconstructed {len(trades)} trades over {len(ds)} days "
          f"({len(trades)/len(ds):.1f}/day)\n")
    print("=== full sample ===")
    trades_frozen = [t for t in trades if t["z"] >= 0.05]
    report("ALL (frozen |z|>=0.05)", trades_frozen)
    report("ALL (wide |z|>=0.005)", trades)
    print("\n=== train / val (chronological halves) ===")
    h = len(ds) // 2
    tr, va = set(ds[:h]), set(ds[h:])
    report(f"TRAIN {ds[0]}..{ds[h-1]}", [t for t in trades_frozen if t["date"] in tr])
    report(f"VAL   {ds[h]}..{ds[-1]}", [t for t in trades_frozen if t["date"] in va])
    import pickle
    pickle.dump(trades, open("/tmp/nix15m_trades.pkl", "wb"))
    print("\n=== by quarter (is it stable, or one lucky stretch?) ===")
    for q in sorted(set(d[:7] for d in ds)):
        report(q, [t for t in trades_frozen if t["date"].startswith(q)])
    sweep()


if __name__ == "__main__":
    main()


def sweep():
    """Does a RESCALED z-band find an edge on 15m? Picked on TRAIN, scored on
    VAL, so the answer is a pre-registration candidate not a sweep argmax."""
    import sys
    import pickle
    trades = pickle.load(open("/tmp/nix15m_trades.pkl", "rb"))
    ds = sorted(set(t["date"] for t in trades))
    h = len(ds) // 2
    tr, va = set(ds[:h]), set(ds[h:])
    print("\n=== RESCALED z-band: pick on TRAIN, score on VAL ===")
    print("  (|z| floor scaled down: 15m needs a bigger move for the same z)")
    best, bev = None, -9e9
    for lo in (0.010, 0.020, 0.029, 0.040, 0.050):
        rows = [t for t in trades if t["date"] in tr and lo <= t["z"] < 0.40]
        ev = report(f"TRAIN |z|>={lo:.3f}", rows)
        if ev is not None and ev > bev:
            bev, best = ev, lo
    print(f"\n  -> TRAIN picks |z| >= {best:.3f}")
    b = report("VAL  frozen |z|>=0.050",
               [t for t in trades if t["date"] in va and 0.05 <= t["z"] < 0.40])
    p = report(f"VAL  picked |z|>={best:.3f}",
               [t for t in trades if t["date"] in va and best <= t["z"] < 0.40])
    if b is not None and p is not None:
        print(f"\n  -> {'HOLDS' if p > b else 'FAILS'}: picked ${p:+.3f} vs frozen ${b:+.3f}")
