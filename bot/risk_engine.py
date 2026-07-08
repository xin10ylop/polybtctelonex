"""NIXULTIMATE risk engine — every rule the live bot must obey, as pure logic.

No feeds, no orders, no I/O: the engine receives signals and results and
answers two questions — "may this trade happen, and at what stake?" and
"must we stop?". The live bot wraps this around real WebSocket feeds and the
CLOB client; paper mode wraps it around simulated fills. Same engine either
way, so what we paper-test is exactly what later trades real money.

Rule sources (all measured in FINAL_REPORT.md):
  - bankroll >= 20x stake        dev max drawdown was 8.5x stake (App. 7/8)
  - basis guard                  the two Jul 6 fake signals: contrarian entry
                                 (ask<0.5) while |Binance - Chainlink anchor|
                                 > 5bp (App. 7 failure analysis)
  - tape confirmation            required in every backtest fill; silently
                                 saved both Jul 6 losers
  - broadcast-delay kill         < 0.4s median = the free feed's raison
                                 d'etre is gone (App. 6 kill-switch)
  - rolling wr / slippage kills  holdout-era calibration (App. 6)
  - EV gate                      fair - ask - fee >= 2c, frozen
State machine: RUNNING -> (PAUSED_TODAY | HALTED). Pauses clear at UTC
midnight; halts clear only by operator intervention.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


def load_config(path: str | Path = Path(__file__).parent / "config.json") -> dict:
    return json.loads(Path(path).read_text())


@dataclass
class Signal:
    """One candidate trade at T = window + toff, all fields feed-derived."""
    family: str                 # "5m" | "15m"
    window_ts: int              # unix window start
    dir_up: bool
    fair: float                 # model win probability, Phi(|z|)
    ask: float                  # token-space cost incl. book walk at stake size
    fee_rate: float             # live fee param for this family
    basis_bp: float             # |Binance - Chainlink anchor| in bp at T
    tape_confirmed: bool        # a real print <= ask+1c within confirm window
    broadcast_delay_med_s: float  # rolling median of PM broadcast delay
    book_exhausted: bool = False  # book-walk could not fill the stake


@dataclass
class TradeResult:
    family: str
    day: str                    # "YYYY-MM-DD" UTC
    stake: float
    pnl: float
    fill_slippage: float        # realized fill px - model ask (>= 0 is worse)


@dataclass
class Decision:
    approved: bool
    stake: float = 0.0
    reasons: list[str] = field(default_factory=list)


class RiskEngine:
    def __init__(self, cfg: dict, bankroll: float, rung: int = 0,
                 paper: bool = True):
        self.cfg = cfg
        self.bankroll = float(bankroll)
        self.rung = rung
        self.paper = paper
        self.halted: str | None = None      # reason string when halted
        self.paused_day: str | None = None  # UTC day for which we are paused
        self.open_positions = 0
        r = cfg["risk"]
        self.wr_window: deque[bool] = deque(maxlen=r["kill_rolling_wr_window"])
        self.slip_window: deque[float] = deque(maxlen=r["kill_slippage_window"])
        self.day: str | None = None
        self.day_pnl = 0.0
        self.red_day_streak = 0
        self.rung_days = 0
        self.rung_trades = 0
        self.rung_pnl = 0.0
        self.week_pnl = 0.0
        self.week_days = 0
        self.recent_interruption = False    # halt/pause seen since last promo check

    # ---------------- pre-trade ----------------

    def stake(self) -> float:
        ladder = self.cfg["ladder"]["rung_stakes"]
        s = ladder[min(self.rung, len(ladder) - 1)]
        cap = self.bankroll / self.cfg["risk"]["bankroll_multiple_min"]
        return min(float(s), cap)

    def pre_trade(self, sig: Signal, day: str) -> Decision:
        c = self.cfg
        r = c["risk"]
        s = c["signal"]
        reasons = []
        if self.halted:
            return Decision(False, 0.0, [f"HALTED: {self.halted}"])
        if self.paused_day == day:
            return Decision(False, 0.0, ["paused until next UTC day"])
        if sig.broadcast_delay_med_s < r["kill_broadcast_delay_median_s"]:
            self.halt("broadcast delay below 0.4s — structural edge gone")
            return Decision(False, 0.0, [f"HALTED: {self.halted}"])
        exp_rate = r["expected_fee_rate"].get(sig.family)
        if exp_rate is not None and abs(sig.fee_rate - exp_rate) > 1e-9:
            self.halt(f"fee param changed for {sig.family}: "
                      f"{sig.fee_rate} != {exp_rate}")
            return Decision(False, 0.0, [f"HALTED: {self.halted}"])
        if sig.book_exhausted:
            reasons.append("book too thin for stake")
        if not (0.02 < sig.ask < 0.995):
            reasons.append("ask out of tradable range")
        ev = sig.fair - sig.ask - sig.fee_rate * sig.ask * (1.0 - sig.ask)
        if ev < s["ev_margin"]:
            reasons.append(f"EV gate: {ev:.4f} < {s['ev_margin']}")
        if not sig.tape_confirmed:
            reasons.append("no tape confirmation")
        if (sig.ask < r["basis_guard_ask_below"]
                and sig.basis_bp > r["basis_guard_bp"]):
            reasons.append(f"basis guard: contrarian entry with basis "
                           f"{sig.basis_bp:.1f}bp > {r['basis_guard_bp']}bp")
        if self.open_positions >= r["max_concurrent_positions"]:
            reasons.append("max concurrent positions")
        stake = self.stake()
        if stake <= 0:
            reasons.append("bankroll too small for any stake")
        if self.day_pnl - stake < -r["daily_loss_pause_stakes"] * stake:
            # this trade could push the day past the pause line
            if self.day_pnl <= -r["daily_loss_pause_stakes"] * stake:
                self.paused_day = day
                self.recent_interruption = True
                reasons.append("daily loss limit — paused until next UTC day")
        if reasons:
            return Decision(False, 0.0, reasons)
        return Decision(True, stake, ["ok"])

    # ---------------- post-trade ----------------

    def on_open(self) -> None:
        self.open_positions += 1

    def post_trade(self, res: TradeResult) -> None:
        self.open_positions = max(0, self.open_positions - 1)
        self._roll_day(res.day)
        self.day_pnl += res.pnl
        self.rung_trades += 1
        self.rung_pnl += res.pnl
        self.week_pnl += res.pnl
        self.wr_window.append(res.pnl > 0)
        self.slip_window.append(res.fill_slippage)
        r = self.cfg["risk"]
        if (len(self.wr_window) == self.wr_window.maxlen
                and sum(self.wr_window) / len(self.wr_window) < r["kill_rolling_wr_min"]):
            self.halt(f"rolling {self.wr_window.maxlen}-trade win rate below "
                      f"{r['kill_rolling_wr_min']:.0%}")
        if (len(self.slip_window) == self.slip_window.maxlen
                and sum(self.slip_window) / len(self.slip_window) > r["kill_slippage_max_avg"]):
            self.halt("avg fill slippage above 1c over "
                      f"last {self.slip_window.maxlen} trades")

    # ---------------- day / ladder ----------------

    def _roll_day(self, day: str) -> None:
        if self.day is None:
            self.day = day
            return
        if day == self.day:
            return
        # close previous day
        if self.day_pnl < 0:
            self.red_day_streak += 1
            if self.red_day_streak >= self.cfg["risk"]["kill_consecutive_red_days"]:
                self.halt(f"{self.red_day_streak} consecutive red days")
        else:
            self.red_day_streak = 0
        self.day = day
        self.day_pnl = 0.0
        self.paused_day = None
        self.rung_days += 1
        self.week_days += 1
        if self.week_days >= 7:
            self._weekly_ladder_review()

    def _weekly_ladder_review(self) -> None:
        lad = self.cfg["ladder"]
        if lad["demote_on_losing_week"] and self.week_pnl < 0 and self.rung > 0:
            self.rung -= 1
            self._reset_rung()
        elif self._promotion_ok():
            self.rung = min(self.rung + 1, len(lad["rung_stakes"]) - 1)
            self._reset_rung()
        self.week_pnl = 0.0
        self.week_days = 0
        self.recent_interruption = False

    def _promotion_ok(self) -> bool:
        lad = self.cfg["ladder"]
        r = self.cfg["risk"]
        if self.recent_interruption or self.halted:
            return False
        if self.rung_days < lad["promote_min_days_on_rung"]:
            return False
        if self.rung_trades < lad["promote_min_trades_on_rung"]:
            return False
        if lad["promote_requires_positive_rung_pnl"] and self.rung_pnl <= 0:
            return False
        if (len(self.wr_window) < self.wr_window.maxlen
                or sum(self.wr_window) / len(self.wr_window) < lad["promote_min_rolling_wr"]):
            return False
        stakes = lad["rung_stakes"]
        if self.rung + 1 < len(stakes):
            nxt = stakes[self.rung + 1]
            if self.bankroll < r["bankroll_multiple_min"] * nxt:
                return False
        return True

    def _reset_rung(self) -> None:
        self.rung_days = 0
        self.rung_trades = 0
        self.rung_pnl = 0.0

    # ---------------- halts ----------------

    def halt(self, reason: str) -> None:
        if not self.halted:
            self.halted = reason
            self.recent_interruption = True

    def operator_clear_halt(self) -> None:
        """Only a human clears a halt — and demotes to the bottom rung."""
        self.halted = None
        self.rung = 0
        self._reset_rung()
        self.wr_window.clear()
        self.slip_window.clear()
        self.red_day_streak = 0
