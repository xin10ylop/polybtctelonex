"""Calibrate + validate the nix2 risk engine's kill switches against history.

A kill switch is only useful if it (a) essentially never fires during a
genuinely profitable regime — a false halt costs you the whole edge — and
(b) fires promptly once the edge actually dies. This measures both:

  FALSE-POSITIVE test: replay the profitable Feb-May cell through the engine.
                       Any halt is a false alarm.
  TRUE-POSITIVE test:  replay a synthetic dead regime (same trades, EV forced
                       to zero and to negative) and measure how many trades
                       it takes the decay detector to halt.
  Also: bootstrap the distribution of worst drawdown and longest losing
  streak, so the thresholds sit far outside normal variation.
"""
from __future__ import annotations

import sys

import numpy as np
import polars as pl

sys.path.insert(0, "bot/live")
from risk import RiskConfig, RiskEngine   # noqa: E402

STAKE = 10.0


def load_pnl() -> tuple[np.ndarray, list[str]]:
    d = pl.read_parquet("results/nix_fillaudit_rows.parquet")
    a0 = d["ask_t0"].to_numpy()
    gate = (a0 >= 0.44) & (a0 <= 0.4999)
    ask = d["ask_250ms"].to_numpy().astype(np.float64)
    dep = d["dep_250ms"].to_numpy().astype(np.float64)
    m = gate & np.isfinite(ask) & (dep >= STAKE)
    win = d["win"].to_numpy().astype(float)[m]
    rate = d["rate"].to_numpy()[m]
    a = ask[m]
    sh = STAKE / a
    pnl = sh * win - STAKE - rate * a * (1 - a) * sh
    return pnl, list(d["date"].to_numpy()[m])


def replay(pnl: np.ndarray, days: list[str], cfg: RiskConfig) -> dict:
    e = RiskEngine(cfg=cfg)
    halted_at = None
    traded = 0
    for i, (p, day) in enumerate(zip(pnl, days)):
        ok, _ = e.may_trade(day)
        if not ok:
            if e.state == "HALTED" and halted_at is None:
                halted_at = i
            continue
        e.record(float(p), STAKE, day)
        traded += 1
    if e.state == "HALTED" and halted_at is None:
        halted_at = len(pnl)
    return {"state": e.state, "reason": e.reason, "halted_at": halted_at,
            "traded": traded, "equity": e.equity}


def main() -> None:
    pnl, days = load_pnl()
    print(f"historical profitable cell: {len(pnl)} trades, "
          f"EV ${pnl.mean():+.3f}, total ${pnl.sum():+.0f}\n")

    cfg = RiskConfig()
    print("=== 1. FALSE-POSITIVE TEST (replay the PROFITABLE regime) ===")
    r = replay(pnl, days, cfg)
    print(f"  final state: {r['state']}  {r['reason']}")
    print(f"  traded {r['traded']}/{len(pnl)}, equity ${r['equity']:+.0f}")
    print(f"  -> {'PASS: no false halt' if r['state'] != 'HALTED' else 'FAIL: halted a winning strategy'}")

    print("\n=== 2. TRUE-POSITIVE TEST (edge dies — how fast do we stop?) ===")
    rng = np.random.default_rng(7)
    for shift, label in ((-pnl.mean(), "EV -> exactly zero"),
                         (-pnl.mean() - 0.5, "EV -> -$0.50/trade"),
                         (-pnl.mean() - 1.0, "EV -> -$1.00/trade")):
        stops = []; reasons = []
        for _ in range(200):
            idx = rng.permutation(len(pnl))
            dead = pnl[idx] + shift
            dd = [days[i] for i in idx]
            rr = replay(dead, dd, RiskConfig())
            stops.append(rr["halted_at"] if rr["state"] == "HALTED" else len(pnl))
            reasons.append(rr["reason"] if rr["state"] == "HALTED" else "")
        stops = np.array(stops)
        halted = np.mean(stops < len(pnl))
        why = {}
        for r_ in reasons:
            k = r_.split(":")[0] if r_ else "none"
            why[k] = why.get(k, 0) + 1
        top = sorted(why.items(), key=lambda kv: -kv[1])[:2]
        print(f"  {label:<22} halts in {halted:>4.0%} of runs, "
              f"median after {np.median(stops):.0f} trades  via {top}")

    print("\n=== 3. NATURAL VARIATION (bootstrap: is the threshold far enough out?) ===")
    dds, streaks = [], []
    for _ in range(2000):
        s = pnl[rng.integers(0, len(pnl), len(pnl))]
        eq = np.cumsum(s)
        dds.append((np.maximum.accumulate(eq) - eq).max())
        r_, c_ = 0, 0
        for x in s:
            if x < 0:
                c_ += 1; r_ = max(r_, c_)
            else:
                c_ = 0
        streaks.append(r_)
    dds = np.array(dds) / STAKE
    streaks = np.array(streaks)
    halt_stakes = cfg.max_drawdown_frac * cfg.bankroll / (cfg.stake_fraction * cfg.bankroll)
    print(f"  drawdown (in stakes): median {np.median(dds):.0f}  p95 {np.percentile(dds,95):.0f}  "
          f"p99 {np.percentile(dds,99):.0f}  | halt at {halt_stakes:.0f} stakes"
          f"  -> fires {np.mean(dds>=halt_stakes):.1%} of the time when edge is ALIVE")
    print(f"  losing streak: median {np.median(streaks):.0f}  p95 {np.percentile(streaks,95):.0f}  "
          f"p99 {np.percentile(streaks,99):.0f}  | halt at {cfg.consecutive_losses}"
          f"  -> fires {np.mean(streaks>=cfg.consecutive_losses):.1%} when alive")

    print("\n=== 4. SIZING under this config ===")
    for bank in (200, 500, 1000, 2000):
        c2 = RiskConfig(bankroll=bank); e = RiskEngine(cfg=c2)
        print(f"  bankroll ${bank:>5}: stake ${e.stake():>6.2f}   halt at "
              f"${c2.max_drawdown_frac*bank:.0f} drawdown "
              f"({c2.max_drawdown_frac*bank/e.stake():.0f} stakes)")
    print("\nRISKCAL DONE")


if __name__ == "__main__":
    main()
