"""GATE 0 unit tests: fee calculator vs Polymarket's documented worked examples.

Source table: docs.polymarket.com/trading/fees.md (fetched 2026-07-06), crypto tab,
100 shares. Values are the official published USDC fees at 2dp.
"""
import sys

sys.path.insert(0, "src")
import fees

# (price, documented_fee_for_100_shares) — full official crypto table
DOC_TABLE = [
    (0.01, 0.07), (0.05, 0.33), (0.10, 0.63), (0.15, 0.89), (0.20, 1.12),
    (0.25, 1.31), (0.30, 1.47), (0.35, 1.59), (0.40, 1.68), (0.45, 1.73),
    (0.50, 1.75), (0.55, 1.73), (0.60, 1.68), (0.65, 1.59), (0.70, 1.47),
    (0.75, 1.31), (0.80, 1.12), (0.85, 0.89), (0.90, 0.63), (0.95, 0.33),
    (0.99, 0.07),
]


def test_documented_worked_examples_exact():
    for p, doc_fee in DOC_TABLE:
        got = fees.taker_fee(100, p, "2026-06-15", "5m")
        assert round(got, 2) == doc_fee, f"p={p}: {got} != {doc_fee}"


def test_symmetry():
    for p in (0.1, 0.25, 0.37, 0.44):
        a = fees.taker_fee(100, p, "2026-06-15", "5m")
        b = fees.taker_fee(100, 1 - p, "2026-06-15", "5m")
        assert abs(a - b) < 1e-9


def test_pre_fee_era_is_free():
    assert fees.taker_fee(100, 0.5, "2025-11-15", "5m") == 0.0
    assert fees.taker_fee(100, 0.5, "2026-01-04", "15m") == 0.0


def test_current_era_is_not_free():
    assert fees.taker_fee(100, 0.5, "2026-07-01", "5m") == 1.75


def test_makers_pay_zero():
    assert fees.maker_fee(1000, 0.5, "2026-07-01", "5m") == 0.0


def test_linear_in_shares():
    one = fees.taker_fee(1, 0.42, "2026-06-15", "5m")
    forty = fees.taker_fee(40, 0.42, "2026-06-15", "5m")
    assert abs(forty - 40 * one) < 1e-4  # 5dp rounding tolerance


def test_precision_5dp():
    # tiny trades near extremes can round to zero (documented)
    assert fees.taker_fee(0.001, 0.01, "2026-06-15", "5m") == 0.0


def test_historical_documented_peaks():
    """Changelog worked examples: peak 1.56% (Jan 5 era) and 1.80% (V2, Mar 30)."""
    import importlib
    importlib.reload(fees)
    # 15m, Feb 2026: peak fee per 100 shares at 50c = $1.56
    assert round(fees.taker_fee(100, 0.5, "2026-02-01", "15m"), 2) == 1.56
    # V2 era April: $1.80
    assert round(fees.taker_fee(100, 0.5, "2026-04-15", "5m"), 2) == 1.80
    # post-May-7: $1.75 (current docs table)
    assert round(fees.taker_fee(100, 0.5, "2026-06-15", "5m"), 2) == 1.75
    # 5m markets did not exist / no fees before Feb 12
    assert fees.taker_fee(100, 0.5, "2026-01-20", "5m") == 0.0
    # 4h fee-free until Mar 6
    assert fees.taker_fee(100, 0.5, "2026-02-20", "4h") == 0.0
