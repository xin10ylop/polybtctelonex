"""Pre-open strategy grid (user-specified shape, tested honestly).

Entry BEFORE window open (t_offset in {-30,-10,-3}) in a price band, with the
direction chosen by: nothing (blind), Binance candles (bret_60s/bret_300s
sign), the concurrent 15m market, the currently-resolving previous window's
live mid (follow or fade), or the last resolved window's outcome (follow or
fade). Exits: immediate resting maker sell at +3/+5/+8 cents (fee-free leg,
strict trade-through fills) or hold to expiry. Taker entry fees date-correct.
Also: a pre-open ML pass (logit+LGBM, walk-forward, isotonic) at the same
offsets. All results $-scale-free (bound the $5-bankroll case).

Output: results/grid_5m_preopen.parquet
"""
from __future__ import annotations

import glob
import json
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
from engine import Matrix, evaluate

BANDS = [(0.18, 0.22), (0.28, 0.32), (0.45, 0.55), (0.58, 0.62), (0.68, 0.72)]
NEG_OFFS = [-30, -10, -3]
EXITS = [("maker", 3), ("maker", 5), ("maker", 8), ("hold",)]


def load_matrix() -> Matrix:
    M = Matrix("5m")
    base = pl.DataFrame({"wts": np.repeat(M.uw, len(M.offsets)),
                         "t_offset": np.tile(np.array(M.offsets), M.n)})
    for pat, cols in (("results/preopen/5m/*.parquet", ["prior_live_mid", "prior2_up"]),
                      ("results/xtf/5m/*.parquet", ["xtf15_mid"])):
        x = pl.concat([pl.read_parquet(p) for p in sorted(glob.glob(pat))])
        x = base.join(x.sort("wts", "t_offset"), on=["wts", "t_offset"], how="left")
        for c in cols:
            M.cols[c] = x[c].to_numpy().astype(np.float64).reshape(M.n, len(M.offsets))
    return M


DIRS = {
    "blind_up": ("up", []),
    "blind_down": ("down", []),
    "binance_1m": ("sign:bret_60s", []),
    "binance_5m": ("sign:bret_300s", []),
    "m15_up": ("up", [("xtf15_mid", ">", 0.55)]),
    "m15_down": ("down", [("xtf15_mid", "<", 0.45)]),
    "prior_follow_up": ("up", [("prior_live_mid", ">", 0.65)]),
    "prior_follow_down": ("down", [("prior_live_mid", "<", 0.35)]),
    "prior_fade_up": ("up", [("prior_live_mid", "<", 0.35)]),
    "prior_fade_down": ("down", [("prior_live_mid", ">", 0.65)]),
    "prior2_follow": ("up", [("prior2_up", ">", 0.5)]),
    "prior2_fade": ("down", [("prior2_up", ">", 0.5)]),
}


def main() -> None:
    M = load_matrix()
    rows = []
    for off in NEG_OFFS:
        for lo, hi in BANDS:
            for dname, (side, gate) in DIRS.items():
                for exit_ in EXITS:
                    entry = [("pm_mid", ">", lo), ("pm_mid", "<", hi)] + gate
                    cfg = {"family": "5m", "offset": off, "entry": entry, "side": side,
                           "exit": exit_, "notional": 50, "latency": "l250",
                           "tag": f"preopen_{dname}"}
                    r = evaluate(M, cfg)
                    flat = {"idx": len(rows), "family": "5m", "latency": "l250",
                            "tag": f"preopen_{dname}", "offset": off, "side": side,
                            "exit": json.dumps(list(exit_)), "notional": 50,
                            "entry": json.dumps(entry)}
                    for split in ("train", "val"):
                        for k, v in r[split].items():
                            flat[f"{split}_{k}"] = v
                    rows.append(flat)
    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet("results/grid_5m_preopen.parquet")
    ok = df.filter(pl.col("val_n") >= 300)
    print(f"pre-open grid: {len(df)} configs; val_n>=300: {len(ok)}")
    print(ok.sort("val_t", descending=True)
            .select("tag", "offset", "exit", "train_n", "train_t", "train_pf",
                    "val_n", "val_t", "val_pf", "val_pnl").head(12))
    # data sanity: how often is the pre-open book even quoted at these offsets?
    for off in NEG_OFFS:
        m = M.col("pm_mid", off)
        print(f"offset {off}s: quoted books {np.isfinite(m).mean():.1%}, "
              f"median spread {np.nanmedian(M.col('pm_spread', off)):.3f}")


if __name__ == "__main__":
    main()
