"""Phase 3 strategy grid — exhaustive programmatic enumeration + evaluation.

Families (run brief floor): fair-value EV taker/maker-exit, lead-lag/latency,
momentum, odds mean-reversion, legacy price-level entries, cross-feature
signal-mining pass (EVERY feature x quantile-threshold grid x direction x
offsets), streak control. ML family runs separately (phase3_ml.py) and joins
the same leaderboard. Sizing beyond flat-$N is applied to survivor trade
sequences in Phase 4 (equivalent per-trade economics).

Usage: python src/grid.py <family> [--latency l250] -> results/grid_{family}_{lat}.parquet
Threshold grids use TRAIN quantiles only (no validation peeking).
"""
from __future__ import annotations

import itertools
import json
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
from engine import Matrix, evaluate
from features import OFFSETS

MINED_FEATURES = [
    "bret_1s", "bret_5s", "bret_15s", "bret_60s", "bret_300s", "bret_900s",
    "ofi_10s", "ofi_60s", "intensity_60s", "vwap_dev_60s", "rvol_60s", "rvol_300s",
    "odds_vel_1s", "odds_vel_5s", "odds_vel_15s", "odds_vel_60s",
    "book_imb", "pm_spread", "pm_vol_sofar", "dist_50", "streak", "prior_up",
    "cl_delta_from_open", "fair_value_gauss", "edge_vs_ask",
]
Q = [0.1, 0.25, 0.75, 0.9]


def mining_offsets(fam):
    return {"5m": [5, 30, 60, 150, 240], "15m": [10, 60, 300, 660]}[fam]


def build_configs(M: Matrix, family: str, latency: str) -> list[dict]:
    cfgs: list[dict] = []
    offs = mining_offsets(family)
    exits = {"5m": [("hold",), ("maker", 3), ("maker", 5)],
             "15m": [("hold",), ("maker", 3), ("maker", 5)]}[family]
    tx_exits = {"5m": [("taker", 240), ("taker", 285)],
                "15m": [("taker", 660), ("taker", 840)]}[family]

    def add(entry, side, off, exit_, N=200, fam_tag=""):
        cfgs.append({"family": family, "offset": off, "entry": entry, "side": side,
                     "exit": exit_, "notional": N, "latency": latency, "tag": fam_tag})

    # ---- family 1/2: fair value EV (taker entry; hold / maker / taker exits)
    for off in offs:
        for thr in (0.02, 0.04, 0.07, 0.10):
            for exit_ in exits + tx_exits:
                add([("edge_vs_ask", ">", thr)], "up", off, exit_, fam_tag="fv")
                # symmetric down side: fair value below bid by thr
                add([("fair_value_gauss", "<", 0.5), ("edge_vs_ask", "<", -thr)],
                    "down", off, exit_, fam_tag="fv")

    # ---- family 3: lead-lag / latency (Binance moved, odds quiet)
    for off in offs:
        for bthr in (0.0003, 0.0007, 0.0015):
            for vel_cap in (0.01, 0.02):
                for exit_ in [("hold",), ("maker", 3)] + tx_exits[:1]:
                    add([("bret_5s", ">", bthr), ("odds_vel_5s", "<", vel_cap)],
                        "up", off, exit_, fam_tag="leadlag")
                    add([("bret_5s", "<", -bthr), ("odds_vel_5s", ">", -vel_cap)],
                        "down", off, exit_, fam_tag="leadlag")

    # ---- family 4/5: odds momentum and mean-reversion
    for off in offs:
        for vthr in (0.02, 0.05, 0.10):
            for exit_ in exits:
                add([("odds_vel_15s", ">", vthr)], "up", off, exit_, fam_tag="mom")
                add([("odds_vel_15s", "<", -vthr)], "down", off, exit_, fam_tag="mom")
                add([("odds_vel_15s", ">", vthr)], "down", off, exit_, fam_tag="mrev")
                add([("odds_vel_15s", "<", -vthr)], "up", off, exit_, fam_tag="mrev")

    # ---- family 6: legacy price-level entries (blind + signal-gated)
    lvl_bands = [(0.18, 0.22), (0.28, 0.32), (0.48, 0.52), (0.58, 0.62), (0.68, 0.72)]
    for off in offs[:3]:
        for lo, hi in lvl_bands:
            for exit_ in exits + tx_exits[:1]:
                add([("pm_mid", ">", lo), ("pm_mid", "<", hi)], "up", off, exit_,
                    fam_tag="legacy_blind")
                add([("pm_mid", ">", lo), ("pm_mid", "<", hi)], "sign:bret_60s",
                    off, exit_, fam_tag="legacy_gated")
                add([("pm_mid", ">", lo), ("pm_mid", "<", hi),
                     ("edge_vs_ask", ">", 0.02)], "up", off, exit_, fam_tag="legacy_fv")

    # ---- family 8: calibration-pocket (favorites 0.55-0.70 underpriced, Phase 1)
    for off in offs:
        for exit_ in exits:
            add([("pm_mid", ">", 0.55), ("pm_mid", "<", 0.70)], "up", off, exit_,
                fam_tag="calib_pocket")

    # ---- streak control (Phase 1 says anti-persistent -> fade prior)
    for off in offs[:3]:
        add([("prior_up", ">", 0.5)], "down", off, ("hold",), fam_tag="antistreak")
        add([("prior_up", "<", 0.5)], "up", off, ("hold",), fam_tag="antistreak")
        add([("prior_up", ">", 0.5)], "up", off, ("hold",), fam_tag="streak_ctl")
        add([("prior_up", "<", 0.5)], "down", off, ("hold",), fam_tag="streak_ctl")

    # ---- exhaustive signal-mining pass: EVERY feature x quantile grid x dir
    for feat in MINED_FEATURES:
        arr = np.concatenate([M.cols[feat][M.is_train][:, M.off_idx[o]] for o in offs])
        arr = arr[np.isfinite(arr)]
        if len(arr) < 1000:
            continue
        qs = np.unique(np.round(np.quantile(arr, Q), 6))
        for off, q, op, side in itertools.product(offs, qs, (">", "<"), ("up", "down")):
            add([(feat, op, float(q))], side, off, ("hold",), fam_tag="mined")

    # notional variants for capacity on a subset (fv + leadlag + pocket)
    extra = [dict(c, notional=N) for c in cfgs
             if c["tag"] in ("fv", "leadlag", "calib_pocket") for N in (50, 1000)]
    return cfgs + extra


def main() -> None:
    family = sys.argv[1]
    latency = sys.argv[2] if len(sys.argv) > 2 else "l250"
    M = Matrix(family)
    cfgs = build_configs(M, family, latency)
    print(f"{family}/{latency}: {len(cfgs)} configs over {M.n:,} windows", flush=True)
    rows = []
    for i, cfg in enumerate(cfgs):
        r = evaluate(M, cfg)
        flat = {"idx": i, "family": family, "latency": latency, "tag": cfg["tag"],
                "offset": cfg["offset"], "side": cfg["side"],
                "exit": json.dumps(cfg["exit"]), "notional": cfg["notional"],
                "entry": json.dumps(cfg["entry"])}
        for split in ("train", "val"):
            for k, v in r[split].items():
                flat[f"{split}_{k}"] = v
        rows.append(flat)
        if (i + 1) % 2000 == 0:
            print(f"  {i+1} done", flush=True)
    out = f"results/grid_{family}_{latency}.parquet"
    pl.DataFrame(rows, infer_schema_length=None).write_parquet(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
