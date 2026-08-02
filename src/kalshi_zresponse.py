"""The REAL nix2 test on Kalshi 15m — signal, then entry filter.

The earlier Kalshi probe tested the wrong thing: it used the spot-vs-strike
GAP as the signal. nix2's actual signal is the 1-SECOND spot return before the
boundary, normalised by sigma*sqrt(duration). That was never tested here.

This matters because of what the Polymarket 15m work just showed: the signal
survives on 15m (54% at |z| 0.02-0.05) but the ENTRY FILTER destroys it —
whenever the signal is right and the market has noticed, the signal side
prices above 0.4999 and fails the ask gate, leaving only windows where the
market disagreed and was right. That is a property of Polymarket's book, not
of the signal. Kalshi is a different market with different participants, so
the filter could behave differently there.

Two questions, in order:
  1. SIGNAL   — does the hit rate rise with |z| against Kalshi's BRTI outcome?
  2. FILTER   — among windows where Kalshi's signal-side ask is cheap
                (<= 0.4999), does the edge survive?

Ground truth: settlement-index BRTI at every 15m boundary (strike of the
window opening, settlement of the window closing). Entry prices: 1-minute
candles carrying yes_bid/yes_ask OHLC.

Kalshi YES = "price up". So the signal side's ask is:
    g > 0 (up)   -> yes_ask
    g < 0 (down) -> 1 - yes_bid   (buying NO = selling YES)

  .venv/bin/python src/kalshi_zresponse.py
"""
from __future__ import annotations

import glob
import math

import polars as pl

KL = "data/processed/binance/klines_1s"
DUR = 900


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (float("nan"),) * 2
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sigma_bp(px: dict[int, float], t: int) -> float | None:
    rets, prev = [], px.get(t - 305)
    for s in range(t - 304, t - 4):
        cur = px.get(s)
        if cur and prev and prev > 0:
            rets.append(math.log(cur / prev))
        if cur:
            prev = cur
    if len(rets) < 30:
        return None
    m = sum(rets) / len(rets)
    v = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(v) * math.sqrt(DUR) * 1e4


def curve(label: str, rows: list[dict], key="ok") -> None:
    print(f"\n  --- {label}  (n={len(rows):,}) ---")
    print(f"  {'|z| band':<14}{'n':>7}{'hit':>9}{'95% CI':>18}{'z':>7}")
    for a, b in [(0.00, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 0.20),
                 (0.20, 0.40), (0.40, 99)]:
        sub = [r for r in rows if a <= abs(r["z"]) < b]
        if len(sub) < 40:
            continue
        h = sum(1 for r in sub if r[key])
        lo, hi = wilson(h, len(sub))
        zs = (h / len(sub) - 0.5) / math.sqrt(0.25 / len(sub))
        print(f"  {a:.2f}-{b:<9.2f}{len(sub):>7,}{h/len(sub):>8.2%}"
              f"  [{lo:5.1%},{hi:5.1%}]{zs:>+7.2f}")


def main() -> None:
    # --- BRTI boundaries (strike + settlement) ---
    d = pl.concat([pl.read_parquet(f) for f in
                   sorted(glob.glob("data/kalshi/BTC_settlement_index_*.parquet"))])
    d = d.with_columns(pl.col("price").cast(pl.Float64),
                       (pl.col("timestamp_us") // 1_000_000).alias("ts"))
    brti = dict(zip(d["ts"].to_list(), d["price"].to_list()))

    # --- Binance 1s spot ---
    px: dict[int, float] = {}
    for f in sorted(glob.glob(f"{KL}/*.parquet")):
        day = f.split("/")[-1][:-8]
        if not ("2026-05" <= day <= "2026-07"):
            continue
        k = pl.read_parquet(f, columns=["open_time_us", "close"])
        px.update(zip((k["open_time_us"] // 1_000_000).to_list(),
                      k["close"].to_list()))

    # --- Kalshi entry prices: first 1-min candle of each window ---
    c = pl.concat([pl.read_parquet(f) for f in
                   sorted(glob.glob("data/kalshi/BTC_15m_candles_*.parquet"))])
    c = c.with_columns((pl.col("timestamp_us") // 1_000_000).alias("ts"))
    for col in ("yes_bid_open", "yes_ask_open"):
        c = c.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    c = c.filter(pl.col("ts") % DUR == 0)          # candle at the window open
    quote = {t: (b, a) for t, b, a in
             zip(c["ts"].to_list(), c["yes_bid_open"].to_list(),
                 c["yes_ask_open"].to_list())}
    print(f"BRTI {len(brti):,} boundaries | spot {len(px):,}s | "
          f"open-quotes {len(quote):,}")

    rows = []
    for T, K in brti.items():
        settle = brti.get(T + DUR)
        p1, p2 = px.get(T - 1), px.get(T - 2)
        if settle is None or not p1 or not p2 or p2 <= 0 or not K:
            continue
        g = math.log(p1 / p2) * 1e4
        if g == 0:
            continue
        sg = sigma_bp(px, T)
        if not sg or sg <= 0:
            continue
        up_won = settle > K
        side_up = g > 0
        bid, ask = quote.get(T, (None, None))
        # signal-side ask: YES = "up"; buying DOWN means buying NO = 1 - yes_bid
        sig_ask = ask if side_up else (1 - bid if bid is not None else None)
        rows.append({"z": g / sg, "ok": side_up == up_won, "sig_ask": sig_ask})

    print(f"{len(rows):,} windows with BRTI + spot")
    print("\n=== 1. SIGNAL: does nix2's z predict Kalshi's outcome? ===")
    curve("Kalshi BTC 15m — ALL windows", rows)

    have = [r for r in rows if r["sig_ask"] is not None]
    cheap = [r for r in have if 0.44 <= r["sig_ask"] <= 0.4999]
    print(f"\n=== 2. ENTRY FILTER: {len(cheap):,} of {len(have):,} windows have "
          f"the signal side at 0.44-0.4999 ({100*len(cheap)/max(1,len(have)):.1f}%) ===")
    curve("Kalshi — signal side CHEAP (<=0.4999)", cheap)

    print("\n=== the comparison that matters ===")
    for a, b in [(0.02, 0.05), (0.05, 0.40), (0.02, 0.40)]:
        allw = [r for r in have if a <= abs(r["z"]) < b]
        chp = [r for r in cheap if a <= abs(r["z"]) < b]
        if len(allw) < 40 or len(chp) < 40:
            continue
        ha = sum(1 for r in allw if r["ok"]) / len(allw)
        hc = sum(1 for r in chp if r["ok"]) / len(chp)
        print(f"  |z| {a:.2f}-{b:.2f}:  all {ha:6.2%} (n={len(allw):,})  ->  "
              f"cheap {hc:6.2%} (n={len(chp):,})   kept "
              f"{100*(hc-0.5)/max(1e-9,(ha-0.5)):.0f}%")
    print("\n  Polymarket for reference:  5m kept 42% of its signal edge,")
    print("                             15m kept only 9%.")


if __name__ == "__main__":
    main()
