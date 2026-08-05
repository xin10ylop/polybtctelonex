"""Why did the paper fleet's performance drop? Find the breakpoint in the log.

Between 2026-08-01 23:45 and 2026-08-02 00:08 several things changed at once:
  * the fleet moved from hand-launched processes to systemd units
  * paper1/paper4 briefly ran DOUBLE (legacy nix2-bot* units alongside)
  * bot/live/nix2_live.py gained _io(): pm.* HTTP calls now run via
    asyncio.to_thread under an 8s timeout, plus a watchdog

That last one touches the decision path, and the z-response work showed this
edge lives in the half-second before the open — so added latency would not
shrink the edge, it would remove it. This script tests that against the data
instead of arguing about it.

  .venv/bin/python src/nix_regress.py --account paper1
  .venv/bin/python src/nix_regress.py --account paper4 --stake 50

Reports, split BEFORE vs AFTER the 2026-08-02 cutover:
  1. per-day P&L, so the breakpoint is visible rather than inferred
  2. win rate / EV / entry price / |z| / depth — did the TRADES change, or
     just their outcomes?
  3. for --realistic accounts: ask_at_fill vs ask, which measures whether the
     book moved away between decision and fill (i.e. late execution)
  4. skip-reason mix, which shows whether the bot is seeing the same market
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict

CUT = "2026-08-02"          # systemd cutover + _io() change


def load(account: str):
    trades, skips = [], []
    for line in open(f"logs/nix2_live_{account}.jsonl"):
        r = json.loads(line)
        (trades if r.get("decision") == "TRADE" else skips).append(r)
    return trades, skips


def resolve(slug: str, cache: dict):
    import ssl
    import urllib.request
    if slug in cache:
        return cache[slug]
    try:
        req = urllib.request.Request(
            f"https://gamma-api.polymarket.com/markets?slug={slug}&closed=true",
            headers={"User-Agent": "nix2/1.0"})
        with urllib.request.urlopen(req, timeout=12,
                                    context=ssl.create_default_context()) as r:
            d = json.load(r)
        op = d[0].get("outcomePrices") if d else None
        if isinstance(op, str):
            op = json.loads(op)
        cache[slug] = (float(op[0]) > float(op[1])) if op and len(op) == 2 else None
    except Exception:
        cache[slug] = None
    return cache[slug]


def stats(label: str, rows: list[dict]) -> None:
    if not rows:
        print(f"  {label:<10} (none)")
        return
    p = [r["pnl"] for r in rows]
    wr = sum(1 for r in rows if r["won"]) / len(rows)
    m = statistics.mean(p)
    t = (m / (statistics.stdev(p) / math.sqrt(len(p)))
         if len(p) > 1 and statistics.stdev(p) > 0 else float("nan"))
    asks = [r["ask"] for r in rows if r["ask"] is not None]
    zs = [abs(r["z"]) for r in rows if r["z"] is not None]
    dp = [r["depth"] for r in rows if r["depth"] is not None]
    print(f"  {label:<10} n={len(rows):>4}  wr {wr:6.2%}  EV ${m:+7.3f}  "
          f"tot ${sum(p):+8.2f}  t={t:+5.2f}  |  ask {statistics.mean(asks):.4f}  "
          f"|z| {statistics.mean(zs):.4f}  depth ${statistics.median(dp):.0f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="paper1")
    ap.add_argument("--stake", type=float, default=10.0)
    args = ap.parse_args()
    trades, skips = load(args.account)
    cache: dict = {}

    rows = []
    for t in trades:
        uw = resolve(t["slug"], cache)
        if uw is None:
            continue
        won = (t["side"] == "up") == uw
        px, sh = t["fill"]["price"], t["fill"]["shares"]
        spent = t["fill"].get("spent", t["stake"])
        pnl = sh * (1.0 if won else 0.0) - spent - 0.07 * px * (1 - px) * sh
        rows.append({"d": t["ts"][:10], "won": won, "pnl": pnl,
                     "ask": t.get("ask"), "z": t.get("z"),
                     "depth": t.get("depth_usd"),
                     "askfill": t.get("ask_at_fill"),
                     "partial": bool(t.get("partial"))})

    print(f"=== {args.account}: {len(rows)} resolved trades ===\n")
    print("--- per-day P&L (breakpoint should be visible) ---")
    by = defaultdict(list)
    for r in rows:
        by[r["d"]].append(r)
    cum = 0.0
    for d in sorted(by):
        v = by[d]
        s = sum(x["pnl"] for x in v)
        cum += s
        mark = "  <<< cutover" if d == CUT else ""
        print(f"  {d}  n={len(v):>2}  wr {sum(1 for x in v if x['won'])/len(v):5.0%}  "
              f"${s:+8.2f}   cum ${cum:+9.2f}{mark}")

    print(f"\n--- BEFORE vs AFTER {CUT} ---")
    stats("BEFORE", [r for r in rows if r["d"] < CUT])
    stats("AFTER", [r for r in rows if r["d"] >= CUT])

    af = [r for r in rows if r["askfill"] is not None]
    if af:
        print(f"\n--- execution drift: ask at decision vs ask at fill ---")
        for lab, sub in (("BEFORE", [r for r in af if r["d"] < CUT]),
                         ("AFTER", [r for r in af if r["d"] >= CUT])):
            if not sub:
                continue
            dr = [r["askfill"] - r["ask"] for r in sub if r["ask"] is not None]
            pr = sum(1 for r in sub if r["partial"]) / len(sub)
            print(f"  {lab:<8} n={len(sub):>4}  median drift {statistics.median(dr):+.4f}  "
                  f"mean {statistics.mean(dr):+.4f}  partial-fill rate {pr:.1%}")
        print("  (a widening positive drift = the book moved away before we filled)")

    print(f"\n--- skip-reason mix (is the bot seeing the same market?) ---")
    for lab, sub in (("BEFORE", [s for s in skips if s["ts"][:10] < CUT]),
                     ("AFTER", [s for s in skips if s["ts"][:10] >= CUT])):
        c = Counter(s.get("reason") for s in sub)
        tot = sum(c.values()) or 1
        top = "  ".join(f"{k}={100*v/tot:.1f}%" for k, v in c.most_common(5))
        print(f"  {lab:<8} n={tot:>6}   {top}")


if __name__ == "__main__":
    main()
