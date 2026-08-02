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
WALK_MAX_PX = 0.55       # v3: refuse a walk that climbs past this
FILL_OFF_US = -250_000   # fill 0.25s before open
DUR_S = 300


async def _io(fn, *a, timeout: float = 8.0):
    """Run a blocking urllib call off the event loop under a HARD timeout.

    pm.* use urllib, whose `timeout=` covers socket reads but NOT DNS
    resolution — getaddrinfo can block forever. Called synchronously inside a
    coroutine that also freezes the price feed, and systemd cannot see it
    (the process stays alive and healthy), so Restart=always never fires.
    On 2026-08-02 all four bots froze on the same second this way and sat
    dead for 8h with Result=success/NRestarts=0.
    """
    return await asyncio.wait_for(asyncio.to_thread(fn, *a), timeout=timeout)


def next_boundary_us(now_us: int) -> int:
    """Next 5-minute UTC boundary strictly after now."""
    step = 300_000_000
    return ((now_us // step) + 1) * step


def log(account: str, rec: dict) -> None:
    os.makedirs("logs", exist_ok=True)
    with open(f"logs/nix2_live_{account}.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


async def trade_window(feed: SpotFeed, execu: pm.Executor, stake: float,
                       account: str, live: bool, B: int,
                       qimb_max: float | None = None, walk: bool = False,
                       realistic: bool = False, slip_ticks: int = 1) -> None:
    T0 = B + T0_OFF_US
    # sleep until decision time (0.5s before open)
    await asyncio.sleep(max(0.0, (T0 - int(time.time() * 1_000_000)) / 1e6))
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
        mkt = await _io(pm.find_btc_5m_market, B)
    except Exception as e:
        return emit(f"discover_err:{e}")
    if not mkt:
        return emit("no_market")
    token = mkt["up_token"] if side == "up" else mkt["down_token"]
    bs = await _io(pm.book_summary, token)
    ask = bs["ask"] if bs else None
    depth = bs["ask_usd"] if bs else 0.0
    q_imb = bs.get("q_imb") if bs else None
    rec.update({"slug": mkt["slug"], "ask": ask, "depth_usd": round(depth, 1),
                "q_imb": q_imb, "stake": stake})
    if ask is None:
        return emit("no_book")
    if not (Z_MIN <= abs(z) < Z_MAX):
        return emit("z_gate")
    if not (ASK_MIN <= ask <= ASK_MAX):
        return emit("ask_gate")
    if stake < mkt["min_size"]:
        return emit("below_min_size")
    # fill price: touch (v1/v2) or walk the ladder (v3 — keeps thin windows
    # tradeable, which is what lets stakes above ~$10 scale; fill audit)
    fill_px = ask
    if walk:
        wp, filled = pm.walk_price(bs.get("_asks") or [], stake)
        if not (wp == wp) or filled < stake * 0.99:
            return emit("cant_fill")
        if wp > WALK_MAX_PX:
            return emit("walk_too_deep")
        fill_px = round(wp, 4)
        rec["walk_px"] = fill_px
    elif depth < stake:
        return emit("thin_book")
    if qimb_max is not None and (q_imb is None or q_imb >= qimb_max):
        return emit("qimb_gate")   # v2: require book leaning AWAY (q_imb < max)

    # ---- execution ----
    await asyncio.sleep(max(0.0, (B + FILL_OFF_US - int(time.time() * 1e6)) / 1e6))
    if realistic:
        # Honest simulation: our order arrives AFTER the decision, so fill it
        # against the book as it is THEN, as a marketable limit (observed ask
        # + slip tolerance). The book can have moved away -> partial or no
        # fill. Anything else silently assumes the liquidity waited for us.
        bs2 = await _io(pm.book_summary, token)
        if not bs2 or not bs2.get("_asks"):
            return emit("fill_no_book")
        limit = round(ask + slip_ticks * mkt["tick"], 4)
        avg, filled = pm.walk_price(bs2["_asks"], stake, limit_px=limit)
        rec["limit_px"] = limit
        rec["ask_at_fill"] = bs2["ask"]
        if filled < mkt["min_size"]:
            return emit("unfilled", filled_usd=round(filled, 2))
        fill_px, spent = round(avg, 4), round(filled, 2)
        if spent < stake * 0.99:
            rec["partial"] = True
    else:
        spent = stake

    rec["decision"] = "TRADE"
    rec["fill"] = execu.buy(token, fill_px, spent, mkt["tick"])
    rec["fill"]["spent"] = spent
    rec["fill"]["intended"] = stake
    rec["resolves_at"] = B + DUR_S * 1_000_000
    emit()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", default="binanceus", help="binance|binanceus|coinbase")
    ap.add_argument("--stake", type=float, default=10.0)
    ap.add_argument("--walk", action="store_true",
                    help="v3: fill by walking the ask ladder instead of "
                         "skipping thin books (needed to scale past ~$10)")
    ap.add_argument("--realistic", action="store_true",
                    help="honest execution: re-fetch the book at fill time and "
                         "fill as a marketable limit (partial/no fill possible)")
    ap.add_argument("--slip-ticks", type=int, default=1,
                    help="how many cents above the observed ask the limit sits")
    ap.add_argument("--qimb-max", type=float, default=None,
                    help="v2 gate: only trade if signal-side book q_imb < this "
                         "(e.g. -0.05 = book must lean away). Default off (v1).")
    ap.add_argument("--account", default="paper1")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    if args.live:
        # ------------------------------------------------------------------
        # LIVE IS LOCKED. An independent audit (2026-08-02) found the live
        # path has never been exercised end-to-end and cannot work as written.
        # Unlocking requires fixing these and re-auditing — not just deleting
        # this guard. See reports/mc_campaign_notes.md "LIVE-PATH AUDIT".
        #   1 AUTH: post_order needs L2 API creds; they are treated as
        #     optional and never derived -> every order raises.
        #   2 WALLET: ClobClient built with no signature_type/funder -> EOA
        #     signing, but funded accounts normally hold USDC in a proxy
        #     wallet; orders rejected for balance/allowance.
        #   3 RECORDS: execu.buy() is unguarded and never inspects the
        #     response; the loop's blanket except swallows failures, so
        #     killed orders vanish and unfilled ones are scored as fills.
        #   4 ORDER TYPE: live posts FOK (all-or-nothing) while the paper sim
        #     models PARTIAL fills -> paper4's partials are impossible live,
        #     and the FOK limit is the walk average (can round below the
        #     level the walk consumed, killing otherwise-fillable orders).
        #   5 RISK: bot/live/risk.py is NOT wired into this file at all;
        #     a real-money run would have no drawdown/decay/streak halts and
        #     no bankroll-based sizing.
        #   + no redemption of winning CTF tokens (bankroll drains in EOA
        #     mode), no crash reconciliation, ~250-700ms of unmodelled order
        #     latency that pushes the fill past the boundary.
        # AND: the pre-registered forward test is NOT passing (t 1.37 -> 1.12
        # -> 0.92 against a 2.0 bar), so there is nothing to deploy yet.
        # ------------------------------------------------------------------
        raise SystemExit(
            "--live is LOCKED. The live order path is unaudited and known "
            "broken (auth, wallet mode, order type, record-keeping, no risk "
            "controls) and the forward test has not passed its bar. "
            "See the comment above this guard in bot/live/nix2_live.py.")
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
    last_B = 0
    last_ok = time.time()
    while True:
        try:
            # WATCHDOG: a hang that leaves the process alive is invisible to
            # systemd. If three windows pass with no completed decision, exit
            # non-zero and let Restart=always recover us.
            if time.time() - last_ok > 3 * (DUR_S + 30):
                raise SystemExit(
                    f"watchdog: no completed window in "
                    f"{int(time.time() - last_ok)}s — exiting for restart")
            now = int(time.time() * 1_000_000)
            B = next_boundary_us(now)
            if B == last_B:                       # already handled this window
                await asyncio.sleep(max(0.5, (B + 1_000_000 - now) / 1e6))
                continue
            last_B = B
            await trade_window(feed, execu, args.stake, args.account, args.live,
                               B, args.qimb_max, args.walk,
                               args.realistic, args.slip_ticks)
            last_ok = time.time()
        except SystemExit:
            raise
        except Exception as e:
            print(f"[loop] {e}")
            await asyncio.sleep(2.0)


if __name__ == "__main__":
    asyncio.run(main())
