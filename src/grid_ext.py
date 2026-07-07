"""Extension grid (user-requested pass, same discipline, thresholds unchanged):
  A) cross-timeframe: 5m decisions gated by the concurrent 15m market
  B) maker-ENTRY family: resting limit entries (fee-free), strict trade-through
     fills, hold to expiry — the fee wall does not apply to the entry leg
  C) exhaustive mined pass over the 4 new xtf features

$5-bet note: fills use the $50-bucket book-walk price, which upper-bounds the
cost of a $5 order; per-trade t-stats are scale-free, so these results bound
the $5 case exactly.

Output: results/grid_5m_ext.parquet (leaderboard schema).
"""
from __future__ import annotations

import glob
import itertools
import json
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
from engine import Matrix, evaluate, _fee

FAM = "5m"


def load_matrix() -> Matrix:
    M = Matrix(FAM)
    x = pl.concat([pl.read_parquet(p) for p in sorted(glob.glob("results/xtf/5m/*.parquet"))])
    x = x.sort("wts", "t_offset")
    # align to M's window set and offset layout
    base = pl.DataFrame({"wts": np.repeat(M.uw, len(M.offsets)),
                         "t_offset": np.tile(np.array(M.offsets), M.n)})
    x = base.join(x, on=["wts", "t_offset"], how="left")
    for c in ("xtf15_mid", "xtf15_vel60", "xtf15_align", "xtf15_t_rem"):
        M.cols[c] = x[c].to_numpy().astype(np.float64).reshape(M.n, len(M.offsets))
    return M


def eval_maker_entry(M: Matrix, cfg: dict) -> dict:
    """Maker-entry, hold-to-expiry. L in token space; fill = strict trade-through."""
    off = cfg["offset"]
    N = cfg["notional"]
    mask = np.ones(M.n, dtype=bool)
    for feat, op, thr in cfg["entry"]:
        v = M.col(feat, off)
        mask &= ((v > thr) if op == ">" else (v < thr)) & np.isfinite(v)
    dir_up = np.ones(M.n, dtype=bool) if cfg["side"] == "up" else np.zeros(M.n, dtype=bool)
    bid = M.col("pm_bid", off); ask = M.col("pm_ask", off)
    mid = (bid + ask) / 2
    lvl = cfg["level"]  # ("join",) | ("behind", cents) | ("mid_minus", cents)
    if lvl[0] == "join":
        L_up = bid
    elif lvl[0] == "behind":
        L_up = bid - lvl[1] / 100.0
    else:
        L_up = mid - lvl[1] / 100.0
    # token-space limit: long-up buys UP at L_up; long-down buys DOWN at (1-ask)-adj
    L = np.where(dir_up, L_up, (1.0 - ask) - (bid - L_up))
    mask &= np.isfinite(L) & (L > 0.01) & (L < 0.97)
    mn = M.col("min_tpx_after", off); mx = M.col("max_tpx_after", off)
    filled = np.where(dir_up, mn < L, mx > 1.0 - L) & np.isfinite(np.where(dir_up, mn, mx))
    mask &= filled
    shares = N / np.maximum(L, 1e-9)
    win = np.where(dir_up, M.up_won, 1.0 - M.up_won)
    pnl = shares * win - N  # maker entry: zero fee
    out = {"config": cfg, "n_total": int(mask.sum())}
    for split, sel in (("train", M.is_train & mask), ("val", (~M.is_train) & mask)):
        p = pnl[sel]; n = len(p)
        if n == 0:
            out[split] = {"n": 0}; continue
        mu = float(p.mean()); sd = float(p.std(ddof=1)) if n > 1 else 0.0
        cum = np.cumsum(p)
        out[split] = {"n": n, "pnl": round(float(p.sum()), 2), "mean": round(mu, 4),
                      "t": round(mu / (sd / np.sqrt(n)), 2) if sd > 0 else 0.0,
                      "pf": round(float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)), 3),
                      "wr": round(float((p > 0).mean()), 4),
                      "maxdd": round(float((np.maximum.accumulate(cum) - cum).max()), 2)}
    return out


