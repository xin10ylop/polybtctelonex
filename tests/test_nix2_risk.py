"""Tests for the nix2 risk engine (bot/live/risk.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bot" / "live"))
from risk import RiskConfig, RiskEngine  # noqa: E402


def eng(**kw):
    return RiskEngine(cfg=RiskConfig(**kw))


def test_stake_is_fraction_of_bankroll_clamped():
    assert eng(bankroll=1000).stake() == 10.0
    assert eng(bankroll=200).stake() == 5.0          # floored at PM minimum
    assert eng(bankroll=100_000).stake() == 50.0     # capped by book capacity


def test_stake_never_sweeps_more_than_twice_the_touch():
    e = eng(bankroll=5000)                            # would want $50
    assert e.stake(touch_usd=6.0) == 12.0             # 2x what rests
    assert e.stake(touch_usd=1.0) == 5.0              # but never below minimum


def test_drawdown_halt_is_bankroll_based_not_stake_multiple():
    """Regression: a stake-multiple threshold could exceed the whole account."""
    # isolate the drawdown rule: one loss per day, streak/daily rules off
    e = eng(bankroll=1000, consecutive_losses=10_000, daily_loss_stakes=1e9)
    for i in range(34):
        e.record(-10.0, 10.0, f"day{i}")
    assert e.state == "RUNNING"
    for i in range(34, 36):
        e.record(-10.0, 10.0, f"day{i}")
    assert e.state == "HALTED" and "drawdown" in e.reason


def test_consecutive_loss_halt_above_observed_streaks():
    e = eng(bankroll=1000, max_drawdown_frac=9.9, daily_loss_stakes=1e9)
    for _ in range(11):
        e.record(-10.0, 10.0, "2026-07-01")
    assert e.state == "RUNNING", "must tolerate the 8-streak seen live"
    e.record(-10.0, 10.0, "2026-07-01")
    assert e.state == "HALTED" and "consecutive" in e.reason


def test_daily_pause_clears_next_day():
    e = eng(bankroll=1000, daily_loss_stakes=3, max_drawdown_frac=9.9)
    for _ in range(3):
        e.record(-10.0, 10.0, "2026-07-01")
    assert e.state == "PAUSED_TODAY"
    assert e.may_trade("2026-07-01")[0] is False
    assert e.may_trade("2026-07-02")[0] is True       # new day clears it


def test_halt_is_sticky_across_days():
    e = eng(bankroll=1000)
    for _ in range(40):
        e.record(-10.0, 10.0, "2026-07-01")
    assert e.state == "HALTED"
    assert e.may_trade("2026-07-09")[0] is False      # only operator clears


def test_decay_detector_silent_while_winning():
    import random
    rnd = random.Random(0)
    e = eng(bankroll=100_000, max_drawdown_frac=9.9, daily_loss_stakes=1e9,
            consecutive_losses=10_000)
    for i in range(400):                              # 53% wins, interleaved
        e.record(10.5 if rnd.random() < 0.53 else -10.4, 10.0, f"d{i//8}")
    assert e.state == "RUNNING"
    assert e.decay_t() > 0


def test_decay_detector_needs_minimum_sample():
    e = eng()
    for _ in range(30):
        e.record(-1.0, 10.0, "2026-07-01")
    assert e.decay_t() is None, "must not judge on a handful of trades"


def test_decay_detector_halts_a_dead_edge():
    e = eng(bankroll=1_000_000, max_drawdown_frac=9.9, daily_loss_stakes=1e9,
            consecutive_losses=10_000)
    for i in range(300):                              # persistently negative
        e.record(-2.0 if i % 3 else 3.0, 10.0, f"d{i//8}")
        if e.state == "HALTED":
            break
    assert e.state == "HALTED" and "decay" in e.reason


def test_status_shape():
    e = eng()
    e.record(5.0, 10.0, "2026-07-01")
    s = e.status()
    assert set(s) == {"state", "reason", "equity", "drawdown", "streak",
                      "n", "decay_t"}
    assert s["equity"] == 5.0 and s["streak"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
