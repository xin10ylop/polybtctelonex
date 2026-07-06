"""Phase 2 — feature library. One row per (window_ts, t_offset) decision point.

Hard Rule 1 enforcement: every feature is computed from data with availability
timestamp strictly <= decision time T. Availability = `local_timestamp_us`
(collector receive time) for Telonex channels; Binance event time + BINANCE_LAT_US
assumed feed latency; prior-window outcomes become available PRIOR_END + 2s
(the Chainlink boundary tick is public within ~1-2s).

Output: results/features/{family}/{date}.parquet
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import polars as pl
from scipy.stats import norm

sys.path.insert(0, "src")
import loader
import windows as W

BINANCE_LAT_US = 100_000          # assumed Binance->home feed latency
PRIOR_OUTCOME_DELAY_US = 2_000_000
OFFSETS = {                        # decision offsets (s) relative to window START
    "5m": [-30, -10, -3, 1, 5, 10, 20, 30, 45, 60, 90, 120, 150, 180, 210, 240, 270, 285],
    "15m": [-30, -10, -3, 1, 10, 30, 60, 120, 180, 300, 420, 540, 660, 780, 840, 870],
}
RET_HORIZONS_S = [1, 5, 15, 60, 300, 900, 3600]
VOL_LOOKBACKS_S = [60, 300, 1800]
ODDS_VEL_S = [1, 5, 15, 60]
FLOW_S = [10, 60]


def _asof(ts_sorted: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Index of last element <= target, -1 if none."""
    return np.searchsorted(ts_sorted, targets, side="right") - 1


class DayFrames:
    """All per-day source arrays, loaded once."""

    def __init__(self, family: str, date: str):
        self.family, self.date = family, date
        self.dur = W.FAMILY_DUR[family]
        q = (loader.load_daily(family, "quotes", [date])
             .select("wts", "local_timestamp_us", "bid_price", "ask_price")
             .drop_nulls().collect().sort("wts", "local_timestamp_us"))
        self.q_wts = q["wts"].to_numpy()
        self.q_ts = q["local_timestamp_us"].to_numpy()
        self.q_mid = ((q["bid_price"] + q["ask_price"]) / 2).to_numpy().astype(np.float64)
        self.q_spread = (q["ask_price"] - q["bid_price"]).to_numpy().astype(np.float64)
        self.q_bid = q["bid_price"].to_numpy().astype(np.float64)
        self.q_ask = q["ask_price"].to_numpy().astype(np.float64)

        b = (loader.load_daily(family, "bookcurves", [date])
             .select("wts", "local_timestamp_us", "bid_depth_5c", "ask_depth_5c")
             .collect().sort("wts", "local_timestamp_us"))
        self.b_wts = b["wts"].to_numpy()
        self.b_ts = b["local_timestamp_us"].to_numpy()
        self.b_bd = b["bid_depth_5c"].to_numpy().astype(np.float64)
        self.b_ad = b["ask_depth_5c"].to_numpy().astype(np.float64)

        t = (loader.load_daily(family, "trades", [date])
             .select("wts", "local_timestamp_us", "price", "size")
             .collect().sort("wts", "local_timestamp_us"))
        self.t_wts = t["wts"].to_numpy()
        self.t_ts = t["local_timestamp_us"].to_numpy()
        self.t_cumsz = np.cumsum(t["size"].to_numpy().astype(np.float64))

        # Binance aggTrades (event ts + latency = availability)
        bin_path = f"data/processed/binance/aggTrades/{date}.parquet"
        prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
        paths = [p for p in (f"data/processed/binance/aggTrades/{prev}.parquet", bin_path)
                 if os.path.exists(p)]
        a = pl.concat([pl.read_parquet(p) for p in paths]).sort("ts_us")
        self.a_ts = a["ts_us"].to_numpy() + BINANCE_LAT_US
        px = a["price"].to_numpy().astype(np.float64)
        qty = a["qty"].to_numpy().astype(np.float64)
        sign = np.where(a["is_buyer_maker"].to_numpy(), -1.0, 1.0)  # taker buy = +
        self.a_px = px
        self.a_cum_qty = np.cumsum(qty)
        self.a_cum_sqty = np.cumsum(sign * qty)
        self.a_cum_pq = np.cumsum(px * qty)
        self.a_cum_n = np.arange(1, len(px) + 1, dtype=np.float64)
        self.a_logpx = np.log(px)

        # 1s kline returns for realized vol
        kpaths = [f"data/processed/binance/klines_1s/{d}.parquet" for d in (prev, date)]
        k = pl.concat([pl.read_parquet(p) for p in kpaths if os.path.exists(p)]).sort("open_time_us")
        kc = k["close"].to_numpy().astype(np.float64)
        self.k_ts = k["open_time_us"].to_numpy() + 1_000_000 + BINANCE_LAT_US  # bar close time
        r = np.diff(np.log(kc), prepend=np.log(kc[0]))
        self.k_cum_r2 = np.cumsum(r * r)

        # Chainlink (may be absent pre-2026-04-02)
        try:
            cp = (loader.load_crypto_prices([date]).select("local_timestamp_us", "timestamp_us", "price")
                  .collect().sort("local_timestamp_us"))
            self.c_ts = cp["local_timestamp_us"].to_numpy()
            self.c_src_ts = cp["timestamp_us"].to_numpy()
            self.c_px = cp["price"].to_numpy().astype(np.float64)
        except (FileNotFoundError, loader.HoldoutViolation):
            self.c_ts = None

    def win_slice(self, arr_wts: np.ndarray, wts: int) -> slice:
        lo = np.searchsorted(arr_wts, wts, side="left")
        hi = np.searchsorted(arr_wts, wts, side="right")
        return slice(lo, hi)


