"""nix2 live bot — the cheap+signal edge, deployable.

RULE (frozen, bot/cheapsig.json): at 0.5s before a BTC 5m market opens, compute
the 1s spot return g and z=g/sigma from the fast feed. side = sign(g). If the
signal-side token's ask is in [0.44, 0.4999], |z| in [0.05, 0.40), and >= stake
rests at the touch, buy `stake` USDC taker and HOLD to resolution.

Runs PAPER by default (real live data + real book, simulated fills — this is
the pre-registered forward test). Set --live to place real orders (needs a
funded Polymarket account + PM_PRIVATE_KEY in env). Multi-account scaling: run
N instances with different --account tags / keys; each logs to its own file.

  python bot/live/nix2_live.py --venue binanceus --stake 10           # paper
  python bot/live/nix2_live.py --venue binanceus --stake 5 --live \
         --account wallet1                                             # live

Every decision (trade or skip) is appended to logs/nix2_live_<account>.jsonl so
the forward record accumulates automatically for the one-shot verdict.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import time

from feeds import SpotFeed
import pm

# frozen rule
ASK_MIN, ASK_MAX = 0.44, 0.4999
Z_MIN, Z_MAX = 0.05, 0.40
T0_OFF_US = -500_000     # decide 0.5s before open
FILL_OFF_US = -250_000   # fill 0.25s before open
DUR_S = 300


def next_boundary_us(now_us: int) -> int:
    """Next 5-minute UTC boundary strictly after now."""
    step = 300_000_000
    return ((now_us // step) + 1) * step


def log(account: str, rec: dict) -> None:
    os.makedirs("logs", exist_ok=True)
    with open(f"logs/nix2_live_{account}.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


async def trade_window(feed: SpotFeed, execu: pm.Executor, stake: float,
                       account: str, live: bool) -> None:
    now = int(time.time() * 1_000_000)
    B = next_boundary_us(now)
    T0 = B + T0_OFF_US
    # sleep until decision time
    await asyncio.sleep(max(0.0, (T0 - now) / 1e6))
    rec = {"ts": dt.datetime.utcnow().isoformat(), "B": B, "decision": "skip",
           "live": live, "reason": None}

    def emit(reason=None, **extra):
        rec.update(extra)
        if reason:
            rec["reason"] = reason
        print(f"[{account}] {rec['decision']} B={time.strftime('%H:%M', time.gmtime(B/1e6))} "
              f"reason={rec.get('reason')} z={rec.get('z')} ask={rec.get('ask')} "
              f"depth={rec.get('depth_usd')}", flush=True)
        log(account, rec)

    if not feed.ready():
        return emit("feed_warming", feed_n=len(feed.ts))
    sig = feed.signal(T0)
    if sig is None:
        return emit("no_signal")
    g, z = sig
    side = "up" if g > 0 else "down"
    rec.update({"g_bp": round(g, 3), "z": round(z, 4), "side": side})
    try:
        mkt = pm.find_btc_5m_market(B)
    except Exception as e:
        return emit(f"discover_err:{e}")
    if not mkt:
        return emit("no_market")
    token = mkt["up_token"] if side == "up" else mkt["down_token"]
    tob = pm.top_of_book(token)
    ask, depth = (tob if tob else (None, 0.0))
    rec.update({"slug": mkt["slug"], "ask": ask, "depth_usd": round(depth, 1),
                "stake": stake})
    if ask is None:
        return emit("no_book")
    if not (Z_MIN <= abs(z) < Z_MAX):
        return emit("z_gate")
    if not (ASK_MIN <= ask <= ASK_MAX):
        return emit("ask_gate")
    if depth < stake or stake < mkt["min_size"]:
        return emit("thin_book")
    # all gates pass -> TRADE
    rec["decision"] = "TRADE"
    await asyncio.sleep(max(0.0, (B + FILL_OFF_US - int(time.time() * 1e6)) / 1e6))
    rec["fill"] = execu.buy(token, ask, stake, mkt["tick"])
    rec["resolves_at"] = B + DUR_S * 1_000_000
    emit()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="binanceus", help="binance|binanceus|coinbase")
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--account", default="paper1")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    if args.live:
        pk = os.environ.get("PM_PRIVATE_KEY")
        if not pk:
            raise SystemExit("--live requires PM_PRIVATE_KEY in env (never logged)")
        creds = None
        if os.environ.get("PM_API_KEY"):
            creds = {"api_key": os.environ["PM_API_KEY"],
                     "api_secret": os.environ["PM_API_SECRET"],
                     "api_passphrase": os.environ["PM_API_PASSPHRASE"]}
        execu = pm.Executor(paper=False, private_key=pk, api_creds=creds)
    else:
        execu = pm.Executor(paper=True)

    feed = SpotFeed(args.venue)
    asyncio.create_task(feed.run())
    print(f"nix2 bot up: venue={args.venue} stake=${args.stake} "
          f"account={args.account} mode={'LIVE' if args.live else 'PAPER'}")
    print("warming up feed (~5 min for the 300s vol window)...")
    while True:
        try:
            await trade_window(feed, execu, args.stake, args.account, args.live)
        except Exception as e:
            print(f"[loop] {e}")
            await asyncio.sleep(2.0)


if __name__ == "__main__":
    asyncio.run(main())
