"""Execution simulation primitives: taker book-walk and maker trade-through fills.

These are the ONLY code paths allowed to produce fill prices in backtests
(Hard Rule 3). Unit-tested against hand-computed values in tests/test_execution.py.
"""
from __future__ import annotations

import numpy as np


def walk_book(levels: list[tuple[float, float]], notional: float) -> tuple[float, float, bool]:
    """Walk price levels [(price, size_shares), ...] best-first with $notional.

    Returns (avg_fill_price, shares_filled, exhausted).
    exhausted=True when the visible book couldn't absorb the full notional.
    Reference implementation — the vectorized version lives in consolidate._walk_curves
    and must agree with this exactly (tested).
    """
    remaining = float(notional)
    shares = 0.0
    spent = 0.0
    for price, size in levels:
        if price <= 0 or size <= 0 or not np.isfinite(price):
            continue
        cost_full = price * size
        if cost_full <= remaining:
            shares += size
            spent += cost_full
            remaining -= cost_full
        else:
            part = remaining / price
            shares += part
            spent += part * price
            remaining = 0.0
            break
    if shares == 0:
        return float("nan"), 0.0, True
    return spent / shares, shares, spent < notional * 0.999


def maker_fill_trade_through(
    limit_price: float,
    side: str,  # "buy" | "sell"
    quantity: float,
    placed_ts_us: int,
    trade_ts_us: np.ndarray,   # sorted ascending, trades on the SAME token
    trade_px: np.ndarray,
    trade_sz: np.ndarray,
    expiry_ts_us: int,
) -> tuple[float, int | None]:
    """Conservative trade-through fill rule for a resting limit order.

    A BUY limit at P is considered filled only by strictly-through prints
    (trade price < P) after placement; trades AT P are assumed to go to queue
    ahead of us (conservative). Symmetrically for sells (trade price > P).
    Fill quantity accumulates from through-prints' sizes until `quantity`.

    Returns (filled_quantity, fill_completed_ts_us | None).
    """
    if side not in ("buy", "sell"):
        raise ValueError(side)
    lo = np.searchsorted(trade_ts_us, placed_ts_us, side="right")
    hi = np.searchsorted(trade_ts_us, expiry_ts_us, side="right")
    px = trade_px[lo:hi]
    sz = trade_sz[lo:hi]
    ts = trade_ts_us[lo:hi]
    through = px < limit_price if side == "buy" else px > limit_price
    if not through.any():
        return 0.0, None
    csum = np.cumsum(np.where(through, sz, 0.0))
    filled = float(min(csum[-1], quantity))
    if csum[-1] >= quantity:
        idx = int(np.searchsorted(csum, quantity, side="left"))
        return float(quantity), int(ts[idx])
    return filled, None