def binance_feats(F: DayFrames, T: np.ndarray) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    i_now = _asof(F.a_ts, T)
    px_now = np.where(i_now >= 0, F.a_px[np.clip(i_now, 0, None)], np.nan)
    lp_now = np.where(i_now >= 0, F.a_logpx[np.clip(i_now, 0, None)], np.nan)
    for h in RET_HORIZONS_S:
        i_past = _asof(F.a_ts, T - h * 1_000_000)
        lp_past = np.where(i_past >= 0, F.a_logpx[np.clip(i_past, 0, None)], np.nan)
        out[f"bret_{h}s"] = lp_now - lp_past
    for h in FLOW_S:
        i_past = _asof(F.a_ts, T - h * 1_000_000)
        ok = (i_now >= 0) & (i_past >= 0)
        d = lambda c: np.where(ok, c[np.clip(i_now, 0, None)] - c[np.clip(i_past, 0, None)], np.nan)
        vol = d(F.a_cum_qty)
        out[f"ofi_{h}s"] = np.where(vol > 0, d(F.a_cum_sqty) / np.maximum(vol, 1e-9), 0.0)
        out[f"intensity_{h}s"] = d(F.a_cum_n) / h
        vwap = np.where(vol > 0, d(F.a_cum_pq) / np.maximum(vol, 1e-9), np.nan)
        if h == 60:
            out["vwap_dev_60s"] = np.where(np.isfinite(vwap), px_now / vwap - 1, np.nan)
    for lb in VOL_LOOKBACKS_S:
        i2 = _asof(F.k_ts, T)
        i1 = _asof(F.k_ts, T - lb * 1_000_000)
        ok = (i1 >= 0) & (i2 > i1)
        n = np.maximum(i2 - i1, 1)
        var = np.where(ok, (F.k_cum_r2[np.clip(i2, 0, None)]
                            - F.k_cum_r2[np.clip(i1, 0, None)]) / n, np.nan)
        out[f"rvol_{lb}s"] = np.sqrt(np.maximum(var, 0))  # per-1s-return std
    return out


