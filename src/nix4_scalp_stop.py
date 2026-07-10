"""NIX4 — the user's pre-open scalp, explored deeply (task #4).

Structure: buy Up or Down at <= band cents, 3-30s BEFORE window open; rest a
sell limit at entry+target; exit rules: (a) hold to expiry if unfilled
(original), (b) STOP — if the limit hasn't filled by +X seconds after open,
taker-sell everything at the then-current book (user's risk-engine idea),
X in {5,10,20,30}s.

Direction sources compared head-to-head on identical entries:
  ml@tau     — calibrated walk-forward P(up) from JOB A (results/nix4/preds_*)
  blind_up / blind_dn — the user's "guessing"
  prior_follow / prior_fade — previous window's outcome
  bmom       — sign of Binance 60s return at decision time

Fill realism: entries bracketed cons ($50 book-walk) / opt (top-of-book);
maker exit = strict trade-through (a print beyond limit by >= 1 tick);
stop fills at the +X book (walk / tob by convention) and pays a second
taker fee. When the tape is ambiguous about WHEN the limit was touched
(touched both before and after +X), both brackets are reported:
stop*_opt (assume filled before stop) / stop*_pess (assume stopped).

All P&L at $5 stakes, date-correct fees. TRAIN <= 2026-03-19 / VAL after.
Usage: .venv/bin/python src/nix4_scalp_stop.py
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import polars as pl

sys.path.insert(0, "src")
from nix4_btc_deep import load_fam, TRAIN_END, VAL_END  # noqa: E402

ENTRY_OFF = [-30, -10, -3]
STOP_OFF = [5, 10, 20, 30]
BANDS = [0.47, 0.48, 0.49, 0.50, 0.51, 0.52, 0.53]
TARGETS = [0.03, 0.04, 0.05]
TAUS = [0.50, 0.52, 0.55, 0.60, 0.65]
STAKE = 5.0
TICK = 0.01


def build(fam: str):
    df = load_fam(fam).filter(pl.col("date") <= VAL_END)
    preds = pl.read_parquet(f"results/nix4/preds_{fam}_preopen.parquet")
    df = df.join(preds.select("wts", "t_offset", "p_hat"),
                 on=["wts", "t_offset"], how="left")
    # stop-state per window: book + tape extremes at +X after open
    stop_cols = {}
    for X in STOP_OFF:
        s = (df.filter(pl.col("t_offset") == X)
               .select("wts",
                       pl.col("pm_bid").alias(f"bid_{X}"),
                       pl.col("pm_ask").alias(f"ask_{X}"),
                       pl.col("l250_sell_avgpx_50").alias(f"wsell_{X}"),
                       pl.col("l250_buy_avgpx_50").alias(f"wbuy_{X}"),
                       pl.col("max_tpx_after").alias(f"maxa_{X}"),
                       pl.col("min_tpx_after").alias(f"mina_{X}")))
        stop_cols[X] = s
    ent = df.filter(pl.col("t_offset").is_in(ENTRY_OFF))
    for X in STOP_OFF:
        ent = ent.join(stop_cols[X], on="wts", how="left")
    return ent


def sim_fam(fam: str, lines: list[str]) -> pl.DataFrame:
    ent = build(fam)
    n = ent.height
    g = lambda c: ent[c].to_numpy().astype(np.float64)
    up_won = ent["up_won"].to_numpy().astype(bool)
    rate = g("rate")
    toff = ent["t_offset"].to_numpy()
    split = np.where(ent["date"].to_numpy() <= TRAIN_END, "TRAIN", "VAL")
    date_arr = ent["date"].to_numpy()
    p_hat = g("p_hat")
    prior_up = g("prior_up")
    bmom = g("bret_60")

    # entry prices per side x conv
    entry = {("up", "cons"): g("l250_buy_avgpx_50"),
             ("dn", "cons"): 1 - g("l250_sell_avgpx_50"),
             ("up", "opt"): g("pm_ask"),
             ("dn", "opt"): 1 - g("pm_bid")}
    # tape extremes in OWN-side price space ("max after" for the held token)
    max_ent = {"up": g("max_tpx_after"), "dn": 1 - g("min_tpx_after")}
    max_stop = {("up", X): g(f"maxa_{X}") for X in STOP_OFF}
    max_stop.update({("dn", X): 1 - g(f"mina_{X}") for X in STOP_OFF})
    # stop sale prices per side x conv
    stop_px = {}
    for X in STOP_OFF:
        stop_px[("up", "cons", X)] = g(f"wsell_{X}")
        stop_px[("dn", "cons", X)] = 1 - g(f"wbuy_{X}")
        stop_px[("up", "opt", X)] = g(f"bid_{X}")
        stop_px[("dn", "opt", X)] = 1 - g(f"ask_{X}")

    win = {"up": up_won.astype(float), "dn": (~up_won).astype(float)}

    # ---- precompute pnl[side, conv, tgt, exit] ----
    EXITS = (["hold"] + [f"stop{X}_{b}" for X in STOP_OFF for b in ("opt", "pess")])
    pnl = {}
    fee_entry = {}
    for side in ("up", "dn"):
        for conv in ("cons", "opt"):
            e = entry[(side, conv)]
            sh = STAKE / e
            fe = sh * rate * e * (1 - e)
            fee_entry[(side, conv)] = fe
            hold_scalp = {}
            for tgt in TARGETS:
                L = e + tgt
                touched = max_ent[side] >= L + TICK
                scalp = sh * tgt - fe
                expiry = sh * win[side] - STAKE - fe
                pnl[(side, conv, tgt, "hold")] = np.where(touched, scalp, expiry)
                for X in STOP_OFF:
                    tb = max_stop[(side, X)] >= L + TICK   # touched after +X
                    s = stop_px[(side, conv, X)]
                    s_ok = np.isfinite(s) & (s > 0.01)
                    stop_pnl = np.where(
                        s_ok, sh * (s - e) - fe - sh * rate *
                        np.clip(s, 0.01, 0.99) * (1 - np.clip(s, 0.01, 0.99)),
                        expiry)
                    filled_sure = touched & ~tb
                    ambiguous = touched & tb
                    pnl[(side, conv, tgt, f"stop{X}_opt")] = np.where(
                        filled_sure | ambiguous, scalp, stop_pnl)
                    pnl[(side, conv, tgt, f"stop{X}_pess")] = np.where(
                        filled_sure, scalp, stop_pnl)

    # ---- direction sources ----
    dirs = {}
    for tau in TAUS:
        s_ = np.where(p_hat >= tau, 1, np.where(1 - p_hat >= tau, -1, 0))
        s_ = np.where(np.isfinite(p_hat), s_, 0)
        dirs[f"ml@{tau:.2f}"] = s_
    dirs["blind_up"] = np.ones(n, dtype=int)
    dirs["blind_dn"] = -np.ones(n, dtype=int)
    pf_ = np.where(prior_up > 0.5, 1, -1)
    dirs["prior_follow"] = np.where(np.isfinite(prior_up), pf_, 0)
    dirs["prior_fade"] = -dirs["prior_follow"]
    dirs["bmom"] = np.where(np.isfinite(bmom), np.sign(bmom), 0).astype(int)

    # ---- sweep ----
    rows = []
    for dname, sd in dirs.items():
        side_up = sd == 1
        side_dn = sd == -1
        active = sd != 0
        for conv in ("cons", "opt"):
            e_row = np.where(side_up, entry[("up", conv)],
                             np.where(side_dn, entry[("dn", conv)], np.nan))
            for tgt in TARGETS:
                pu = {x: pnl[("up", conv, tgt, x)] for x in EXITS}
                pd_ = {x: pnl[("dn", conv, tgt, x)] for x in EXITS}
                for x in EXITS:
                    p_row = np.where(side_up, pu[x], np.where(side_dn, pd_[x], np.nan))
                    for band in BANDS:
                        ok0 = (active & np.isfinite(e_row) & (e_row > 0.03)
                               & (e_row <= band) & (e_row + tgt < 0.99)
                               & np.isfinite(p_row))
                        for off in ENTRY_OFF:
                            ok = ok0 & (toff == off)
                            for sp in ("TRAIN", "VAL"):
                                m = ok & (split == sp)
                                nn = int(m.sum())
                                if nn < 2:
                                    continue
                                xarr = p_row[m]
                                sd_ = xarr.std(ddof=1)
                                t = xarr.mean() / sd_ * math.sqrt(nn) if sd_ > 0 else np.nan
                                gp = xarr[xarr > 0].sum()
                                gl = -xarr[xarr < 0].sum()
                                rows.append({
                                    "fam": fam, "dir": dname, "conv": conv,
                                    "tgt": tgt, "exit": x, "band": band,
                                    "off": off, "split": sp, "n": nn,
                                    "mean": float(xarr.mean()), "t": float(t),
                                    "pf": float(gp / gl) if gl > 0 else float("inf"),
                                    "total": float(xarr.sum()),
                                    "ndays": len(np.unique(date_arr[m])),
                                })
    res = pl.DataFrame(rows)

    # ---- anatomy table for the user's canonical config ----
    lines.append(f"\n### fam {fam} — anatomy at band<=0.51, tgt=+4c, off=-10s, conv=cons")
    for dname in ("ml@0.55", "blind_up", "prior_follow", "bmom"):
        sd = dirs[dname]
        side_up = sd == 1
        side_dn = sd == -1
        e_row = np.where(side_up, entry[("up", "cons")],
                         np.where(side_dn, entry[("dn", "cons")], np.nan))
        okm = ((sd != 0) & np.isfinite(e_row) & (e_row > 0.03) & (e_row <= 0.51)
               & (toff == -10) & (split == "VAL"))
        tch = np.where(side_up, max_ent["up"], max_ent["dn"]) >= e_row + 0.04 + TICK
        w = np.where(side_up, win["up"], win["dn"])
        ph = np.where(side_up, pnl[("up", "cons", 0.04, "hold")],
                      pnl[("dn", "cons", 0.04, "hold")])
        ps10o = np.where(side_up, pnl[("up", "cons", 0.04, "stop10_opt")],
                         pnl[("dn", "cons", 0.04, "stop10_opt")])
        ps10p = np.where(side_up, pnl[("up", "cons", 0.04, "stop10_pess")],
                         pnl[("dn", "cons", 0.04, "stop10_pess")])
        if okm.sum() < 10:
            lines.append(f"{dname:13s}: n={okm.sum()} (too few)")
            continue
        lines.append(
            f"{dname:13s}: n={okm.sum():5d} | limit-touch {tch[okm].mean():5.1%} | "
            f"dir-acc {w[okm].mean():5.1%} | VAL $/tr hold {np.nanmean(ph[okm]):+.3f} "
            f"| stop10 opt {np.nanmean(ps10o[okm]):+.3f} / pess {np.nanmean(ps10p[okm]):+.3f}")
    return res


def main() -> None:
    lines = ["# NIX4 — user scalp + stop-loss deep pass"]
    out = []
    for fam in ("5m", "15m"):
        if not os.path.exists(f"results/nix4/preds_{fam}_preopen.parquet"):
            lines.append(f"\nfam {fam}: preds not ready, skipped")
            continue
        print(f"sim {fam}", flush=True)
        out.append(sim_fam(fam, lines))
    res = pl.concat(out)
    res.write_parquet("results/nix4/scalp_stop_grid.parquet", compression="zstd")
    keys = ["fam", "dir", "conv", "tgt", "exit", "band", "off"]
    M = res.select(keys).unique().height
    bar = math.sqrt(2 * math.log(M))
    va = res.filter((pl.col("split") == "VAL") & (pl.col("n") >= 300))
    tr = (res.filter(pl.col("split") == "TRAIN")
             .select(keys + ["t"]).rename({"t": "t_train"}))
    va = va.join(tr, on=keys, how="left")
    surv = va.filter((pl.col("t") >= bar) & (pl.col("pf") >= 1.15)
                     & (pl.col("t_train") > 0))
    lines.insert(1, f"\nconfigs M={M}, deflated bar t>={bar:.2f}; "
                    f"VAL n>=300: {va.height}; SURVIVORS: {surv.height}")
    lines.append("\n## Top 25 by VAL t\n```")
    for r in va.sort("t", descending=True).head(25).iter_rows(named=True):
        lines.append(
            f"{r['fam']:3s} {r['dir']:13s} {r['conv']:4s} tgt={r['tgt']:.2f} "
            f"{r['exit']:11s} band={r['band']:.2f} off={r['off']:+3d} | "
            f"n={r['n']:5d} ${r['mean']:+.3f}/tr t={r['t']:+5.2f} pf={r['pf']:.2f} "
            f"(train t={r['t_train']:+.2f})")
    lines.append("```")
    if surv.height:
        lines.append("\n## SURVIVORS\n```")
        for r in surv.sort("t", descending=True).iter_rows(named=True):
            lines.append(str(r))
        lines.append("```")
    # exit-rule marginal effect (does the user's stop help?), matched configs
    lines.append("\n## Exit-rule marginal effect (VAL mean $/tr averaged over "
                 "all matched configs)\n```")
    base = va.group_by("exit").agg(pl.col("mean").mean().alias("avg"),
                                   pl.len()).sort("avg", descending=True)
    for r in base.iter_rows(named=True):
        lines.append(f"{r['exit']:12s}: {r['avg']:+.4f} $/tr over {r['len']} configs")
    lines.append("```")
    os.makedirs("reports", exist_ok=True)
    open("reports/nix4_scalp_stop.md", "w").write("\n".join(lines) + "\n")
    print("DONE — reports/nix4_scalp_stop.md", flush=True)


if __name__ == "__main__":
    main()
