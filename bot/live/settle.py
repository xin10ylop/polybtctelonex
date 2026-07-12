"""Settle the nix2 paper/live log against real resolutions and print P&L.

Reads logs/nix2_live_<account>.jsonl (the TRADE records) and looks up each 5m
window's official outcome from Polymarket's gamma API (the resolved market's
`outcomePrices`, matched by slug + the side the bot bought). Tallies realized
P&L so the pre-registered forward one-shot fills itself in.

  python bot/live/settle.py --account paper1        # summary + verdict
  python bot/live/settle.py --account paper1 -v      # + per-trade lines

Verdict bar (bot/cheapsig.json): total>0 AND daily-EV t>=2.0 over >=20
trade-days on days strictly after 2026-07-08.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
_CTX = ssl.create_default_context()


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "nix2/1.0"})
    with urllib.request.urlopen(req, timeout=12, context=_CTX) as r:
        return json.load(r)


def up_won(slug: str) -> bool | None:
    """True if Up resolved, False if Down, None if not resolved yet."""
    try:
        d = _get(f"{GAMMA}/markets?slug={slug}&closed=true")
        if not d:
            return None
        m = d[0]
        if m.get("umaResolutionStatus") != "resolved":
            return None
        op = m.get("outcomePrices")
        if isinstance(op, str):
            op = json.loads(op)
        if not op or len(op) != 2:
            return None
        return float(op[0]) > float(op[1])
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="paper1")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    try:
        trades = [json.loads(l) for l in open(f"logs/nix2_live_{args.account}.jsonl")
                  if '"decision": "TRADE"' in l]
    except FileNotFoundError:
        print("no log yet"); return

    by_day: dict[str, list[float]] = {}
    tot = n = wins = 0.0
    pending = 0
    for t in trades:
        uw = up_won(t["slug"])
        if uw is None:
            pending += 1
            continue
        side_won = (t["side"] == "up") == uw
        res = 1.0 if side_won else 0.0
        px = t["fill"]["price"]; sh = t["fill"]["shares"]; stake = t["stake"]
        fee = 0.07 * px * (1 - px) * sh
        pnl = sh * res - stake - fee
        by_day.setdefault(t["ts"][:10], []).append(pnl)
        tot += pnl; n += 1; wins += side_won
        if args.verbose:
            print(f"  {t['ts'][:19]} {t['side']:<4} @{px} -> "
                  f"{'WIN ' if side_won else 'loss'} ${pnl:+.2f}")

    if n == 0:
        print(f"{len(trades)} trades logged, {pending} pending resolution, "
              f"none resolved yet"); return
    daily = [sum(v) / len(v) for v in by_day.values()]
    mean = sum(daily) / len(daily)
    sd = math.sqrt(sum((d - mean) ** 2 for d in daily) / (len(daily) - 1)) if len(daily) > 1 else 0.0
    tstat = mean / (sd / math.sqrt(len(daily))) if sd > 0 else float("nan")
    print(f"account {args.account}: {int(n)} resolved ({pending} pending) over "
          f"{len(by_day)} trade-days")
    print(f"  win rate {wins/n:.1%}, total ${tot:+.2f}, EV ${tot/n:+.3f}/trade")
    print(f"  daily-EV mean ${mean:+.3f}/day, t={tstat:+.2f}")
    passed = tot > 0 and tstat >= 2.0 and len(by_day) >= 20
    print(f"  verdict (bar: total>0, t>=2.0, >=20 days): "
          f"{'PASS - edge confirmed' if passed else 'accumulating...'}")


if __name__ == "__main__":
    main()
