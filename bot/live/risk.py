"""Risk engine for the nix2 cheap+signal bot — sizing and kill switches.

Design principle: EVERY edge measured in this project decayed within 2-3
months (BTC final-seconds, the alt campaign, ETH's cheap+signal). So the
single most important control is not the drawdown limit — it is a DECAY
DETECTOR that notices the edge dying and halts before it bleeds the account.

Thresholds are calibrated against history (src/nix_riskcal.py), not guessed:
they must (a) essentially never fire during a genuinely profitable regime,
and (b) fire promptly once EV goes to zero or negative.

State: RUNNING -> PAUSED_TODAY (clears at UTC midnight) -> HALTED (operator
must clear). Pure logic, no I/O, so paper and live share identical behavior.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RiskConfig:
    # ---- sizing ----
    # NOT Kelly. Kelly (~8-11% here) maximizes growth but tolerates ruinous
    # drawdowns. Sized instead from the measured drawdown distribution:
    # bootstrap p99 drawdown is ~30 stakes, so 1% of bankroll per trade puts
    # a 1-in-100 bad run at ~30% of the account, inside the halt.
    bankroll: float = 1000.0
    stake_fraction: float = 0.01
    stake_min: float = 5.0            # Polymarket minimum order
    stake_max: float = 50.0           # beyond this the book-walk cost bites
    # ---- kill switches ----
    # drawdown is a fraction of BANKROLL (a stake-multiple threshold can
    # exceed the account entirely — that bug is why this is bankroll-based)
    max_drawdown_frac: float = 0.35       # halt
    daily_loss_stakes: float = 12.0       # pause today
    consecutive_losses: int = 12          # halt (live/hist max streak was 8)
    # ---- decay detector ----
    # CALIBRATED, not guessed (src/nix_riskcal.py sweep). The detector is
    # evaluated after every trade, so it gets many chances to dip: the naive
    # (t<-1.5, n>=60, window 120) setting halted a genuinely PROFITABLE edge
    # 38% of the time. This row: 3.7% false-halt over 800 trades, while still
    # catching a -$0.50/trade dead edge 78% of the time (median 335 trades).
    # A thin edge cannot be killed off quickly without killing live ones too;
    # the drawdown halt is the hard backstop underneath.
    decay_window: int = 400
    decay_t_halt: float = -1.5
    decay_min_n: int = 250


@dataclass
class RiskEngine:
    cfg: RiskConfig = field(default_factory=RiskConfig)
    state: str = "RUNNING"
    reason: str = ""
    equity: float = 0.0               # cumulative pnl since start
    peak: float = 0.0
    day: str = ""
    day_pnl: float = 0.0
    streak: int = 0
    recent: deque = field(default_factory=lambda: deque(maxlen=512))

    # ---------- sizing ----------
    def stake(self, touch_usd: float | None = None) -> float:
        """Stake for the next trade: fractional Kelly on current bankroll,
        clamped to [min, max]. If the touch is thin we still trade (walking
        the book costs ~0.4c median, measured) but never more than 2x what
        rests there, so we don't sweep several levels."""
        s = (self.cfg.bankroll + self.equity) * self.cfg.stake_fraction
        s = max(self.cfg.stake_min, min(self.cfg.stake_max, s))
        if touch_usd is not None and touch_usd > 0:
            s = min(s, max(self.cfg.stake_min, 2.0 * touch_usd))
        return round(s, 2)

    # ---------- gate ----------
    def may_trade(self, utc_day: str) -> tuple[bool, str]:
        if self.state == "HALTED":
            return False, f"HALTED: {self.reason}"
        if self.day and utc_day != self.day and self.state == "PAUSED_TODAY":
            self.state, self.reason = "RUNNING", ""     # new day clears pause
        if self.state == "PAUSED_TODAY":
            return False, f"PAUSED_TODAY: {self.reason}"
        return True, ""

    # ---------- bookkeeping ----------
    def record(self, pnl: float, stake: float, utc_day: str) -> None:
        if utc_day != self.day:
            self.day, self.day_pnl = utc_day, 0.0
            if self.state == "PAUSED_TODAY":
                self.state, self.reason = "RUNNING", ""
        self.equity += pnl
        self.day_pnl += pnl
        self.peak = max(self.peak, self.equity)
        self.streak = self.streak + 1 if pnl < 0 else 0
        self.recent.append(pnl / max(stake, 1e-9))    # normalized per-$1 stake
        self._check(stake)

    def _check(self, stake: float) -> None:
        c = self.cfg
        dd = self.peak - self.equity
        dd_limit = c.max_drawdown_frac * c.bankroll
        if dd >= dd_limit:
            self.state = "HALTED"
            self.reason = (f"drawdown ${dd:.0f} >= ${dd_limit:.0f} "
                           f"({c.max_drawdown_frac:.0%} of bankroll)")
            return
        if self.streak >= c.consecutive_losses:
            self.state = "HALTED"
            self.reason = f"{self.streak} consecutive losses"
            return
        t = self.decay_t()
        if t is not None and t <= c.decay_t_halt:
            self.state = "HALTED"
            self.reason = f"edge decay: rolling t={t:.2f} over {len(self.recent)} trades"
            return
        if -self.day_pnl >= c.daily_loss_stakes * stake:
            self.state = "PAUSED_TODAY"
            self.reason = f"daily loss ${-self.day_pnl:.0f}"

    def decay_t(self) -> float | None:
        """t-stat of the rolling per-$1 EV. None until enough trades."""
        c = self.cfg
        if len(self.recent) < c.decay_min_n:
            return None
        v = list(self.recent)[-c.decay_window:]
        n = len(v)
        m = sum(v) / n
        var = sum((x - m) ** 2 for x in v) / (n - 1)
        if var <= 0:
            return None
        return m / (math.sqrt(var) / math.sqrt(n))

    def status(self) -> dict:
        return {"state": self.state, "reason": self.reason,
                "equity": round(self.equity, 2),
                "drawdown": round(self.peak - self.equity, 2),
                "streak": self.streak, "n": len(self.recent),
                "decay_t": (round(self.decay_t(), 2)
                            if self.decay_t() is not None else None)}