def main() -> None:
    M = load_matrix()
    offs = [5, 30, 60, 150, 240]
    rows = []

    def record(res, tag, off, side, exit_s, entry, extra=""):
        flat = {"idx": len(rows), "family": FAM, "latency": "l250", "tag": tag,
                "offset": off, "side": side, "exit": exit_s, "notional": 200,
                "entry": json.dumps(entry) + extra}
        for split in ("train", "val"):
            for k, v in res[split].items():
                flat[f"{split}_{k}"] = v
        rows.append(flat)

    # A) structured cross-timeframe (taker, engine evaluator)
    for off in offs:
        for m_thr in (0.60, 0.65, 0.70):
            for gate in ([], [("dist_50", "<", 0.05), ("dist_50", ">", -0.05)]):
                for exit_ in (("hold",), ("maker", 3)):
                    for side, op, thr in (("up", ">", m_thr), ("down", "<", 1 - m_thr)):
                        entry = [("xtf15_mid", op, thr)] + gate
                        cfg = {"family": FAM, "offset": off, "entry": entry, "side": side,
                               "exit": exit_, "notional": 200, "latency": "l250", "tag": "xtf"}
                        record(evaluate(M, cfg), "xtf", off, side, json.dumps(list(exit_)), entry)
        for v_thr in (0.03, 0.06):
            for side, op, t_ in (("up", ">", v_thr), ("down", "<", -v_thr)):
                entry = [("xtf15_vel60", op, t_)]
                cfg = {"family": FAM, "offset": off, "entry": entry, "side": side,
                       "exit": ("hold",), "notional": 200, "latency": "l250", "tag": "xtf_vel"}
                record(evaluate(M, cfg), "xtf_vel", off, side, '["hold"]', entry)

    # C) mined pass over new features (train quantiles)
    for feat in ("xtf15_mid", "xtf15_vel60", "xtf15_align", "xtf15_t_rem"):
        arr = np.concatenate([M.cols[feat][M.is_train][:, M.off_idx[o]] for o in offs])
        arr = arr[np.isfinite(arr)]
        qs = np.unique(np.round(np.quantile(arr, [0.1, 0.25, 0.75, 0.9]), 6))
        for off, q, op, side in itertools.product(offs, qs, (">", "<"), ("up", "down")):
            entry = [(feat, op, float(q))]
            cfg = {"family": FAM, "offset": off, "entry": entry, "side": side,
                   "exit": ("hold",), "notional": 200, "latency": "l250", "tag": "xtf_mined"}
            record(evaluate(M, cfg), "xtf_mined", off, side, '["hold"]', entry)

    # B) maker-entry family
    gates = {"none": [], "fv": [("edge_vs_ask", ">", 0.0)],
             "xtf_agree_up": [("xtf15_mid", ">", 0.58)],
             "bret_up": [("bret_60s", ">", 0.0)]}
    for off in offs:
        for lvl in (("join",), ("behind", 1), ("mid_minus", 2), ("mid_minus", 3)):
            for gname, gate in gates.items():
                for side in ("up", "down"):
                    g = gate
                    if side == "down" and gname != "none":
                        g = [(f, "<" if op == ">" else ">", -t if f != "xtf15_mid" else 1 - t)
                             for f, op, t in gate]
                    cfg = {"family": FAM, "offset": off, "entry": g, "side": side,
                           "level": lvl, "notional": 200, "tag": f"maker_{gname}"}
                    res = eval_maker_entry(M, cfg)
                    record(res, f"maker_{gname}", off, side,
                           json.dumps(["maker_entry", list(lvl)]), g)

    df = pl.DataFrame(rows, infer_schema_length=None)
    df.write_parquet("results/grid_5m_ext.parquet")
    ok = df.filter(pl.col("val_n") >= 300)
    print(f"extension grid: {len(df)} configs; with val_n>=300: {len(ok)}")
    print(ok.sort("val_t", descending=True)
            .select("tag", "offset", "side", "exit", "train_n", "train_t", "train_pf",
                    "val_n", "val_t", "val_pf", "val_pnl").head(12))


if __name__ == "__main__":
    main()
