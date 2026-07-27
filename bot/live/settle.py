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
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="bankroll the risk-engine replay assumes")
    ap.add_argument("--stake", type=float, default=10.0)
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
        px = t["fill"]["price"]; sh = t["fill"]["shares"]
        # actual notional spent (partial fills); older records lack it
        stake = t["fill"].get("spent", t["stake"])
        fee = 0.07 * px * (1 - px) * sh
        pnl = sh * res - stake - fee
        by_day.setdefault(t["ts"][:10], []).append(pnl)
        tot += pnl; n += 1; wins += side_won
        if args.verbose:
            part = " PARTIAL" if t.get("partial") else ""
            print(f"  {t['ts'][:19]} {t['side']:<4} @{px} ${stake:>5.2f}{part} -> "
                  f"{'WIN ' if side_won else 'loss'} ${pnl:+.2f}")

    if n == 0:
        print(f"{len(trades)} trades logged, {pending} pending resolution, "
              f"none resolved yet"); return
    # day-clustered mean of per-trade EV (the pre-registered t-stat basis)
    daily = [sum(v) / len(v) for v in by_day.values()]
    mean = sum(daily) / len(daily)
    sd = math.sqrt(sum((d - mean) ** 2 for d in daily) / (len(daily) - 1)) if len(daily) > 1 else 0.0
    tstat = mean / (sd / math.sqrt(len(daily))) if sd > 0 else float("nan")
    # actual dollars earned per trading day (what "per day" really means)
    per_day = tot / len(by_day)
    # per-trade t, unclustered — reported alongside as the conservative check
    allp = [p for v in by_day.values() for p in v]
    m2 = sum(allp) / len(allp)
    sd2 = math.sqrt(sum((p - m2) ** 2 for p in allp) / (len(allp) - 1)) if len(allp) > 1 else 0.0
    t_trade = m2 / (sd2 / math.sqrt(len(allp))) if sd2 > 0 else float("nan")
    print(f"account {args.account}: {int(n)} resolved ({pending} pending) over "
          f"{len(by_day)} trade-days")
    print(f"  win rate {wins/n:.1%}, total ${tot:+.2f}, EV ${tot/n:+.3f}/trade")
    print(f"  actual ${per_day:+.2f}/trading-day ({n/len(by_day):.1f} trades/day)")
    print(f"  day-clustered mean ${mean:+.3f}/trade, t={tstat:+.2f}  "
          f"(per-trade t={t_trade:+.2f})")
    # --- risk engine replay: what would the live risk layer be doing? ---
    try:
        import os as _os, sys as _sys
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from risk import RiskConfig, RiskEngine
        eng = RiskEngine(cfg=RiskConfig(bankroll=args.bankroll))
        blocked = 0
        for day in sorted(by_day):
            for p in by_day[day]:
                ok, _r = eng.may_trade(day)
                if not ok:
                    blocked += 1
                    continue
                eng.record(p, args.stake, day)
        st = eng.status()
        dt_ = f"{st['decay_t']:+.2f}" if st["decay_t"] is not None else "n/a (needs 250 trades)"
        print(f"  risk engine (bankroll ${args.bankroll:.0f}): {st['state']}"
              f"{(' - ' + st['reason']) if st['reason'] else ''}")
        print(f"    drawdown ${st['drawdown']:.2f} of ${RiskConfig(bankroll=args.bankroll).max_drawdown_frac*args.bankroll:.0f} limit"
              f" | loss streak {st['streak']} of 12 | decay t {dt_}"
              + (f" | {blocked} trades blocked" if blocked else ""))
    except Exception as _e:
        print(f"  risk engine: unavailable ({_e})")

    passed = tot > 0 and tstat >= 2.0 and len(by_day) >= 20
    print(f"  verdict (bar: total>0, t>=2.0, >=20 days): "
          f"{'PASS - edge confirmed' if passed else 'accumulating...'}")


if __name__ == "__main__":
    main()
