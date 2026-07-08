"""NIXULTIMATE 2.0 — frozen final-seconds signal on the FEE-FREE hourly market.

Differences from nix1/N8, all structural (not tuned):
  - resolution = Binance BTC/USDT 1H candle close>=open (verified 765/765 vs
    result_id) -> the signal feed IS the referee; no Chainlink, no broadcast
    delay, no synthesis
  - taker_base_fee = 0 (verified on CLOB API; 5m contrast shows 1000) -> the
    EV gate keeps its frozen 2c margin but fee term = 0
  - no Telonex book data exists -> fills are TAPE-BASED: we require a real
    print on the winner token strictly after the decision second and before
    the close, and price BOTH ways:
      optimistic  = best (lowest) winner-token print in the window
      conservative = worst (highest) winner-token print in the window
    Reality for a taker sits between; the EV gate is applied to the
    CONSERVATIVE price. Exploratory evidence — live paper validation decides.

Frozen gates: T = close-3s, |z|>=1.5 (sigma = 1s Binance logret std over
prior 300s), EV margin 0.02, $5 stakes.
Usage: .venv/bin/python src/hourly_lastsec.py
Output: results/hourly_lastsec.parquet + monthly table.
"""
from __future__ import annotations

import datetime as dt
import glob
import math
import os
import re
import sys

import numpy as np
import polars as pl
from scipy.stats import norm

Z_THR = 1.5
EV_MARGIN = 0.02
STAKE = 5.0
HOURLY_RE = re.compile(r"(am|pm)-et$")


def main() -> None:
    kcache: dict[str, pl.DataFrame | None] = {}

    def klines(day: str):
        if day not in kcache:
            p = f"data/processed/binance/klines_1s/{day}.parquet"
            kcache[day] = pl.read_parquet(p).sort("open_time_us") if os.path.exists(p) else None
        return kcache[day]

    rows = []
    for path in sorted(glob.glob("data/processed/hourly/tape/*.parquet")):
        tape = pl.read_parquet(path)
        if tape.is_empty():
            continue
        tape = tape.filter(pl.col("slug").str.contains(HOURLY_RE.pattern))
        for (end_us, slug, rid), g in tape.group_by(["end_us", "slug", "result_id"],
                                                    maintain_order=True):
            end_s = end_us // 1_000_000
            start_s = end_s - 3600
            T = end_s - 3
            d1 = dt.datetime.fromtimestamp(start_s - 400, dt.timezone.utc).strftime("%Y-%m-%d")
            d2 = dt.datetime.fromtimestamp(end_s, dt.timezone.utc).strftime("%Y-%m-%d")
            ks = [klines(d) for d in dict.fromkeys([d1, d2])]
            if any(k is None for k in ks):
                continue
            k = pl.concat(ks).sort("open_time_us") if len(ks) > 1 else ks[0]
            t_us = k["open_time_us"].to_numpy()
            op = k["open"].to_numpy()
            cl = k["close"].to_numpy()
            i0 = np.searchsorted(t_us, start_s * 1_000_000, "left")
            if i0 >= len(t_us) or t_us[i0] >= end_s * 1_000_000:
                continue
            O = op[i0]
            iT = np.searchsorted(t_us, (T - 1) * 1_000_000, "right") - 1
            j0 = np.searchsorted(t_us, (T - 300) * 1_000_000, "left")
            if iT <= j0 + 30:
                continue
            seg = np.log(cl[j0:iT + 1])
            sig = float(np.std(np.diff(seg)))
            if not (np.isfinite(sig) and sig > 0):
                continue
            P = cl[iT]
            z = math.log(P / O) / (sig * math.sqrt(3))
            if abs(z) < Z_THR:
                continue
            fair = float(norm.cdf(abs(z)))
            dir_up = z > 0
            up_won = rid == "0"
            # winner-token prints strictly after the decision second, pre-close
            gg = g.filter((pl.col("ts") >= T + 1) & (pl.col("ts") < end_s))
            if gg.is_empty():
                stagep = None
            else:
                tokpx = np.where(gg["up_token"].to_numpy(),
                                 gg["price"].to_numpy(),
                                 1.0 - gg["price"].to_numpy())
                wpx = tokpx if dir_up else 1.0 - tokpx
                sizes = gg["size"].to_numpy()
                stagep = (float(wpx.min()), float(wpx.max()), float(sizes.sum()))
            month = dt.datetime.fromtimestamp(end_s, dt.timezone.utc).strftime("%Y-%m")
            row = {"slug": slug, "end_s": int(end_s), "month": month,
                   "z": round(z, 2), "fair": round(fair, 4),
                   "dir_up": bool(dir_up), "won": bool(up_won == dir_up)}
            if stagep is None:
                row["stage"] = "no_prints"
            else:
                lo_px, hi_px, vol = stagep
                row.update({"px_opt": round(lo_px, 4), "px_con": round(hi_px, 4),
                            "final_vol": round(vol, 1)})
                if not (0.02 < hi_px < 0.995):
                    row["stage"] = "px_range"
                elif fair - hi_px < EV_MARGIN:   # fee = 0, gate on CONSERVATIVE px
                    row["stage"] = "ev_block"
                else:
                    row["stage"] = "traded"
                    win = 1.0 if row["won"] else 0.0
                    for tag, px in (("opt", lo_px), ("con", hi_px)):
                        sh = STAKE / px
                        row[f"pnl_{tag}"] = round(sh * win - STAKE, 4)
            rows.append(row)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet("results/hourly_lastsec.parquet")
    pl.Config.set_tbl_cols(16)
    print(f"z-passed windows: {len(df)}")
    print(df.group_by("stage").len().sort("len", descending=True))
    tr = df.filter(pl.col("stage") == "traded")
    for mo in sorted(set(df["month"])):
        t = tr.filter(pl.col("month") == mo)
        d = df.filter(pl.col("month") == mo)
        days = len(set(s // 86400 for s in d["end_s"]))
        if len(t) == 0:
            print(f"{mo}: z-passed {len(d):4d}, 0 trades")
            continue
        for tag in ("con", "opt"):
            p = t[f"pnl_{tag}"].to_numpy()
            mu, sd = p.mean(), p.std(ddof=1)
            tstat = mu / (sd / np.sqrt(len(p))) if sd > 0 else 0
            print(f"{mo} [{tag}]: n={len(p):3d} ${p.sum():8.2f} (${p.sum()/max(days,1):6.2f}/day) "
                  f"mean=${mu:.2f} t={tstat:.1f} wr={(p > 0).mean():.0%}")
    # gate-openness: winner-token conservative price distribution
    px = df.filter(pl.col("px_con").is_not_null())["px_con"]
    if len(px):
        print(f"\nfinal-3s winner-token print (conservative): median {px.median():.3f}, "
              f"share<0.98: {float((px < 0.98).mean()):.0%}  (5m July was 99c+)")
    fv = df.filter(pl.col("final_vol").is_not_null())["final_vol"]
    if len(fv):
        print(f"final-3s tape volume/window: median {fv.median():.0f} shares")


if __name__ == "__main__":
    main()
