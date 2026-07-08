"""NIXULTIMATE N2/N3 — crowd-flow & book-pressure grid through the engine.

Every config: entry gates on the nixflow columns (signed taker flow, whale
flow, quote/depth imbalance), follow AND fade covered by both ops x both
sides; exits hold / maker+3 / maker+5; date-correct fees on taker entries.
Includes the user's pre-open 45-55c band shape, now gated by PRE-MARKET
positioning flow (flow_open_imb at t-3s: who is loading up before the open).

Thresholds from train quantiles only. Notional 50 (upper-bounds the $5 fill).
Output: results/nix_grid.parquet (leaderboard schema).
"""
from __future__ import annotations

import glob
import itertools
import json
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
from engine import Matrix, evaluate

FEATS = ["flow_imb_10s", "flow_imb_30s", "flow_imb_60s", "flow_net_30s",
         "flow_open_imb", "nprints_30s", "big_imb_30s", "q_imb", "depth_imb"]
OFFS = [-30, -10, -3, 5, 30, 60, 150, 240]
EXITS = [("hold",), ("maker", 3), ("maker", 5)]


def load_matrix() -> Matrix:
    M = Matrix("5m")
    base = pl.DataFrame({"wts": np.repeat(M.uw, len(M.offsets)),
                         "t_offset": np.tile(np.array(M.offsets), M.n)})
    x = pl.concat([pl.read_parquet(p) for p in
                   sorted(glob.glob("results/nixflow/5m/*.parquet"))])
    x = base.join(x.sort("wts", "t_offset"), on=["wts", "t_offset"], how="left")
    for c in FEATS:
        M.cols[c] = x[c].to_numpy().astype(np.float64).reshape(M.n, len(M.offsets))
    return M


def main() -> None:
    M = load_matrix()
    rows = []

    def record(res, tag, off, side, exit_, entry):
        flat = {"idx": len(rows), "family": "5m", "latency": "l250", "tag": tag,
                "offset": off, "side": side, "exit": json.dumps(list(exit_)),
                "notional": 50, "entry": json.dumps(entry)}
        for split in ("train", "val"):
            for k, v in res[split].items():
                flat[f"{split}_{k}"] = v
        rows.append(flat)

    # mined pass: train-quantile thresholds, both ops, both sides
    for feat in FEATS:
        arr = np.concatenate([M.cols[feat][M.is_train][:, M.off_idx[o]] for o in OFFS])
        arr = arr[np.isfinite(arr)]
        if len(arr) < 1000:
            continue
        qs = np.unique(np.round(np.quantile(arr, [0.1, 0.9]), 6))
        for off, q, op, side, exit_ in itertools.product(
                OFFS, qs, (">", "<"), ("up", "down"), EXITS):
            entry = [(feat, op, float(q))]
            cfg = {"family": "5m", "offset": off, "entry": entry, "side": side,
                   "exit": exit_, "notional": 50, "latency": "l250", "tag": "nixflow"}
            record(evaluate(M, cfg), "nixflow", off, side, exit_, entry)

    # user's shape: pre-open 45-55c band, gated by pre-market flow direction
    for off in (-30, -10, -3):
        for fthr in (0.2, 0.5):
            for exit_ in EXITS:
                for side, op, t in (("up", ">", fthr), ("down", "<", -fthr)):
                    entry = [("pm_mid", ">", 0.45), ("pm_mid", "<", 0.55),
                             ("flow_open_imb", op, t)]
                    cfg = {"family": "5m", "offset": off, "entry": entry,
                           "side": side, "exit": exit_, "notional": 50,
                           "latency": "l250", "tag": "preopen_flow"}
                    record(evaluate(M, cfg), "preopen_flow", off, side, exit_, entry)
                    # whale variant
                    entry2 = [("pm_mid", ">", 0.45), ("pm_mid", "<", 0.55),
                              ("big_imb_30s", op, t)]
                    cfg2 = dict(cfg, entry=entry2, tag="preopen_whale")
                    record(evaluate(M, cfg2), "preopen_whale", off, side, exit_, entry2)

    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet("results/nix_grid.parquet")
    ok = df.filter(pl.col("val_n") >= 300)
    print(f"nix grid: {len(df)} configs; val_n>=300: {len(ok)}")
    pl.Config.set_tbl_cols(14)
    print(ok.sort("val_t", descending=True)
            .select("tag", "offset", "side", "exit", "entry", "train_n", "train_t",
                    "val_n", "val_t", "val_pnl", "val_wr").head(20))


if __name__ == "__main__":
    main()
