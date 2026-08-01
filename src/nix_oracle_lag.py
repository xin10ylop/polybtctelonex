"""Is nix2's core assumption true? Measure the REAL Binance->Chainlink lag.

nix2's whole edge rests on one mechanism: the strike K = Chainlink(T) is a
STALE view of spot, so a spot move in the last second before T predicts which
side of K the window opens on. The bot encodes that as a fixed 1-second
lookback (feeds.py::signal):

    g = ln( price(T-0.65s) / price(T-1.65s) )

That hard-codes "the oracle lags spot by about one second." Nobody has
checked. windows.parquet carries `open_chainlink` (the actual strike) for
47k windows and we hold 1s Binance klines, so the assumption is directly
measurable:

  TEST 1 (mechanism): for lag L, how far is Binance(T-L) from K? The L that
          minimises |error| IS the true oracle lag. If it is not ~1s, nix2's
          lookback is mis-specified.

  TEST 2 (payoff):    sweep the lookback W used to build g and measure the
          realised hit rate. Uses only pre-T spot data -- no look-ahead, so
          the winner is a deployable parameter, not a diagnostic.

Both tests are descriptive measurements over history; neither is a backtest
of a trading rule, and neither is used to justify a P&L number.

  .venv/bin/python src/nix_oracle_lag.py
"""
from __future__ import annotations

import glob
import math
import os

import polars as pl

MAX_LAG = 10          # seconds to probe on either side
WINDOWS = "data/processed/windows.parquet"
KLINES = "data/processed/binance/klines_1s"


def load_windows() -> pl.DataFrame:
    w = pl.read_parquet(WINDOWS)
    w = w.filter(
        (pl.col("family") == "5m")
        & pl.col("open_chainlink").is_not_null()
        & pl.col("close_chainlink").is_not_null()
        & pl.col("result_id").is_not_null()
        # oracle strike is not real data before Apr 2 2026 (March agreement
        # with the outcome is 50.5% = chance). Independently documented in the
        # S2 research repo as "no oracle K before Apr 2".
        & (pl.col("date") >= "2026-04-02")
    )
    return w.select("slug", "wts", "date", "open_chainlink",
                    "close_chainlink", "result_id")


def verify_result_encoding(w: pl.DataFrame) -> bool:
    """result_id==0 should mean Up won, i.e. close_chainlink > open_chainlink.
    Verified against the data rather than trusted from documentation."""
    chk = w.with_columns(
        (pl.col("close_chainlink") > pl.col("open_chainlink")).alias("up_by_px"),
        (pl.col("result_id").cast(pl.Int32) == 0).alias("up_by_id"),
    )
    agree = chk.filter(pl.col("up_by_px") == pl.col("up_by_id")).height
    print(f"result encoding check: {agree}/{chk.height} "
          f"({100*agree/chk.height:.2f}%) agree that result_id==0 <=> Up won")
    return agree / chk.height > 0.99


def main() -> None:
    w = load_windows()
    dates = sorted(set(w["date"].to_list()))
    have = {os.path.basename(p)[:-8] for p in glob.glob(f"{KLINES}/*.parquet")}
    dates = [d for d in dates if d in have]
    w = w.filter(pl.col("date").is_in(dates))
    print(f"{w.height} 5m windows with a strike, over {len(dates)} days "
          f"({dates[0]} .. {dates[-1]})\n")
    verify_result_encoding(w)

    # accumulate per-lag absolute error (bp) and per-lookback hit counts
    lag_err: dict[int, list[float]] = {L: [] for L in range(0, MAX_LAG + 1)}
    hits: dict[int, list[int]] = {W: [] for W in range(1, MAX_LAG + 1)}

    for i, d in enumerate(dates):
        try:
            k = pl.read_parquet(f"{KLINES}/{d}.parquet",
                                columns=["open_time_us", "close"])
        except Exception:
            continue
        px = dict(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))
        day = w.filter(pl.col("date") == d)
        for wts, K, res in zip(day["wts"], day["open_chainlink"],
                               day["result_id"]):
            # TEST 1 -- which lag reproduces the strike?
            for L in lag_err:
                p = px.get(wts - L)
                if p and K and K > 0:
                    lag_err[L].append(abs(1e4 * math.log(p / K)))
            # TEST 2 -- which lookback predicts the outcome? (pre-T data only)
            p_now = px.get(wts - 1)
            if not p_now:
                continue
            up_won = (int(res) == 0)
            for W in hits:
                p_prev = px.get(wts - 1 - W)
                if not p_prev or p_prev <= 0:
                    continue
                g = math.log(p_now / p_prev)
                if g == 0:
                    continue
                hits[W].append(1 if ((g > 0) == up_won) else 0)
        if (i + 1) % 40 == 0:
            print(f"  ...{i+1}/{len(dates)} days", flush=True)

    def med(xs):
        s = sorted(xs)
        return s[len(s) // 2] if s else float("nan")

    print("\n=== TEST 1: which Binance lag reproduces the Chainlink strike? ===")
    print("  (median |error| in basis points; the MINIMUM is the true lag)")
    best_L, best_v = None, float("inf")
    for L in sorted(lag_err):
        if not lag_err[L]:
            continue
        m = med(lag_err[L])
        star = ""
        if m < best_v:
            best_v, best_L = m, L
        print(f"   lag {L:>2}s : median |err| {m:6.2f} bp   n={len(lag_err[L])}")
    print(f"\n  -> TRUE ORACLE LAG = {best_L}s (median error {best_v:.2f} bp)")
    print(f"  -> nix2 assumes 1s. Median deciding move in a 5m window ~4.8 bp,")
    print(f"     so an error of {best_v:.2f} bp is "
          f"{'SMALLER' if best_v < 4.8 else 'LARGER'} than the thing being predicted.")

    print("\n=== TEST 2: which lookback W maximises hit rate? (no look-ahead) ===")
    print("  g = ln( close(T-1s) / close(T-1s-W) ),  side = sign(g)")
    bw, bh = None, 0.0
    for W in sorted(hits):
        h = hits[W]
        if not h:
            continue
        r = sum(h) / len(h)
        se = math.sqrt(r * (1 - r) / len(h))
        z = (r - 0.5) / se if se > 0 else float("nan")
        mark = "  <-- nix2" if W == 1 else ""
        if r > bh:
            bh, bw = r, W
        print(f"   W={W:>2}s : hit {r:6.3%}  n={len(h):>6}  z={z:+5.2f}{mark}")
    print(f"\n  -> BEST lookback = {bw}s at {bh:.3%}; nix2 uses 1s.")


if __name__ == "__main__":
    main()
