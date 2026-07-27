"""FILL AUDIT for the cheap+signal (nix2) strategy — deployability, not alpha.

The question this answers: the backtest gates on the book and fills at the SAME
instant. A real bot OBSERVES the book at T0, then its order ARRIVES some
latency later. In between, the cheap liquidity can vanish or reprice. If the
edge only exists at zero latency, it is not deployable.

Method (all on historical data — the live forward test is never tuned on):
  decision at T0 = boundary - 0.5s, gate on the book AS SEEN at T0
  fill at T0 + L for L in {0, 250ms, 500ms, 1s, 2s}, at the book THEN
  three fill conventions:
    touch    - we get the best ask that exists at fill time
    +1tick   - we miss the touch by one cent (someone beat us)
    walk50   - we take the $50 book-walk average (worst realistic case)
  plus a depth filter: only trade if >= stake rests at fill time.

Outputs EV/trade, win rate, fill rate and day-clustered t for every cell, so
we can see exactly how much latency and queue-position the edge tolerates.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import polars as pl
from scipy import stats

sys.path.insert(0, "src")

ASK_MIN, ASK_MAX = 0.44, 0.4999
Z_MIN, Z_MAX = 0.05, 0.40
T0_OFF_US = -500_000          # decision: 0.5s before boundary
LATENCIES_US = [0, 250_000, 500_000, 1_000_000, 2_000_000]
STAKE = 10.0


def load_signals() -> pl.DataFrame:
    """The frozen cell's windows (signal + side + outcome), from the committed
    research rows. `ask` here was measured at T0+250ms; we re-measure below."""
    df = pl.read_parquet("results/nix_scalp6_rows.parquet").filter(
        (pl.col("t0") == -0.5) & (pl.col("family") == "5m")
        & (pl.col("date") <= "2026-05-12")
        & (pl.col("absz") >= Z_MIN) & (pl.col("absz") < Z_MAX))
    return df.sort("date", "wts")


def book_arrays(date: str):
    p = f"data/processed/daily/5m/bookcurves/{date}.parquet"
    if not os.path.exists(p):
        return None
    b = pl.read_parquet(p).sort("wts", "timestamp_us")
    return {
        "wts": b["wts"].to_numpy(), "ts": b["timestamp_us"].to_numpy(),
        "bid": b["bid_p0"].to_numpy().astype(np.float64),
        "ask": b["ask_p0"].to_numpy().astype(np.float64),
        "bsz": b["bid_s0"].to_numpy().astype(np.float64),
        "asz": b["ask_s0"].to_numpy().astype(np.float64),
        "bwalk": b["buy_avgpx_50"].to_numpy().astype(np.float64),
        "swalk": b["sell_avgpx_50"].to_numpy().astype(np.float64),
    }


def build() -> pl.DataFrame:
    out = "results/nix_fillaudit_rows.parquet"
    if os.path.exists(out):
        return pl.read_parquet(out)
    sig = load_signals()
    recs = []
    for date, grp in sig.group_by("date", maintain_order=True):
        date = date[0] if isinstance(date, tuple) else date
        B = book_arrays(date)
        if B is None:
            continue
        for r in grp.iter_rows(named=True):
            w = r["wts"]; side = r["side"]
            lo = np.searchsorted(B["wts"], w, "left")
            hi = np.searchsorted(B["wts"], w, "right")
            if hi <= lo:
                continue
            seg_ts = B["ts"][lo:hi]
            T0 = w * 1_000_000 + T0_OFF_US

            def snap(t_us):
                k = int(np.searchsorted(seg_ts, t_us, "right")) - 1
                if k < 0:
                    return None
                j = lo + k
                if side == "up":
                    a = B["ask"][j]; d = B["asz"][j] * a
                    wk = B["bwalk"][j]
                else:
                    a = 1 - B["bid"][j]; d = B["bsz"][j] * a
                    wk = 1 - B["swalk"][j]
                if not np.isfinite(a):
                    return None
                return a, (d if np.isfinite(d) else 0.0), (wk if np.isfinite(wk) else a)

            s0 = snap(T0)
            if s0 is None:
                continue
            rec = {"date": date, "wts": int(w), "side": side, "win": r["win"],
                   "rate": r["rate"], "absz": r["absz"],
                   "ask_t0": round(s0[0], 4), "depth_t0": round(s0[1], 1)}
            for L in LATENCIES_US:
                s = snap(T0 + L)
                tag = f"{L//1000}ms"
                if s is None:
                    rec[f"ask_{tag}"] = None; rec[f"dep_{tag}"] = None
                    rec[f"walk_{tag}"] = None
                else:
                    rec[f"ask_{tag}"] = round(s[0], 4)
                    rec[f"dep_{tag}"] = round(s[1], 1)
                    rec[f"walk_{tag}"] = round(s[2], 4)
            recs.append(rec)
    df = pl.DataFrame(recs, infer_schema_length=None)
    df.write_parquet(out)
    return df


def pnl_of(ask, win, rate, stake=STAKE):
    sh = stake / ask
    return sh * win - stake - rate * ask * (1 - ask) * sh


def judge(d: pl.DataFrame, fill_px: np.ndarray, mask: np.ndarray, label: str,
          n_windows: int):
    if mask.sum() < 20:
        print(f"  {label:<34} n={mask.sum():>4}  (too few)")
        return
    win = d["win"].to_numpy().astype(float)[mask]
    rate = d["rate"].to_numpy()[mask]
    p = pnl_of(fill_px[mask], win, rate)
    dates = d["date"].to_numpy()[mask]
    dl = pl.DataFrame({"d": dates, "p": p}).group_by("d").agg(
        pl.col("p").mean().alias("e"))["e"].to_numpy()
    t = stats.ttest_1samp(dl, 0)[0] if len(dl) > 2 else float("nan")
    print(f"  {label:<34} n={mask.sum():>4} ({mask.sum()/n_windows:>4.0%} fill) "
          f"wr {win.mean():>5.1%}  EV ${p.mean():+.3f}  t={t:+5.2f}  "
          f"tot ${p.sum():+7.0f}")


def main() -> None:
    d = build()
    print(f"signal windows with book data: {len(d)}  "
          f"({d['date'].n_unique()} days, |z| {Z_MIN}-{Z_MAX})\n")

    # gate on what we SEE at T0 (this is what a live bot does)
    ask_t0 = d["ask_t0"].to_numpy()
    gate = (ask_t0 >= ASK_MIN) & (ask_t0 <= ASK_MAX)
    n_gated = gate.sum()
    print(f"windows passing the ask gate AS SEEN AT DECISION TIME: {n_gated}"
          f"  ({n_gated/d['date'].n_unique():.1f}/day)\n")

    print("=== A. LATENCY SENSITIVITY (gate at T0, fill at T0+L, touch price) ===")
    print("   the current sim is the 250ms row; live adds network delay on top")
    for L in LATENCIES_US:
        tag = f"{L//1000}ms"
        a = d[f"ask_{tag}"].to_numpy().astype(np.float64)
        dep = d[f"dep_{tag}"].to_numpy().astype(np.float64)
        m = gate & np.isfinite(a) & (dep >= STAKE)
        judge(d, a, m, f"fill@{tag} touch, depth>=${STAKE:.0f}", n_gated)

    print("\n=== B. QUEUE RISK (we miss the touch — pay one cent worse) ===")
    for L in [250_000, 500_000, 1_000_000]:
        tag = f"{L//1000}ms"
        a = d[f"ask_{tag}"].to_numpy().astype(np.float64) + 0.01
        dep = d[f"dep_{tag}"].to_numpy().astype(np.float64)
        m = gate & np.isfinite(a) & (dep >= STAKE) & (a <= 0.55)
        judge(d, a, m, f"fill@{tag} +1 tick worse", n_gated)

    print("\n=== C. WORST CASE (take the $50 book-walk average price) ===")
    for L in [250_000, 1_000_000]:
        tag = f"{L//1000}ms"
        a = d[f"walk_{tag}"].to_numpy().astype(np.float64)
        m = gate & np.isfinite(a) & (a <= 0.60)
        judge(d, a, m, f"walk50@{tag}", n_gated)

    print("\n=== D. HOW THE PRICE MOVES between decision and fill ===")
    for L in [250_000, 500_000, 1_000_000]:
        tag = f"{L//1000}ms"
        a = d[f"ask_{tag}"].to_numpy().astype(np.float64)
        m = gate & np.isfinite(a)
        drift = (a[m] - ask_t0[m]) * 100
        print(f"  T0 -> +{tag:<7} median {np.median(drift):+.2f}c  "
              f"mean {drift.mean():+.2f}c  |  worse {np.mean(drift>0):.0%} / "
              f"same {np.mean(drift==0):.0%} / better {np.mean(drift<0):.0%}")

    print("\n=== E. DEPTH AT THE TOUCH (can we even get size on?) ===")
    dep = d["dep_250ms"].to_numpy().astype(np.float64)
    m = gate & np.isfinite(dep)
    for q in (10, 25, 50, 75, 90):
        print(f"  p{q:<3} ${np.percentile(dep[m], q):>7.0f}")
    for S in (5, 10, 25, 50, 100):
        print(f"  windows with >= ${S:>3} at touch: {np.mean(dep[m] >= S):>5.0%}")

    print("\n=== F. SIZE SCALING (walk the book to fill the full stake) ===")
    a250 = d["ask_250ms"].to_numpy().astype(np.float64)
    w250 = d["walk_250ms"].to_numpy().astype(np.float64)
    for S in (5, 10, 25, 50):
        at = np.minimum(S, np.nan_to_num(dep))
        rest = S - at
        # blended: touch for what's there, walk price for the remainder
        px = np.where(rest > 0.5, (at * a250 + rest * w250) / np.maximum(S, 1e-9), a250)
        m = gate & np.isfinite(px) & (np.nan_to_num(dep) >= 1.0)
        if m.sum() < 20:
            continue
        win = d["win"].to_numpy().astype(float)[m]
        rate = d["rate"].to_numpy()[m]
        p = pnl_of(px[m], win, rate, stake=S)
        dates = d["date"].to_numpy()[m]
        dl = pl.DataFrame({"d": dates, "p": p}).group_by("d").agg(
            pl.col("p").mean().alias("e"))["e"].to_numpy()
        t = stats.ttest_1samp(dl, 0)[0]
        print(f"  ${S:>3}/trade blended fill: n={m.sum()} EV ${p.mean():+.3f} "
              f"({p.mean()/S*100:+.1f}%) t={t:+.2f} -> ${p.sum()/d['date'].n_unique():+.2f}/day")

    print("\nFILL_AUDIT DONE")


if __name__ == "__main__":
    main()
