"""Phase 1 — microstructure study. Produces reports/phase1_microstructure.md.

Six sections (run brief): calibration, lead-lag, spread/depth/cost profiles,
taker-vs-maker P&L, serial dependence, and the 50-cent post-mortem.

Runs over all NON-HOLDOUT processed dates available at invocation time (the
loader guard enforces holdout hygiene once configs/holdout.json exists).
Numeric outputs land in results/phase1/*.parquet + the markdown report;
plots are generated separately by src/phase1_plots.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import numpy as np
import polars as pl
from scipy import stats

sys.path.insert(0, "src")
import fees
import loader
import windows as W

OUT_DIR = "results/phase1"
T_OFFSETS = [10, 30, 60, 120, 180, 240]          # seconds BEFORE expiry (5m)
PRICE_BANDS = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.45), (0.45, 0.55),
               (0.55, 0.7), (0.7, 0.9), (0.9, 1.01)]


def non_holdout_dates(family: str, channel: str) -> list[str]:
    dates = loader.available_dates(family, channel)
    rng = loader.holdout_range()
    if rng:
        dates = [d for d in dates if not (rng[0] <= d <= rng[1])]
    return dates


def load_windows_all(family: str, dates: list[str]) -> pl.DataFrame:
    """Windows table over many dates, chunked by month to bound memory."""
    out = []
    for i in range(0, len(dates), 31):
        out.append(W.build_windows(family, dates[i:i + 31]))
    w = pl.concat(out).unique(subset="wts", keep="first").sort("wts")
    return w


# ---------------------------------------------------------------- section 1
def sec1_calibration(family: str, dates: list[str]) -> pl.DataFrame:
    """Reliability of market-implied prob vs outcome by time-to-expiry x band."""
    dur = W.FAMILY_DUR[family]
    rows = []
    wins = load_windows_all(family, dates)
    wins = wins.filter(pl.col("result_id").is_in(["0", "1"]))
    won = wins.select("wts", (pl.col("result_id") == "0").alias("up_won"))
    for chunk_start in range(0, len(dates), 14):
        chunk = dates[chunk_start:chunk_start + 14]
        q = (loader.load_daily(family, "quotes", chunk)
             .select("wts", "timestamp_us", "bid_price", "ask_price")
             .drop_nulls().collect())
        q = q.with_columns(((pl.col("bid_price") + pl.col("ask_price")) / 2).alias("mid"))
        t = q["timestamp_us"].to_numpy()
        wts_arr = q["wts"].to_numpy()
        mid = q["mid"].to_numpy()
        # per (window, offset): last mid strictly before expiry-offset
        order = np.lexsort((t, wts_arr))
        t, wts_arr, mid = t[order], wts_arr[order], mid[order]
        uw = np.unique(wts_arr)
        starts = np.searchsorted(wts_arr, uw, side="left")
        ends = np.searchsorted(wts_arr, uw, side="right")
        for off in T_OFFSETS:
            target = (uw + dur - off) * 1_000_000
            idx = np.searchsorted(t, target, side="left") - 1
            ok = (idx >= starts) & (idx < ends)
            for w_, m_ in zip(uw[ok], mid[idx[ok]]):
                rows.append({"wts": int(w_), "offset": off, "mid": float(m_)})
    df = pl.DataFrame(rows).join(won, on="wts", how="inner")
    # bucket by band x offset
    agg = []
    for off in T_OFFSETS:
        for lo, hi in PRICE_BANDS:
            b = df.filter((pl.col("offset") == off) & (pl.col("mid") >= lo) & (pl.col("mid") < hi))
            if len(b) < 30:
                continue
            p_implied = float(b["mid"].mean())
            p_real = float(b["up_won"].mean())
            n = len(b)
            se = (p_real * (1 - p_real) / n) ** 0.5 if 0 < p_real < 1 else 0.0
            agg.append({"family": family, "offset_s": off, "band": f"{lo:.2f}-{hi:.2f}",
                        "n": n, "implied": round(p_implied, 4), "realized": round(p_real, 4),
                        "gap": round(p_real - p_implied, 4), "se": round(se, 4)})
    return pl.DataFrame(agg)


# ---------------------------------------------------------------- section 3
def sec3_costs(family: str, dates: list[str]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Spread/depth by seconds-into-window and hour-of-day; realized $ cost of
    market orders vs mid, from precomputed book-walk curves."""
    prof_rows, hour_rows = [], []
    dur = W.FAMILY_DUR[family]
    sec_bins = list(range(0, dur + 1, max(dur // 20, 15)))
    for chunk_start in range(0, len(dates), 14):
        chunk = dates[chunk_start:chunk_start + 14]
        b = (loader.load_daily(family, "bookcurves", chunk)
             .select("wts", "timestamp_us", "bid_p0", "ask_p0", "bid_depth_5c",
                     "ask_depth_5c", "buy_avgpx_50", "buy_avgpx_200", "buy_avgpx_1000",
                     "sell_avgpx_50", "sell_avgpx_200", "sell_avgpx_1000")
             .collect())
        b = b.with_columns(
            ((pl.col("timestamp_us") / 1e6).cast(pl.Int64) - pl.col("wts")).alias("s_in"),
            ((pl.col("bid_p0") + pl.col("ask_p0")) / 2).alias("mid"),
            (pl.col("ask_p0") - pl.col("bid_p0")).alias("spread"),
            ((pl.col("wts") % 86400) // 3600).alias("hour"),
        ).filter((pl.col("s_in") >= 0) & (pl.col("s_in") < dur) & (pl.col("spread") >= 0))
        for c in ("buy_avgpx_50", "buy_avgpx_200", "buy_avgpx_1000"):
            b = b.with_columns((pl.col(c) - pl.col("mid")).alias(c.replace("avgpx", "slip")))
        for c in ("sell_avgpx_50", "sell_avgpx_200", "sell_avgpx_1000"):
            b = b.with_columns((pl.col("mid") - pl.col(c)).alias(c.replace("avgpx", "slip")))
        b = b.with_columns(pl.col("s_in").cut(sec_bins, left_closed=True).alias("s_bin"))
        prof_rows.append(
            b.group_by("s_bin").agg(
                pl.len().alias("n"), pl.col("spread").median().alias("spread_med"),
                pl.col("bid_depth_5c").median().alias("bid_depth_med"),
                pl.col("ask_depth_5c").median().alias("ask_depth_med"),
                pl.col("buy_slip_50").median().alias("slip50"),
                pl.col("buy_slip_200").median().alias("slip200"),
                pl.col("buy_slip_1000").median().alias("slip1000"),
            ).with_columns(pl.lit(family).alias("family")))
        hour_rows.append(
            b.group_by("hour").agg(
                pl.len().alias("n"), pl.col("spread").median().alias("spread_med"),
                pl.col("bid_depth_5c").median().alias("bid_depth_med"),
                pl.col("buy_slip_200").median().alias("slip200"),
            ).with_columns(pl.lit(family).alias("family")))
    def wavg(col: str):
        return ((pl.col(col) * pl.col("n")).sum() / pl.col("n").sum()).alias(col)

    prof = (pl.concat(prof_rows).group_by("family", "s_bin")
            .agg(wavg("spread_med"), wavg("bid_depth_med"), wavg("ask_depth_med"),
                 wavg("slip50"), wavg("slip200"), wavg("slip1000"),
                 pl.col("n").sum().alias("n")))
    hour = (pl.concat(hour_rows).group_by("family", "hour")
            .agg(wavg("spread_med"), wavg("bid_depth_med"), wavg("slip200"),
                 pl.col("n").sum().alias("n")))
    return prof.sort("family", "s_bin"), hour.sort("family", "hour")


# ---------------------------------------------------------------- section 4
def sec4_taker_maker_pnl(family: str, dates: list[str]) -> pl.DataFrame:
    """Aggregate taker vs maker P&L from on-chain fills (Up-token economics).

    Every fill: taker trades `amount` shares at `price` vs maker. We track the
    UP-token equivalent position for both roles and settle at resolution.
    Uses non-mirrored rows only (each economic fill counted once)."""
    wins = load_windows_all(family, dates).filter(pl.col("result_id").is_in(["0", "1"]))
    up_won = wins.select("wts", (pl.col("result_id") == "0").cast(pl.Float64).alias("up_pay"))
    out = []
    for chunk_start in range(0, len(dates), 31):
        chunk = dates[chunk_start:chunk_start + 31]
        f = (loader.load_daily(family, "fills", chunk)
             .filter(~pl.col("mirrored"))
             .select("wts", "taker_side", "token", "amount", "price", "taker_fee")
             .collect())
        # normalize to UP token: buying DOWN at p == selling UP at 1-p
        f = f.with_columns(
            pl.when(pl.col("token") == "Up").then(pl.col("price"))
              .otherwise(1 - pl.col("price")).alias("p_up"),
            pl.when((pl.col("taker_side") == "buy") == (pl.col("token") == "Up"))
              .then(1).otherwise(-1).alias("taker_dir_up"),  # +1 taker long UP
        )
        f = f.join(up_won, on="wts", how="inner")
        # taker P&L per fill: dir*(payout - price)*amount - fee ; maker = mirror + 0 fee
        f = f.with_columns(
            (pl.col("taker_dir_up") * (pl.col("up_pay") - pl.col("p_up"))
             * pl.col("amount") - pl.col("taker_fee")).alias("taker_pnl"),
            (-pl.col("taker_dir_up") * (pl.col("up_pay") - pl.col("p_up"))
             * pl.col("amount")).alias("maker_pnl"),
        )
        out.append(f.select(
            pl.col("wts").min().alias("first_wts"), pl.col("wts").max().alias("last_wts"),
            pl.len().alias("n_fills"), pl.col("amount").sum().alias("shares"),
            (pl.col("amount") * pl.col("p_up")).sum().alias("notional"),
            pl.col("taker_pnl").sum(), pl.col("maker_pnl").sum(),
            pl.col("taker_fee").sum().alias("fees_paid"),
        ))
    agg = pl.concat(out).select(
        pl.col("n_fills").sum(), pl.col("shares").sum(), pl.col("notional").sum(),
        pl.col("taker_pnl").sum(), pl.col("maker_pnl").sum(), pl.col("fees_paid").sum())
    return agg.with_columns(pl.lit(family).alias("family"))


# ---------------------------------------------------------------- section 5
def sec5_serial(family: str, dates: list[str]) -> dict:
    """Runs test + autocorrelation on window outcomes."""
    wins = load_windows_all(family, dates).filter(pl.col("result_id").is_in(["0", "1"]))
    x = (wins.sort("wts")["result_id"] == "0").to_numpy().astype(int)
    n = len(x)
    n1, n0 = int(x.sum()), int(n - x.sum())
    runs = int(1 + (np.diff(x) != 0).sum())
    mu = 1 + 2 * n1 * n0 / n
    var = 2 * n1 * n0 * (2 * n1 * n0 - n) / (n ** 2 * (n - 1))
    z = (runs - mu) / var ** 0.5 if var > 0 else 0.0
    ac = {}
    xm = x - x.mean()
    denom = float((xm ** 2).sum())
    for lag in (1, 2, 3, 5, 10, 20):
        ac[lag] = round(float((xm[:-lag] * xm[lag:]).sum() / denom), 4)
    return {"family": family, "n_windows": n, "share_up": round(n1 / n, 4),
            "runs": runs, "runs_expected": round(mu, 1), "runs_z": round(float(z), 3),
            "runs_p": round(float(2 * stats.norm.sf(abs(z))), 5), "autocorr": ac}


# ---------------------------------------------------------------- section 6
def sec6_fifty_cent(family: str, dates: list[str]) -> dict:
    """Exact economics of taker-buy at ~50c, sell at +5c under current fees."""
    d_ref = dates[-1]
    buy_fee = fees.taker_fee(100, 0.50, d_ref, family)
    sell_fee = fees.taker_fee(100, 0.55, d_ref, family)
    # taker round trip 0.50 -> 0.55 on 100 shares
    gross = 100 * 0.05
    rt_cost_taker = buy_fee + sell_fee
    # maker exit variant: sell resting at 0.55, no fee
    # hold-to-expiry variant: win pays (1-0.50)*100 - buy_fee; lose -50-buy_fee
    win_amt = 100 * 0.50 - buy_fee
    lose_amt = 100 * 0.50 + buy_fee
    breakeven_hold = lose_amt / (win_amt + lose_amt)
    return {
        "family": family, "fee_date": d_ref,
        "buy_fee_100sh_at_50c": buy_fee, "sell_fee_100sh_at_55c": sell_fee,
        "taker_taker_roundtrip_fee": round(rt_cost_taker, 4),
        "gross_5c_gain": gross,
        "net_after_fees_taker_taker": round(gross - rt_cost_taker, 4),
        "net_after_fees_taker_maker": round(gross - buy_fee, 4),
        "breakeven_winrate_hold_to_expiry": round(breakeven_hold, 4),
        "note": "spread/slippage NOT included here; see section 3 for realized costs",
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    results: dict = {"generated": dt.datetime.now(dt.UTC).isoformat()}
    for family in ("5m", "15m"):
        dates_q = non_holdout_dates(family, "quotes")
        dates_b = non_holdout_dates(family, "bookcurves")
        dates_f = non_holdout_dates(family, "fills")
        if not dates_q:
            continue
        print(f"[{family}] {len(dates_q)} dates", flush=True)
        sec1_calibration(family, dates_q).write_parquet(f"{OUT_DIR}/calibration_{family}.parquet")
        if dates_b:
            prof, hour = sec3_costs(family, dates_b)
            prof.write_parquet(f"{OUT_DIR}/cost_profile_{family}.parquet")
            hour.write_parquet(f"{OUT_DIR}/cost_hourly_{family}.parquet")
        if dates_f:
            sec4_taker_maker_pnl(family, dates_f).write_parquet(f"{OUT_DIR}/taker_maker_{family}.parquet")
        results[f"serial_{family}"] = sec5_serial(family, dates_q)
        results[f"fifty_cent_{family}"] = sec6_fifty_cent(family, dates_q)
        print(f"[{family}] sections 1,3,4,5,6 done", flush=True)
    with open(f"{OUT_DIR}/phase1_scalars.json", "w") as f:
        json.dump(results, f, indent=1)
    print("phase1 numeric core done (section 2 lead-lag runs separately)")


if __name__ == "__main__":
    main()
