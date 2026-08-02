"""Does the nix2 mechanism exist on Kalshi 15m — and is it BIGGER?

Kalshi settles on CF Benchmarks BRTI, and the contract rules use the SIMPLE
AVERAGE OF THE SIXTY SECONDS before each endpoint. A 60s trailing average lags
spot by ~30s on average (the centroid of the averaging window), so:

    K = mean(S over [T-60, T]) ~ S(T-30)

At the open T you therefore already hold a ~30-second head start over the
strike, versus Polymarket/Chainlink's ~1 second. Naively that is a MUCH larger
version of the same edge, not the absence of one:

    z = g / (sigma * sqrt(duration))
    Polymarket 5m : g = 1s move,  duration 300s
    Kalshi 15m    : g ~ 30s move, duration ~870s
    ratio ~ sqrt(30)/sqrt(2.9) ~ 3.2x larger z for the same volatility

That is a prediction, so test it. Ground truth is exact: the settlement index
file carries the actual BRTI value at every 15m boundary, which is both the
strike of the window that opens and the settlement of the window that closes.

Signal (uses only data available AT the open, no look-ahead):
    g_bp = 1e4 * ln( Binance_spot(T) / BRTI(T) )
    side = up if g > 0
Outcome:
    up_won = BRTI(T+900) > BRTI(T)

  .venv/bin/python src/kalshi_probe.py [--coin BTC]
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import statistics

import polars as pl

KL = "data/processed/binance/klines_1s"
DUR = 900


def load_brti(coin: str) -> dict[int, float]:
    fs = sorted(glob.glob(f"data/kalshi/{coin}_settlement_index_*.parquet"))
    d = pl.concat([pl.read_parquet(f) for f in fs])
    d = d.with_columns(pl.col("price").cast(pl.Float64),
                       (pl.col("timestamp_us") // 1_000_000).alias("ts"))
    return dict(zip(d["ts"].to_list(), d["price"].to_list()))


def sigma_bp(px: dict[int, float], t: int) -> float | None:
    rets, prev = [], px.get(t - 305)
    for s in range(t - 304, t - 4):
        cur = px.get(s)
        if cur and prev and prev > 0:
            rets.append(math.log(cur / prev))
        if cur:
            prev = cur
    if len(rets) < 30:
        return None
    m = sum(rets) / len(rets)
    v = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(v) * math.sqrt(DUR) * 1e4


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (float("nan"),) * 2
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coin", default="BTC")
    args = ap.parse_args()

    brti = load_brti(args.coin)
    kd = sorted(os.path.basename(p)[:-8] for p in glob.glob(f"{KL}/*.parquet"))
    px: dict[int, float] = {}
    for d in kd:
        if not ("2026-05" <= d <= "2026-07"):
            continue
        k = pl.read_parquet(f"{KL}/{d}.parquet", columns=["open_time_us", "close"])
        px.update(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))
    print(f"{args.coin}: {len(brti):,} BRTI boundaries, "
          f"{len(px):,} spot seconds loaded")
    if args.coin != "BTC":
        print("  NOTE: local klines are BTCUSDT. For ETH this compares the wrong\n"
              "  asset and the result is meaningless — reported only as a control.")

    rows = []
    for T, K in brti.items():
        settle = brti.get(T + DUR)
        s = px.get(T)
        if settle is None or s is None or not K or K <= 0:
            continue
        g = 1e4 * math.log(s / K)
        if g == 0:
            continue
        sg = sigma_bp(px, T)
        if not sg or sg <= 0:
            continue
        rows.append({"T": T, "g": g, "z": g / sg,
                     "up": settle > K,
                     "date": __import__("datetime").datetime.utcfromtimestamp(T)
                             .strftime("%Y-%m-%d")})
    if not rows:
        print("no overlapping windows")
        return
    n = len(rows)
    days = len(set(r["date"] for r in rows))
    print(f"{n:,} windows with both BRTI and spot, over {days} days\n")

    hits = sum(1 for r in rows if (r["g"] > 0) == r["up"])
    lo, hi = wilson(hits, n)
    se = math.sqrt(0.25 / n)
    print("=== does spot-vs-strike at the OPEN predict the outcome? ===")
    print(f"  side = sign( ln(spot(T)/BRTI(T)) )")
    print(f"  hit rate {hits/n:.3%}  [{lo:.2%}, {hi:.2%}]  "
          f"n={n:,}  z={(hits/n-0.5)/se:+.2f}")
    print(f"  (Polymarket 5m for reference: ~51.5-52% at |z| in band)\n")

    print("=== by |z| band (the tradeable dimension) ===")
    bands = [(0.0, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, 0.60),
             (0.60, 1.0), (1.0, 99)]
    for a, b in bands:
        sub = [r for r in rows if a <= abs(r["z"]) < b]
        if len(sub) < 30:
            continue
        h = sum(1 for r in sub if (r["g"] > 0) == r["up"])
        l2, h2 = wilson(h, len(sub))
        s2 = math.sqrt(0.25 / len(sub))
        print(f"  |z| {a:4.2f}-{b:<5.2f} n={len(sub):>5,}  hit {h/len(sub):6.2%}  "
              f"[{l2:5.1%},{h2:5.1%}]  z={(h/len(sub)-0.5)/s2:+5.2f}")

    print("\n=== by |gap| in bp (how far spot sits from the strike) ===")
    for a, b in [(0, 2), (2, 5), (5, 10), (10, 20), (20, 50), (50, 1e9)]:
        sub = [r for r in rows if a <= abs(r["g"]) < b]
        if len(sub) < 30:
            continue
        h = sum(1 for r in sub if (r["g"] > 0) == r["up"])
        l2, h2 = wilson(h, len(sub))
        s2 = math.sqrt(0.25 / len(sub))
        print(f"  {a:>3}-{b if b < 1e9 else 'inf':<5} bp  n={len(sub):>5,}  "
              f"hit {h/len(sub):6.2%}  [{l2:5.1%},{h2:5.1%}]  "
              f"z={(h/len(sub)-0.5)/s2:+5.2f}")

    print("\n=== stability: by month ===")
    for mo in sorted(set(r["date"][:7] for r in rows)):
        sub = [r for r in rows if r["date"].startswith(mo)]
        h = sum(1 for r in sub if (r["g"] > 0) == r["up"])
        l2, h2 = wilson(h, len(sub))
        print(f"  {mo}  n={len(sub):>5,}  hit {h/len(sub):6.2%}  [{l2:5.1%},{h2:5.1%}]")


if __name__ == "__main__":
    main()
