"""GATE 3 audits.

A) Look-ahead re-test: evaluate a sample of configs with the outcome vector
   shifted by one window — P&L must change materially for hold-to-expiry
   configs (payouts depend on outcomes; if results barely move, something is
   decoupled and leaking).
B) Evidence-chain audit: 25 random simulated trades re-derived end-to-end from
   the PROCESSED BOOKCURVE STORE independently of the engine's Matrix (fill
   price as-of T+latency from bookcurves, fee via src/fees, payout from
   windows.parquet outcome), compared to hand-arithmetic expectations.
Halts (nonzero exit) on any discrepancy.
"""
from __future__ import annotations

import json
import random
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
import fees
import loader
from engine import Matrix, evaluate

FAM = "5m"


def lookahead_retest(M: Matrix, n_cfg: int = 12) -> None:
    g = pl.read_parquet(f"results/grid_{FAM}_l250.parquet").filter(pl.col("train_n") > 300)
    rng = random.Random(3)
    sample = rng.sample(range(len(g)), n_cfg)
    changed = 0
    for i in sample:
        row = g.row(i, named=True)
        cfg = {"family": FAM, "offset": row["offset"], "entry": json.loads(row["entry"]),
               "side": row["side"], "exit": tuple(json.loads(row["exit"])),
               "notional": row["notional"], "latency": "l250", "tag": row["tag"]}
        base = evaluate(M, cfg)["train"]
        orig = M.up_won.copy()
        M.up_won = np.roll(M.up_won, 1)  # outcomes shifted one window
        shifted = evaluate(M, cfg)["train"]
        M.up_won = orig
        if base["n"] and abs(shifted["pnl"] - base["pnl"]) > 0.05 * max(abs(base["pnl"]), 100):
            changed += 1
    print(f"look-ahead retest: {changed}/{n_cfg} configs changed materially under shift")
    assert changed >= n_cfg * 0.8, "GATE3 FAIL: results insensitive to outcome shift"


def evidence_audit(M: Matrix, n_trades: int = 25) -> None:
    wins = pl.read_parquet("data/processed/windows.parquet").filter(pl.col("family") == FAM)
    won_map = dict(zip(wins["wts"].to_list(),
                       (wins["result_id"] == "0").cast(pl.Float64).to_list()))
    cfg = {"family": FAM, "offset": 60, "entry": [("pm_mid", ">", 0.55), ("pm_mid", "<", 0.70)],
           "side": "up", "exit": ("hold",), "notional": 200, "latency": "l250", "tag": "audit"}
    # engine's view
    off_i = M.off_idx[60]
    mask = ((M.cols["pm_mid"][:, off_i] > 0.55) & (M.cols["pm_mid"][:, off_i] < 0.70)
            & np.isfinite(M.cols["l250_buy_avgpx_200"][:, off_i])
            & (M.cols["buy_exhaust_200"][:, off_i] < 0.5))
    idxs = np.where(mask)[0]
    rng = random.Random(9)
    picks = rng.sample(list(idxs), n_trades)
    bad = 0
    for k in picks:
        w = int(M.uw[k])
        date = __import__("datetime").datetime.fromtimestamp(w, __import__("datetime").UTC).strftime("%Y-%m-%d")
        # independent rebuild from bookcurves
        b = (loader.load_daily(FAM, "bookcurves", [date])
             .filter(pl.col("wts") == w)
             .select("local_timestamp_us", "buy_avgpx_200").collect()
             .sort("local_timestamp_us"))
        T = (w + 60) * 1_000_000 + 250_000
        bb = b.filter(pl.col("local_timestamp_us") <= T)
        px_ind = float(bb["buy_avgpx_200"][-1])
        px_eng = float(M.cols["l250_buy_avgpx_200"][k, off_i])
        shares = 200.0 / px_ind
        rate = fees.params(date, FAM)[0]
        fee = shares * rate * px_ind * (1 - px_ind)
        payout = shares * won_map[w]
        pnl_ind = payout - 200.0 - fee
        # engine trade pnl
        e_shares = 200.0 / px_eng
        e_fee = e_shares * M.fee_rate[k] * px_eng * (1 - px_eng)
        pnl_eng = e_shares * M.up_won[k] - 200.0 - e_fee
        if abs(px_ind - px_eng) > 1e-4 or abs(pnl_ind - pnl_eng) > 0.05:
            bad += 1
            print(f"MISMATCH wts={w}: px {px_ind} vs {px_eng}, pnl {pnl_ind:.2f} vs {pnl_eng:.2f}")
    print(f"evidence audit: {n_trades} trades, {bad} mismatches")
    assert bad == 0, "GATE3 FAIL: evidence-chain mismatch"


if __name__ == "__main__":
    M = Matrix(FAM)
    lookahead_retest(M)
    evidence_audit(M)
    print("GATE 3 AUDITS PASS")
