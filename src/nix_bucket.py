"""Bucket a paper account's resolved trades by the book state recorded at
decision time, to test two competing claims about resting ask size.

The question (raised by comparing this repo against the S2/polymarketstrat
research):

  nix2 v2 (paper2) gates on q_imb < -0.05 -- "the book leans AWAY from our
  side, which is the mispricing fingerprint" -- i.e. it buys MORE when ask
  size exceeds bid size.

  The S2 audit measured the opposite: large resting asks are INFORMED
  (-2.4c/share in the >=250-share bucket), and it refuses them outright
  (skip_ask_above=500).

paper1 is the clean instrument for settling this: it RECORDS q_imb and
depth_usd on every decision but gates on NEITHER, so its fills are an
unfiltered sample. paper2's 40 trades are already conditioned on the gate
and cannot answer the question.

  .venv/bin/python src/nix_bucket.py --account paper1

Read-only: reads the jsonl log and the public gamma resolution endpoint.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import statistics
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
_CTX = ssl.create_default_context()
FEE = 0.07


def up_won(slug: str) -> bool | None:
    try:
        req = urllib.request.Request(f"{GAMMA}/markets?slug={slug}&closed=true",
                                     headers={"User-Agent": "nix2/1.0"})
        with urllib.request.urlopen(req, timeout=12, context=_CTX) as r:
            d = json.load(r)
        if not d or d[0].get("umaResolutionStatus") != "resolved":
            return None
        op = d[0].get("outcomePrices")
        if isinstance(op, str):
            op = json.loads(op)
        return float(op[0]) > float(op[1]) if op and len(op) == 2 else None
    except Exception:
        return None


def tstat(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = statistics.mean(xs)
    sd = statistics.stdev(xs)
    return m / (sd / math.sqrt(len(xs))) if sd > 0 else float("nan")


def show(label: str, rows: list[dict], total_n: int) -> None:
    if not rows:
        print(f"  {label:<24} (none)")
        return
    p = [r["pnl"] for r in rows]
    wr = sum(1 for r in rows if r["won"]) / len(rows)
    print(f"  {label:<24} n={len(rows):>3} ({100*len(rows)/total_n:4.1f}%)  "
          f"wr {wr:5.1%}  EV ${statistics.mean(p):+6.3f}  "
          f"tot ${sum(p):+8.2f}  t={tstat(p):+5.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="paper1")
    args = ap.parse_args()

    trades = []
    for line in open(f"logs/nix2_live_{args.account}.jsonl"):
        if '"decision": "TRADE"' not in line:
            continue
        t = json.loads(line)
        uw = up_won(t["slug"])
        if uw is None:
            continue
        won = (t["side"] == "up") == uw
        px = t["fill"]["price"]
        sh = t["fill"]["shares"]
        spent = t["fill"].get("spent", t["stake"])
        fee = FEE * px * (1 - px) * sh
        trades.append({
            "pnl": sh * (1.0 if won else 0.0) - spent - fee,
            "won": won, "ask": t.get("ask"), "q_imb": t.get("q_imb"),
            "depth": t.get("depth_usd"), "z": abs(t.get("z") or 0.0),
        })

    n = len(trades)
    if not n:
        print("no resolved trades")
        return
    print(f"=== {args.account}: {n} resolved trades ===\n")
    show("ALL", trades, n)

    # --- 1. the paper2 gate, measured on UNGATED data -------------------
    print("\n--- q_imb: does paper2's gate (q_imb < -0.05) actually help? ---")
    print("    (q_imb < 0 = MORE ask size than bid size on our side)")
    have_q = [t for t in trades if t["q_imb"] is not None]
    show("q_imb < -0.05  (BUY)", [t for t in have_q if t["q_imb"] < -0.05], n)
    show("q_imb >= -0.05 (SKIP)", [t for t in have_q if t["q_imb"] >= -0.05], n)

    # --- 2. the S2 claim: is large resting ask size informed? -----------
    print("\n--- touch depth: are big resting asks informed (S2) or opportunity (v2)? ---")
    have_d = sorted([t for t in trades if t["depth"] is not None],
                    key=lambda t: t["depth"])
    if have_d:
        q = len(have_d) // 4
        cuts = [have_d[:q], have_d[q:2*q], have_d[2*q:3*q], have_d[3*q:]]
        for i, c in enumerate(cuts):
            if c:
                lo, hi = c[0]["depth"], c[-1]["depth"]
                show(f"Q{i+1} ${lo:.0f}-${hi:.0f}", c, n)

    # --- 3. entry-price band (S2 found bands behave very differently) ---
    print("\n--- entry price band ---")
    for lo, hi in ((0.43, 0.455), (0.455, 0.475), (0.475, 0.495), (0.495, 0.51)):
        show(f"ask {lo:.3f}-{hi:.3f}",
             [t for t in trades if t["ask"] is not None and lo <= t["ask"] < hi], n)

    # --- 4. signal strength ---------------------------------------------
    print("\n--- |z| band (signal strength) ---")
    for lo, hi in ((0.05, 0.15), (0.15, 0.25), (0.25, 0.40)):
        show(f"|z| {lo:.2f}-{hi:.2f}",
             [t for t in trades if lo <= t["z"] < hi], n)


if __name__ == "__main__":
    main()
