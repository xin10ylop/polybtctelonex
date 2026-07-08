"""NIXULTIMATE judgment — all families, one deflated bar, no mercy.

Counts every config tested across the nix families, computes the deflated
significance bar sqrt(2 ln M), and lists any config that clears:
  val_n >= 300, train/fit t > 0, val t >= deflated bar.
The 15m last-seconds run is a single PRE-REGISTERED config (frozen nix1
params, market swap only) — its bar is t >= 3 on dev, then the one-shot
fresh-OOS check on Jul 6-7, same as nix1's protocol.
"""
from __future__ import annotations

import math
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")


def two_split(df: pl.DataFrame, keys: list[str], mask_expr, s1: str, s2: str) -> pl.DataFrame:
    rows = []
    for key, g in df.group_by(keys):
        r = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        for split, gg in ((s1, g.filter(mask_expr)), (s2, g.filter(~mask_expr))):
            p = gg["pnl"].to_numpy()
            n = len(p)
            r[f"{split}_n"] = n
            if n < 2:
                continue
            mu, sd = p.mean(), p.std(ddof=1)
            r[f"{split}_t"] = round(float(mu / (sd / np.sqrt(n))), 2) if sd > 0 else 0.0
            r[f"{split}_mean"] = round(float(mu), 4)
        rows.append(r)
    return pl.DataFrame(rows, infer_schema_length=None)


def main() -> None:
    fams = {}
    fams["straddle"] = two_split(pl.read_parquet("results/nix_straddle.parquet"),
                                 ["L", "t0", "tc"], pl.col("is_train"), "a", "b")
    fams["panic"] = two_split(pl.read_parquet("results/nix_panic.parquet"),
                              ["toff", "k", "side"], pl.col("is_train"), "a", "b")
    near = pl.read_parquet("results/nix_near.parquet")
    fams["near_pm"] = two_split(near.filter(pl.col("gate").str.starts_with("pm")),
                                ["gate", "toff", "B"],
                                pl.col("date") <= "2026-03-19", "a", "b")
    fams["near_hyb"] = two_split(near.filter(pl.col("gate").str.starts_with("hyb")),
                                 ["gate", "toff", "B"],
                                 pl.col("date") <= "2026-04-25", "a", "b")
    fams["xtf_maker"] = two_split(pl.read_parquet("results/nix_xtf_maker.parquet"),
                                  ["toff", "D", "g", "lvl", "H"],
                                  pl.col("is_train"), "a", "b")
    fams["quote"] = two_split(pl.read_parquet("results/nix_quote.parquet"),
                              ["toff", "dthr", "m", "H", "exit"], pl.col("fit"), "a", "b")
    grid = pl.read_parquet("results/nix_grid.parquet")
    M = sum(len(v) for v in fams.values()) + len(grid) + 1  # +1 = 15m lastsec
    bar = math.sqrt(2 * math.log(M))
    print(f"total NIXULTIMATE configs M = {M}; deflated bar = {bar:.2f}")
    surv = 0
    for name, lb in fams.items():
        s = lb.filter((pl.col("b_n") >= 300) & (pl.col("a_t") > 0) & (pl.col("b_t") >= bar))
        print(f"{name:10s}: {len(lb):4d} configs, survivors at bar: {len(s)}")
        surv += len(s)
        if len(s):
            print(s)
    gs = grid.filter((pl.col("val_n") >= 300) & (pl.col("train_t") > 0)
                     & (pl.col("val_t") >= bar))
    print(f"{'flow_grid':10s}: {len(grid):4d} configs, survivors at bar: {len(gs)}")
    surv += len(gs)
    if len(gs):
        print(gs.select("tag", "offset", "side", "exit", "entry", "train_t", "val_t"))
    print(f"\nTOTAL mined survivors: {surv}")
    try:
        m15 = pl.read_parquet("results/nix_15m_lastsec_dev.parquet")
        p = m15["pnl"].to_numpy()
        mu, sd = p.mean(), p.std(ddof=1)
        t = mu / (sd / np.sqrt(len(p)))
        print(f"\n15m lastsec (pre-registered, frozen): n={len(p)} mean=${mu:.2f} "
              f"t={t:.1f} wr={(p > 0).mean():.1%} -> "
              f"{'PASSES dev bar t>=3, eligible for fresh-OOS' if t >= 3 and len(p) >= 300 else 'needs n>=300 & t>=3: ' + ('FAIL' if t < 3 else f'n={len(p)}<300')}")
    except FileNotFoundError:
        print("15m lastsec: not yet run")


if __name__ == "__main__":
    main()
