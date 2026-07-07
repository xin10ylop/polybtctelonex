"""Fine-grained per-cent entry bands + optimistic maker fill (user request).
Entry at each cent 0.47..0.53 (band +-0.5c), pre-open AND early in-window,
direction from blind/Binance/prior-window/15m, maker exit +3/+5c under BOTH
the conservative (strict trade-through) and OPTIMISTIC (price merely touches L)
fill rules. If it loses even optimistically, the door is fully closed.
Output: results/grid_5m_fine.parquet
"""
import sys, json, glob
import numpy as np, polars as pl
sys.path.insert(0, "src")
from grid_preopen import load_matrix

M = load_matrix()
M.cols["xtf15_align"] = M.cols["xtf15_mid"] - 0.5
CENTS = [0.47, 0.48, 0.49, 0.50, 0.51, 0.52, 0.53]
OFFS = [-10, -3, 5, 20, 60]
DELTAS = [3, 5]

def eval_fine(cfg, optimistic):
    off = cfg["offset"]; N = 50
    i = M.off_idx[off]
    mid = M.cols["pm_mid"][:, i]
    lo, hi = cfg["band"]
    mask = np.isfinite(mid) & (mid >= lo) & (mid < hi)
    for feat, op, thr in cfg["gate"]:
        v = M.cols[feat][:, i]
        mask &= ((v > thr) if op == ">" else (v < thr)) & np.isfinite(v)
    side = cfg["side"]
    if side == "up":   dir_up = np.ones(M.n, bool)
    elif side == "down": dir_up = np.zeros(M.n, bool)
    else:
        sv = M.cols[side.split(":")[1]][:, i]; dir_up = sv > 0; mask &= np.isfinite(sv) & (sv != 0)
    buy = M.cols[f"l250_buy_avgpx_{N}"][:, i]; sell = M.cols[f"l250_sell_avgpx_{N}"][:, i]
    entry = np.where(dir_up, buy, 1.0 - sell)
    mask &= np.isfinite(entry) & (entry > 0.02) & (entry < 0.98)
    shares = N / np.maximum(entry, 1e-9)
    win = np.where(dir_up, M.up_won, 1.0 - M.up_won)
    fee_in = shares * M.fee_rate * entry * (1 - entry)
    hold = shares * win - N - fee_in
    delta = cfg["delta"] / 100.0
    L = entry + delta
    mx = M.cols["max_tpx_after"][:, i]; mn = M.cols["min_tpx_after"][:, i]
    tok_hi = np.where(dir_up, mx, 1.0 - mn)   # best token price traded after entry
    if optimistic:
        filled = tok_hi >= L - 1e-9           # touch fills
    else:
        filled = tok_hi > L                   # strict trade-through
    filled &= np.isfinite(tok_hi) & (L < 0.99)
    maker_pnl = shares * delta - fee_in
    pnl = np.where(filled, maker_pnl, hold)
    out = {}
    for split, sel in (("train", M.is_train & mask), ("val", (~M.is_train) & mask)):
        p = pnl[sel]; n = len(p)
        if n == 0: out[split] = {"n": 0}; continue
        mu = float(p.mean()); sd = float(p.std(ddof=1)) if n > 1 else 0.0
        out[split] = {"n": n, "pnl": round(float(p.sum()),2), "mean": round(mu,4),
                      "t": round(mu/(sd/np.sqrt(n)),2) if sd>0 else 0.0,
                      "pf": round(float(p[p>0].sum()/max(-p[p<0].sum(),1e-9)),3),
                      "wr": round(float((p>0).mean()),4),
                      "fill": round(float(filled[sel].mean()),3)}
    return out

DIRS = {"blind_up":("up",[]), "blind_down":("down",[]),
        "binance1m":("sign:bret_60s",[]), "binance5m":("sign:bret_300s",[]),
        "prior_follow":("up",[("prior_live_mid",">",0.6)]),
        "prior_fade":("down",[("prior_live_mid",">",0.6)]),
        "m15":("sign:xtf15_align",[])}
rows=[]
for opt in (False, True):
    for off in OFFS:
        for c in CENTS:
            band=(c-0.005, c+0.005)
            for dname,(side,gate) in DIRS.items():
                for d in DELTAS:
                    cfg={"offset":off,"band":band,"side":side,"gate":gate,"delta":d}
                    r=eval_fine(cfg, opt)
                    flat={"opt":opt,"off":off,"cent":c,"dir":dname,"delta":d}
                    for s in ("train","val"):
                        for k,v in r[s].items(): flat[f"{s}_{k}"]=v
                    rows.append(flat)
df=pl.DataFrame(rows, infer_schema_length=None)
df.write_parquet("results/grid_5m_fine.parquet")
ok=df.filter((pl.col("val_n")>=300))
print(f"fine grid: {len(df)} configs ({len(ok)} with val_n>=300)")
print("--- OPTIMISTIC fill, sorted by val_t ---")
print(ok.filter(pl.col("opt")).sort("val_t",descending=True).select("off","cent","dir","delta","val_n","val_fill","val_wr","val_t","val_pf","val_pnl").head(12))
print("--- CONSERVATIVE fill, best ---")
print(ok.filter(~pl.col("opt")).sort("val_t",descending=True).select("off","cent","dir","delta","val_n","val_fill","val_wr","val_t","val_pf","val_pnl").head(6))
