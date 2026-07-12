"""Sizing / compounding comparison for the BTC cheap+signal edge (2026-07-12).

Answers "should we compound?" empirically on the real trade sequence, under the
capacity cap ($50/window book-depth ceiling). Compares fixed, fractional-Kelly,
and win-doubling ladder by terminal wealth, max drawdown, Sharpe, ruin.
"""
from __future__ import annotations

import numpy as np
import polars as pl

CAPWIN = 50.0   # book-depth ceiling: max $ deployable per window


def load_returns() -> tuple[np.ndarray, np.ndarray]:
    df = pl.read_parquet("results/nix_scalp6_rows.parquet").filter(
        (pl.col("t0") == -0.5) & (pl.col("family") == "5m")
        & (pl.col("date") <= "2026-05-12")
        & (pl.col("ask") < 0.50) & (pl.col("absz") >= 0.05)).sort("date", "wts")
    a = df["ask"].to_numpy(); w = df["win"].to_numpy().astype(float)
    rate = df["rate"].to_numpy()
    r = (w / a - 1.0) - rate * (1 - a)   # return per $1 staked
    return r, df["date"].to_numpy()


def sim(r, sizing, bank0=500.0, **kw):
    bank = peak = bank0; mdd = 0.0; eq = [bank0]; consec = 0; ruin = False
    for ri in r:
        if sizing == "fixed":
            s = kw["S"]
        elif sizing == "frac":
            s = kw["f"] * bank
        else:  # ladder
            s = 10.0 * (2 ** consec)
        s = min(s, CAPWIN, bank)
        if s < 5.0 and bank >= 5.0:
            s = 5.0
        bank += s * ri
        peak = max(peak, bank); mdd = max(mdd, (peak - bank) / peak)
        if sizing == "ladder":
            consec = consec + 1 if (ri > 0 and consec < kw["rungs"]) else 0
        eq.append(bank)
        if bank < 10:
            ruin = True; break
    d = np.diff(np.array(eq))
    sharpe = d.mean() / d.std() * np.sqrt(7.6 * 252) if d.std() > 0 else 0
    return bank, mdd * 100, sharpe, ruin


def main() -> None:
    r, _ = load_returns()
    print(f"{len(r)} trades, mean {r.mean()*100:+.1f}%/stake, sd {r.std():.2f}")
    print(f"{'strategy':<26}{'end$':>8}{'maxDD%':>8}{'Sharpe':>8}{'ruin':>6}")
    rows = [("fixed $10", "fixed", {"S": 10.0}),
            ("fixed $25", "fixed", {"S": 25.0}),
            ("fixed $50 (cap)", "fixed", {"S": 50.0}),
            ("frac 3% (1/4-Kelly)", "frac", {"f": 0.03}),
            ("frac 6% (1/2-Kelly)", "frac", {"f": 0.06}),
            ("frac 11% (full-Kelly)", "frac", {"f": 0.11}),
            ("ladder x2 max2", "ladder", {"rungs": 2}),
            ("ladder x2 max3", "ladder", {"rungs": 3})]
    for lab, sz, kw in rows:
        b, dd, sh, ru = sim(r, sz, **kw)
        print(f"{lab:<26}{b:>8.0f}{dd:>8.1f}{sh:>8.2f}{('YES' if ru else 'no'):>6}")


if __name__ == "__main__":
    main()