def build_day(family: str, date: str) -> pl.DataFrame | None:
    try:
        F = DayFrames(family, date)
    except FileNotFoundError:
        return None
    d0 = int(dt.datetime.fromisoformat(date + "T00:00:00+00:00").timestamp())
    meta = W.market_meta(family, d0, d0 + 86400).sort("wts")
    if meta.is_empty():
        return None
    wts_arr = meta["wts"].to_numpy()
    res = meta["result_id"].to_numpy()
    up_won = np.where(res == "0", 1.0, np.where(res == "1", 0.0, np.nan))
    # prior outcome + streak (availability = prior window end + delay)
    prior_out = np.full(len(wts_arr), np.nan)
    streak = np.full(len(wts_arr), np.nan)
    run = 0
    for i in range(1, len(wts_arr)):
        if wts_arr[i - 1] + F.dur == wts_arr[i] and np.isfinite(up_won[i - 1]):
            prior_out[i] = up_won[i - 1]
            run = run + 1 if i >= 2 and up_won[i - 2] == up_won[i - 1] else 1
            streak[i] = run * (1 if up_won[i - 1] == 1 else -1)
        else:
            run = 0
    offsets = OFFSETS[family]
    rows: list[dict] = []
    n = len(wts_arr)
    for j, off in enumerate(offsets):
        T = (wts_arr + off) * 1_000_000  # decision times, one per window
        feats: dict[str, np.ndarray] = {}
        feats.update(binance_feats(F, T))
        # per-window Polymarket as-of lookups
        pm_mid = np.full(n, np.nan); pm_spread = np.full(n, np.nan)
        pm_bid = np.full(n, np.nan); pm_ask = np.full(n, np.nan)
        vel = {h: np.full(n, np.nan) for h in ODDS_VEL_S}
        imb = np.full(n, np.nan); vol_sofar = np.full(n, np.nan)
        for i, w_ in enumerate(wts_arr):
            s = F.win_slice(F.q_wts, w_)
            if s.stop > s.start:
                ts = F.q_ts[s]
                k = int(_asof(ts, np.array([T[i]]))[0])
                if k >= 0:
                    pm_mid[i] = F.q_mid[s][k]; pm_spread[i] = F.q_spread[s][k]
                    pm_bid[i] = F.q_bid[s][k]; pm_ask[i] = F.q_ask[s][k]
                    for h in ODDS_VEL_S:
                        k2 = int(_asof(ts, np.array([T[i] - h * 1_000_000]))[0])
                        if k2 >= 0:
                            vel[h][i] = F.q_mid[s][k] - F.q_mid[s][k2]
            sb = F.win_slice(F.b_wts, w_)
            if sb.stop > sb.start:
                kb = int(_asof(F.b_ts[sb], np.array([T[i]]))[0])
                if kb >= 0:
                    bd, ad = F.b_bd[sb][kb], F.b_ad[sb][kb]
                    if bd + ad > 0:
                        imb[i] = (bd - ad) / (bd + ad)
            st = F.win_slice(F.t_wts, w_)
            if st.stop > st.start:
                kt = int(_asof(F.t_ts[st], np.array([T[i]]))[0])
                base = F.t_cumsz[st.start - 1] if st.start > 0 else 0.0
                vol_sofar[i] = (F.t_cumsz[st][kt] - base) if kt >= 0 else 0.0
        feats.update({"pm_mid": pm_mid, "pm_spread": pm_spread, "pm_bid": pm_bid,
                      "pm_ask": pm_ask, "book_imb": imb, "pm_vol_sofar": vol_sofar,
                      "dist_50": pm_mid - 0.5})
        for h in ODDS_VEL_S:
            feats[f"odds_vel_{h}s"] = vel[h]
        # prior window ends AT wts; its outcome becomes public a moment later
        prior_avail_ts = wts_arr * 1_000_000 + PRIOR_OUTCOME_DELAY_US
        feats["prior_up"] = np.where(T >= prior_avail_ts, prior_out, np.nan)
        feats["streak"] = np.where(T >= prior_avail_ts, streak, np.nan)
        # fair value from Chainlink (window open known after first tick >= wts)
        fv = np.full(n, np.nan); delta = np.full(n, np.nan)
        if F.c_ts is not None and off >= 1:
            for i, w_ in enumerate(wts_arr):
                io = np.searchsorted(F.c_src_ts, w_ * 1_000_000, side="left")
                if io >= len(F.c_ts) or F.c_ts[io] > T[i]:
                    continue
                open_px = F.c_px[io]
                kc = int(_asof(F.c_ts, np.array([T[i]]))[0])
                if kc < 0:
                    continue
                delta[i] = F.c_px[kc] / open_px - 1
            t_rem = np.maximum(F.dur - off, 1)
            sig = feats["rvol_300s"] * np.sqrt(t_rem)
            fv = np.where(np.isfinite(delta) & (sig > 0), norm.cdf(delta / sig), np.nan)
        feats["cl_delta_from_open"] = delta
        feats["fair_value_gauss"] = fv
        feats["edge_vs_ask"] = fv - pm_ask
        base = {"wts": wts_arr, "t_offset": np.full(n, off, dtype=np.int64),
                "up_won": up_won,
                "hour": (wts_arr % 86400) // 3600,
                "dow": ((wts_arr // 86400) + 4) % 7}
        rows.append(pl.DataFrame({**base, **{k: v for k, v in feats.items()}}))
    out = pl.concat(rows).sort("wts", "t_offset")
    path = f"results/features/{family}/{date}.parquet"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.write_parquet(path, compression="zstd")
    return out


if __name__ == "__main__":
    fam, date = sys.argv[1], sys.argv[2]
    df = build_day(fam, date)
    print(f"{fam} {date}: {0 if df is None else len(df)} feature rows, "
          f"{0 if df is None else df.width} cols")
