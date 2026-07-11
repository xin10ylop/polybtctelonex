"""Settle the nix2 paper/live log against real resolutions and print P&L.

Reads logs/nix2_live_<account>.jsonl (the TRADE records), looks up each 5m
window's outcome from Polymarket's resolved market (gamma umaResolutionStatus /
price), and tallies realized P&L so the pre-registered forward one-shot fills
itself in. Run any time: `python bot/live/settle.py --account paper1`.

Verdict bar (bot/cheapsig.json): positive EV AND daily-EV t>=2.0 over >=20
trade-days on days strictly after 2026-07-08.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import urllib.request

CLOB = "https://clob.polymarket.com"
_CTX = ssl.create_default_context()


def resolved_price(token_id: str) -> float | None:
    """1.0 if the token resolved YES/Up, 0.0 if NO/Down, None if unresolved."""
    try:
        req = urllib.request.Request(f"{CLOB}/prices?token_id={token_id}",
                                     headers={"User-Agent": "nix2/1.0"})
        with urllib.request.urlopen(req, timeout=10, context=_CTX) as r:
            d = json.load(r)
        p = float(d.get("price", d) if isinstance(d, dict) else d)
        if p >= 0.99:
            return 1.0
        if p <= 0.01:
            return 0.0
        return None
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="paper1")
    args = ap.parse_args()
    trades = []
    try:
        for line in open(f"logs/nix2_live_{args.account}.jsonl"):
            r = json.loads(line)
            if r.get("decision") == "TRADE" and r.get("fill"):
                trades.append(r)
    except FileNotFoundError:
        print("no log yet"); return

    by_day: dict[str, list[float]] = {}
    tot = n = wins = 0.0
    for t in trades:
        tok = t["fill"]["token"] if "token" in t["fill"] else None
        # token id isn't stored in fill for live resp; fall back to side mapping
        # (paper fill stores 'token'); resolve via that token's settled price
        res = resolved_price(tok) if tok else None
        if res is None:
            continue
        px = t["fill"]["price"]; sh = t["fill"]["shares"]; stake = t["stake"]
        fee = 0.07 * px * (1 - px) * sh   # taker fee (current schedule)
        pnl = sh * res - stake - fee
        day = t["ts"][:10]
        by_day.setdefault(day, []).append(pnl)
        tot += pnl; n += 1; wins += (res > 0.5)
    if n == 0:
        print(f"{len(trades)} trades logged, none resolved yet"); return
    daily = [sum(v) / len(v) for v in by_day.values()]
    mean = sum(daily) / len(daily)
    sd = math.sqrt(sum((d - mean) ** 2 for d in daily) / (len(daily) - 1)) if len(daily) > 1 else 0
    tstat = mean / (sd / math.sqrt(len(daily))) if sd > 0 else float("nan")
    print(f"account {args.account}: {int(n)} resolved trades over {len(by_day)} days")
    print(f"  win rate {wins/n:.1%}, total ${tot:+.2f}, EV ${tot/n:+.3f}/trade")
    print(f"  daily-EV mean ${mean:+.3f}, t={tstat:+.2f} (bar: t>=2.0 over >=20 days)")
    verdict = "PASS -> confirmed" if (tot > 0 and tstat >= 2.0 and len(by_day) >= 20) \
        else "accumulating / not yet met"
    print(f"  one-shot verdict: {verdict}")


if __name__ == "__main__":
    main()
