"""Remote status pusher for the nix2 bot.

You can't watch a terminal for days, and this Claude session is ephemeral — the
bot must run on an ALWAYS-ON host (a $5/mo VPS, a home PC, or a Raspberry Pi).
This script makes the bot checkable from your phone: it reads the trade logs,
computes the running P&L + pre-registered verdict, writes bot/live/STATUS.md,
and git-pushes it. Run it on a cron next to the bot (e.g. hourly):

    */30 * * * *  cd /path/to/repo && python bot/live/status.py --accounts paper1,paper2

Then just open STATUS.md in the GitHub repo on your phone whenever you want.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess


def load(account: str) -> list[dict]:
    try:
        return [json.loads(l) for l in open(f"logs/nix2_live_{account}.jsonl")]
    except FileNotFoundError:
        return []


def summarize(recs: list[dict]) -> dict:
    trades = [r for r in recs if r.get("decision") == "TRADE" and r.get("fill")]
    by_day: dict[str, list[float]] = {}
    tot = wins = n = 0.0
    for t in trades:
        res = t.get("resolved")           # settle.py backfills this
        if res is None:
            continue
        px = t["fill"]["price"]; sh = t["fill"]["shares"]; stake = t["stake"]
        pnl = sh * res - stake - 0.07 * px * (1 - px) * sh
        by_day.setdefault(t["ts"][:10], []).append(pnl)
        tot += pnl; wins += res > 0.5; n += 1
    daily = [sum(v) / len(v) for v in by_day.values()]
    t = float("nan")
    if len(daily) > 1:
        m = sum(daily) / len(daily)
        sd = math.sqrt(sum((d - m) ** 2 for d in daily) / (len(daily) - 1))
        t = m / (sd / math.sqrt(len(daily))) if sd else float("nan")
    return {"signals": len(recs), "trades": len(trades), "resolved": int(n),
            "wr": wins / n if n else float("nan"), "total": tot,
            "days": len(by_day), "daily_t": t}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", default="paper1")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    lines = [f"# nix2 bot status — {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC\n",
             "Rule: buy cheap (44-50c) BTC 5m side when 1s-signal confirms; hold to resolution.",
             "Verdict bar: total>0 AND daily t>=2.0 over >=20 trade-days (days after 2026-07-08).\n",
             "| account | signals | trades | resolved | win% | total$ | days | daily t | verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for acc in args.accounts.split(","):
        s = summarize(load(acc.strip()))
        v = ("PASS" if s["total"] > 0 and s["daily_t"] >= 2.0 and s["days"] >= 20
             else "accruing")
        wr = f"{s['wr']:.0%}" if s["resolved"] else "-"
        tt = f"{s['daily_t']:+.2f}" if s["days"] > 1 else "-"
        lines.append(f"| {acc} | {s['signals']} | {s['trades']} | {s['resolved']} "
                     f"| {wr} | ${s['total']:+.2f} | {s['days']} | {tt} | {v} |")
    open("bot/live/STATUS.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not args.no_push:
        subprocess.call("git add bot/live/STATUS.md && "
                        "git commit -q -m 'nix2 status update' && "
                        "git push -q", shell=True)


if __name__ == "__main__":
    main()
