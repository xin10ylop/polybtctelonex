"""Unit tests for the NIXULTIMATE risk engine — every rule must fire."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.risk_engine import Decision, RiskEngine, Signal, TradeResult, load_config


def good_signal(**kw) -> Signal:
    d = dict(family="5m", window_ts=1_780_000_000, dir_up=True, fair=0.999,
             ask=0.90, fee_rate=0.07, basis_bp=1.0, tape_confirmed=True,
             broadcast_delay_med_s=1.1, book_exhausted=False)
    d.update(kw)
    return Signal(**d)


def engine(bankroll=100.0, rung=0) -> RiskEngine:
    return RiskEngine(load_config(), bankroll=bankroll, rung=rung)


def test_good_signal_approved_at_ladder_stake():
    d = engine().pre_trade(good_signal(), "2026-07-08")
    assert d.approved and d.stake == 5.0


def test_ev_gate_blocks():
    d = engine().pre_trade(good_signal(ask=0.995 - 1e-6, fair=0.999), "2026-07-08")
    assert not d.approved and any("EV gate" in r or "ask out" in r for r in d.reasons)


def test_tape_confirmation_required():
    d = engine().pre_trade(good_signal(tape_confirmed=False), "2026-07-08")
    assert not d.approved and any("tape" in r for r in d.reasons)


def test_basis_guard_blocks_contrarian_only():
    e = engine()
    blocked = e.pre_trade(good_signal(ask=0.25, basis_bp=8.0), "2026-07-08")
    assert not blocked.approved and any("basis guard" in r for r in blocked.reasons)
    fine = e.pre_trade(good_signal(ask=0.90, basis_bp=8.0), "2026-07-08")
    assert fine.approved  # guard applies only below the 0.5 ask line


def test_broadcast_delay_halts_structurally():
    e = engine()
    d = e.pre_trade(good_signal(broadcast_delay_med_s=0.3), "2026-07-08")
    assert not d.approved and e.halted and "broadcast" in e.halted


def test_fee_change_halts():
    e = engine()
    d = e.pre_trade(good_signal(fee_rate=0.05), "2026-07-08")
    assert not d.approved and e.halted and "fee param" in e.halted


def test_bankroll_caps_stake():
    e = engine(bankroll=40.0)  # 40/20 = $2 cap < $5 rung stake
    d = e.pre_trade(good_signal(), "2026-07-08")
    assert d.approved and d.stake == 2.0


def test_concurrent_position_limit():
    e = engine()
    e.on_open()
    e.on_open()
    d = e.pre_trade(good_signal(), "2026-07-08")
    assert not d.approved and any("concurrent" in r for r in d.reasons)


def test_daily_loss_pauses_until_next_day():
    e = engine()
    for _ in range(6):
        e.post_trade(TradeResult("5m", "2026-07-08", 5.0, -5.0, 0.0))
    d = e.pre_trade(good_signal(), "2026-07-08")
    assert not d.approved
    e.post_trade(TradeResult("5m", "2026-07-09", 5.0, 1.0, 0.0))  # day rolls
    d2 = e.pre_trade(good_signal(), "2026-07-09")
    assert d2.approved


def test_rolling_wr_kill():
    e = engine()
    for i in range(100):
        e.post_trade(TradeResult("5m", "2026-07-08", 5.0,
                                 1.0 if i % 2 == 0 else -5.0, 0.0))
    assert e.halted and "win rate" in e.halted


def test_slippage_kill():
    e = engine()
    for _ in range(50):
        e.post_trade(TradeResult("5m", "2026-07-08", 5.0, 1.0, 0.02))
    assert e.halted and "slippage" in e.halted


def test_red_day_streak_kill():
    e = engine()
    for i in range(11):
        e.post_trade(TradeResult("5m", f"2026-07-{8 + i:02d}", 5.0, -1.0, 0.0))
    assert e.halted and "red days" in e.halted


def test_promotion_needs_everything():
    e = engine(bankroll=10_000.0)
    # 8 profitable days, >=100 trades, high wr -> promote at weekly review
    for day in range(8):
        for _ in range(20):
            e.post_trade(TradeResult("5m", f"2026-07-{8 + day:02d}", 5.0, 1.0, 0.0))
    assert e.rung == 1


def test_no_promotion_without_bankroll():
    e = engine(bankroll=100.0)  # can't cover 20x next rung ($25 -> $500)
    for day in range(8):
        for _ in range(20):
            e.post_trade(TradeResult("5m", f"2026-07-{8 + day:02d}", 5.0, 1.0, 0.0))
    assert e.rung == 0


def test_losing_week_demotes():
    e = engine(bankroll=10_000.0, rung=2)
    for day in range(8):
        e.post_trade(TradeResult("5m", f"2026-07-{8 + day:02d}", 100.0, -1.0, 0.0))
    assert e.rung == 1


def test_operator_clear_resets_to_bottom():
    e = engine(rung=3)
    e.halt("test")
    e.operator_clear_halt()
    assert e.halted is None and e.rung == 0
