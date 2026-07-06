"""Date-correct Polymarket fee model for BTC up/down markets (Hard Rule 3).

Verified sources (2026-07-06):
  - Official docs (docs.polymarket.com/trading/fees.md): fee = C * feeRate * p * (1-p),
    taker-only; crypto feeRate 0.07; maker rebate ~20% of taker fees; fees rounded to
    5 decimal places; generalized per-market form fd = {r, e, to} =>
    fee = C * r * (p*(1-p))**e.
  - Live CLOB snapshot (configs/fee_params_snapshot_2026-07-06.json): every active
    btc-updown market has fd = {r: 0.07, e: 1, to: true}.
  - Empirical onchain fills (2026-06-15): per-fill fee ratio obs/model in [0.999, 1.010];
    fees appear computed on the taker order's aggregate price, then apportioned by shares.

Regime boundaries (from the run brief; *_EMPIRICAL entries are refined by
fit_fee_history.py during bulk download and stored in configs/fee_regimes.json):
  - before 2026-01-05: no taker fees on these markets
  - ~2026-01: dynamic taker fees on 15m first, then 5m
  - 2026-03-30 onward: expanded; crypto r=0.07, e=1 (matches live snapshot)
"""
from __future__ import annotations

import datetime as dt
import json
import os

# (from_date_inclusive, to_date_exclusive, rate, exponent) per family.
# None dates = open-ended. Initial table; empirically refined during Phase 0.6.
DEFAULT_REGIMES: dict[str, list[tuple[str | None, str | None, float, float]]] = {
    "5m": [
        (None, "2026-01-05", 0.0, 1.0),
        ("2026-01-05", None, 0.07, 1.0),  # start date to be refined from fills
    ],
    "15m": [
        (None, "2026-01-05", 0.0, 1.0),
        ("2026-01-05", None, 0.07, 1.0),
    ],
    "4h": [
        (None, "2026-01-05", 0.0, 1.0),
        ("2026-01-05", None, 0.07, 1.0),
    ],
    "1h": [
        (None, "2026-01-05", 0.0, 1.0),
        ("2026-01-05", None, 0.07, 1.0),
    ],
}

_REGIMES_PATH = "configs/fee_regimes.json"


def load_regimes() -> dict:
    if os.path.exists(_REGIMES_PATH):
        with open(_REGIMES_PATH) as f:
            return json.load(f)
    return DEFAULT_REGIMES


_REGIMES = load_regimes()


def params(date: str | dt.date, family: str) -> tuple[float, float]:
    """(rate, exponent) applicable to a trade dated `date` in `family`."""
    d = str(date)[:10]
    for lo, hi, r, e in _REGIMES[family]:
        if (lo is None or d >= lo) and (hi is None or d < hi):
            return r, e
    raise ValueError(f"no fee regime for {family} {d}")


def taker_fee(shares: float, price: float, date: str | dt.date, family: str) -> float:
    """USDC taker fee, rounded to 5dp (documented precision). Makers pay zero."""
    r, e = params(date, family)
    return round(shares * r * (price * (1.0 - price)) ** e, 5)


def maker_fee(shares: float, price: float, date: str | dt.date, family: str) -> float:
    return 0.0


MAKER_REBATE_CRYPTO = 0.20  # of taker fees, redistributed daily (docs)
