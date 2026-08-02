"""Is the 5m edge really the oracle-lag mechanism? Compare z-response curves.

The story says the edge comes from a stale strike, so the probability tilt
should scale with z = g/(sigma*sqrt(T)):

    P(win) - 0.5  ~  phi(0) * z        -> MONOTONIC in |z|

That is a strong, falsifiable prediction and nobody has checked it. It also
settles the 5m-vs-15m puzzle, because z already contains the sqrt(duration)
term: if the mechanism is real, 5m and 15m windows at the SAME z should win at
the SAME rate. The families would then differ only in how many windows reach a
given z, not in edge quality.

Three outcomes, three different conclusions:
  * both families monotonic and overlapping  -> mechanism real, 15m is merely
    starved of qualifying windows (a capacity problem, not an edge problem)
  * 5m monotonic, 15m flat                   -> something 5m-specific; the
    oracle-lag story is wrong or incomplete
  * both flat                                -> the 5m "edge" is not this
    mechanism at all, and the sqrt(duration) reasoning is unfounded

Hit rate only — no prices, no fills, no fees. This asks whether the SIGNAL
predicts direction, which is upstream of whether it is tradeable.

  .venv/bin/python src/nix_zresponse.py
"""
from __future__ import annotations

import glob
import math
import os

import polars as pl

WIN = "data/processed/windows.parquet"
KL = "data/processed/binance/klines_1s"


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (float("nan"),) * 2
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sigma_bp(px: dict[int, float], t: int, dur: int) -> float | None:
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
    return math.sqrt(v) * math.sqrt(dur) * 1e4


def collect(family: str, dur: int) -> list[dict]:
    w = pl.read_parquet(WIN).filter(
        (pl.col("family") == family) & pl.col("result_id").is_not_null())
    have = {os.path.basename(p)[:-8] for p in glob.glob(f"{KL}/*.parquet")}
    dates = [d for d in sorted(set(w["date"].to_list())) if d in have]
    out = []
    for i, d in enumerate(dates):
        k = pl.read_parquet(f"{KL}/{d}.parquet", columns=["open_time_us", "close"])
        px = dict(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))
        day = w.filter(pl.col("date") == d)
        for wts, res in zip(day["wts"], day["result_id"]):
            p_now, p_1s = px.get(wts - 1), px.get(wts - 2)
            if not p_now or not p_1s or p_1s <= 0:
                continue
            g = math.log(p_now / p_1s) * 1e4
            if g == 0:
                continue
            sg = sigma_bp(px, wts, dur)
            if not sg or sg <= 0:
                continue
            out.append({"z": g / sg, "up": int(res) == 0, "g": g})
        if (i + 1) % 60 == 0:
            print(f"    {family}: {i+1}/{len(dates)} days, {len(out)} windows",
                  flush=True)
    return out


def curve(label: str, rows: list[dict]) -> None:
    print(f"\n  --- {label}  (n={len(rows):,}) ---")
    print(f"  {'|z| band':<14}{'n':>7}{'hit':>9}{'95% CI':>18}{'z':>7}")
    bands = [(0.00, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 0.20),
             (0.20, 0.40), (0.40, 0.80), (0.80, 99)]
    for a, b in bands:
        sub = [r for r in rows if a <= abs(r["z"]) < b]
        if len(sub) < 50:
            continue
        h = sum(1 for r in sub if (r["z"] > 0) == r["up"])
        lo, hi = wilson(h, len(sub))
        zs = (h / len(sub) - 0.5) / math.sqrt(0.25 / len(sub))
        print(f"  {a:.2f}-{b:<9.2f}{len(sub):>7,}{h/len(sub):>8.2%}"
              f"  [{lo:5.1%},{hi:5.1%}]{zs:>+7.2f}")


def main() -> None:
    print("collecting 5m ...")
    five = collect("5m", 300)
    print("collecting 15m ...")
    fifteen = collect("15m", 900)
    print("\n=== Z-RESPONSE: does the hit rate rise with |z|, as the "
          "oracle-lag story requires? ===")
    curve("BTC 5m  (dur=300)", five)
    curve("BTC 15m (dur=900)", fifteen)

    print("\n=== THE DECISIVE COMPARISON ===")
    print("  z already carries sqrt(duration). If the mechanism is real, the")
    print("  SAME z must win at the SAME rate on both families.")
    for a, b in [(0.05, 0.20), (0.20, 0.40), (0.05, 0.40)]:
        s5 = [r for r in five if a <= abs(r["z"]) < b]
        s15 = [r for r in fifteen if a <= abs(r["z"]) < b]
        if len(s5) < 50 or len(s15) < 50:
            continue
        h5 = sum(1 for r in s5 if (r["z"] > 0) == r["up"])
        h15 = sum(1 for r in s15 if (r["z"] > 0) == r["up"])
        p5, p15 = h5 / len(s5), h15 / len(s15)
        pp = (h5 + h15) / (len(s5) + len(s15))
        se = math.sqrt(pp * (1 - pp) * (1 / len(s5) + 1 / len(s15)))
        zz = (p5 - p15) / se if se > 0 else float("nan")
        print(f"  |z| {a:.2f}-{b:.2f}:  5m {p5:.2%} (n={len(s5):,})  vs  "
              f"15m {p15:.2%} (n={len(s15):,})   difference z={zz:+.2f}")
    print("\n  |difference z| < 1.96 => the families are statistically the SAME")
    print("  at equal z, i.e. 15m is starved of windows, not short of edge.")


if __name__ == "__main__":
    main()
