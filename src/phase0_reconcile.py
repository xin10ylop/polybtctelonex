"""GATE 0 cross-source reconciliation: Telonex tick data vs Polymarket's free
CLOB prices-history API, on >=200 randomly sampled windows.

For each sampled window (Up token): fetch 1-minute prices-history from
clob.polymarket.com covering [wts-300, wts+dur], then compare each API point
against the Telonex BBO mid as-of that timestamp. Report per-window mean abs
diff and flag windows above tolerance for investigation.

Writes reports/phase0_reconciliation.md.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import loader
import windows as W

SAMPLES = [("5m", "2026-06-15", 210), ("15m", "2025-11-15", 40)]
TOL_MEAN = 0.005  # half a tick: API price must exist in our stream within its bucket
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}


def api_history(token_id: str, start: int, end: int, fidelity: int = 1) -> list[dict]:
    q = urllib.parse.urlencode({"market": token_id, "startTs": start, "endTs": end,
                                "fidelity": fidelity})
    req = urllib.request.Request(f"https://clob.polymarket.com/prices-history?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("history", [])


def reconcile_family(family: str, date: str, n_sample: int, rng: random.Random):
    dur = W.FAMILY_DUR[family]
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(family, d0, d0 + 86400)
    q = (loader.load_daily(family, "quotes", [date])
         .select("wts", "timestamp_us", "bid_price", "ask_price").collect())
    rows = []
    sample = rng.sample(list(meta.iter_rows(named=True)), min(n_sample, len(meta)))
    for i, m in enumerate(sample):
        wts = m["wts"]
        try:
            hist = api_history(m["asset_id_0"], wts - 300, wts + dur)
        except Exception as e:
            rows.append({"family": family, "wts": wts, "n_pts": 0, "mad": None,
                         "note": f"api_error {e}"})
            continue
        qq = q.filter(pl.col("wts") == wts).sort("timestamp_us")
        if not hist or qq.is_empty():
            rows.append({"family": family, "wts": wts, "n_pts": len(hist), "mad": None,
                         "note": "no data one side"})
            continue
        # two-sided books only: near resolution one side empties and mid is undefined
        qq2 = qq.drop_nulls(["bid_price", "ask_price"])
        t_us = qq2["timestamp_us"].to_numpy()
        mid = ((qq2["bid_price"] + qq2["ask_price"]) / 2).to_numpy()
        # The API's minute-bucket label time differs from the sample time by up to
        # one bucket (verified on window 1781500800): count an API point as matched
        # if its price occurs in the Telonex mid stream within the preceding 75s.
        diffs = []
        for h in hist:
            pt = int(h["t"]) * 1_000_000
            lo = np.searchsorted(t_us, pt - 75_000_000, side="left")
            hi = np.searchsorted(t_us, pt, side="right")
            if hi <= lo:
                continue
            diffs.append(float(np.min(np.abs(mid[lo:hi] - float(h["p"])))))
        if not diffs:
            rows.append({"family": family, "wts": wts, "n_pts": len(hist), "mad": None,
                         "note": "no overlap"})
            continue
        rows.append({"family": family, "wts": wts, "n_pts": len(diffs),
                     "mad": float(np.mean(diffs)), "note": ""})
        if i % 25 == 0:
            time.sleep(0.5)  # be polite to the free API
    return rows


def main():
    rng = random.Random(20260706)
    all_rows = []
    for family, date, n in SAMPLES:
        all_rows += reconcile_family(family, date, n, rng)
    df = pl.DataFrame(all_rows)
    comp = df.filter(pl.col("mad").is_not_null())
    n_ok = len(comp.filter(pl.col("mad") <= TOL_MEAN))
    lines = [
        "# Phase 0 — cross-source reconciliation (Telonex vs Polymarket CLOB API)",
        "",
        f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. "
        f"Sampled windows: {len(df)} (target >= 200). Comparable: {len(comp)}.",
        "",
        f"- Comparison: CLOB `prices-history` (1-min fidelity) vs Telonex two-sided BBO mid: API price must occur in the Telonex mid stream within its preceding 75s bucket (bucket-timing convention verified on window 1781500800).",
        f"- Mean abs diff per window: median {comp['mad'].median():.4f}, "
        f"p95 {comp['mad'].quantile(0.95):.4f}, max {comp['mad'].max():.4f}",
        f"- Windows within tolerance (mean diff <= ${TOL_MEAN}): {n_ok}/{len(comp)} "
        f"({100 * n_ok / max(len(comp), 1):.1f}%)",
        "",
    ]
    worst = comp.sort("mad", descending=True).head(10)
    lines += ["Worst 10 windows (for investigation):", "",
              "| family | wts | points | mean_abs_diff |", "|---|---|---|---|"]
    for r in worst.iter_rows(named=True):
        lines.append(f"| {r['family']} | {r['wts']} | {r['n_pts']} | {r['mad']:.4f} |")
    excluded = df.filter(pl.col("mad").is_null())
    lines += ["", f"Windows without comparable data: {len(excluded)} "
              f"({excluded['note'].value_counts().to_dicts() if len(excluded) else 'none'})"]
    with open("reports/phase0_reconciliation.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"median MAD {comp['mad'].median():.4f}, within-tol {n_ok}/{len(comp)}")


if __name__ == "__main__":
    main()
