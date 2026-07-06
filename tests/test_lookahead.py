"""GATE 0 look-ahead unit test (Hard Rule 1).

Shift the entire Chainlink price feed FORWARD one window-step: the boundary
lookups then see data from the previous step (i.e., information delayed one
step). If reconstructed outcomes do NOT change materially, boundary joins are
leaking and the engine is broken.

Also asserts the unshifted build matches Polymarket's actual resolutions on
the validation day (>= 99.9%).

Runs on the processed validation day 2026-06-15 (must exist).
"""
import sys

import pytest

sys.path.insert(0, "src")
import windows

DAY = "2026-06-15"


@pytest.fixture(scope="module")
def built():
    base = windows.build_windows("5m", [DAY])
    shifted = windows.build_windows("5m", [DAY], shift_us=300 * 1_000_000)
    return base, shifted


def test_unshifted_matches_actual_resolutions(built):
    base, _ = built
    m, n = windows.reconciliation_rate(base)
    assert n >= 250, f"too few comparable windows: {n}"
    assert m / n >= 0.999, f"reconciliation {m}/{n} below 99.9%"


def test_shifted_data_breaks_results(built):
    base, shifted = built
    b = base.select("wts", "outcome_reconstructed").drop_nulls()
    s = shifted.select("wts", "outcome_reconstructed").drop_nulls()
    j = b.join(s, on="wts", suffix="_s").drop_nulls()
    assert len(j) >= 200
    disagree = (j["outcome_reconstructed"] != j["outcome_reconstructed_s"]).mean()
    # a one-step shift must flip a material share of outcomes;
    # 5-minute BTC direction is near-coin-flip, so expect ~30-60% flips.
    assert disagree > 0.10, (
        f"only {disagree:.1%} of outcomes changed under a one-step shift — "
        "the windows builder is leaking (not reading boundaries as intended)"
    )


def test_open_close_prices_shift(built):
    base, shifted = built
    j = (base.select("wts", "open_chainlink")
         .join(shifted.select("wts", "open_chainlink"), on="wts", suffix="_s")
         .drop_nulls())
    changed = (j["open_chainlink"] != j["open_chainlink_s"]).mean()
    assert changed > 0.90, f"open prices barely moved under shift ({changed:.1%})"
