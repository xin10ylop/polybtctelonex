# Phase 1 — Microstructure Study

Data: TRAIN+VALIDATION only (2025-10-11 → 2026-05-12; HOLDOUT untouched).
5m: 25,909 windows (Feb 12 → May 12). 15m: 20,492 windows (Oct 11 → May 12).
All dollar figures post-verification fee model (configs/fee_regimes.json).
Numeric sources: results/phase1/*.parquet, phase1_scalars.json, leadlag_daily.parquet.

## 1. Calibration — implied probability vs realized outcomes

Market prices are well-calibrated to within ~1¢ across most bands and decision
times. At 60s before expiry (5m family):

| band | n | implied | realized | gap |
|---|---|---|---|---|
| 0.00–0.10 | 3,227 | 0.046 | 0.048 | +0.001 |
| 0.10–0.30 | 3,241 | 0.191 | 0.181 | **−0.010** |
| 0.30–0.45 | 2,004 | 0.374 | 0.383 | +0.009 |
| 0.45–0.55 | 1,283 | 0.501 | 0.495 | −0.006 |
| 0.55–0.70 | 1,990 | 0.626 | 0.648 | **+0.022** |
| 0.70–0.90 | 3,196 | 0.810 | 0.806 | −0.004 |
| 0.90–1.01 | 3,315 | 0.954 | 0.950 | −0.004 |

**Pocket**: a persistent mild favorite–longshot bias — moderate favorites
(0.55–0.70) resolve ~2.2¢ more often than priced; the mirror band (0.10–0.30)
is ~1¢ overpriced. Full offsets×bands tables: `results/phase1/calibration_*.parquet`.
This pocket feeds the Phase 3 second-generation grid. Note: gross of costs, a
2¢ edge does NOT clear the ~1.7¢ fee + 1¢ spread on its own.

## 2. Lead-lag — Binance → Chainlink → Polymarket odds

Cross-correlation of 250ms returns (positive lag = Binance leads):

| pair | month | median best lag | median corr |
|---|---|---|---|
| Binance → Chainlink | 2026-04 | 1,250 ms | 0.238 |
| Binance → Chainlink | 2026-05 | 1,250 ms | 0.229 |
| Binance → PM odds (5m) | 2026-02 | 250 ms | 0.115 |
| Binance → PM odds (5m) | 2026-03 | 500 ms | 0.112 |
| Binance → PM odds (5m) | 2026-04 | 500 ms | 0.109 |
| Binance → PM odds (5m) | 2026-05 | 500 ms | **0.063** |

Two structurally different lags:
- The **resolution oracle (Chainlink) lags Binance by ~1.25s, stably** — this
  is mechanical (oracle update cadence) and did not decay. Near window close,
  the resolving price is partially knowable ~1s ahead.
- **Polymarket odds lag Binance by only 250–500ms**, and the exploitable
  correlation **decayed ~45% from Feb to May** — MM bots have compressed the
  latency edge; home-latency (250ms+) taker latency-arb is marginal and dying.

## 3. Spread, depth, and realized order costs (5m; walk of real books)

Median spread is pinned at 1¢ for the whole window. Depth and slippage vs
seconds-into-window (median $-slippage vs mid, buy side):

| seconds in window | $50 order | $200 | $1,000 | bid depth ≤5¢ (shares) |
|---|---|---|---|---|
| 0–15 | 0.7¢ | 1.5¢ | 4.3¢ | 1,546 |
| 60–75 | 0.7¢ | 1.5¢ | 4.0¢ | 1,849 |
| 225–240 | 0.9¢ | 1.9¢ | 5.6¢ | 1,830 |
| 270–285 | 1.3¢ | 3.2¢ | 7.8¢ | 1,091 |
| 285–300 | 1.9¢ | 4.7¢ | 9.2¢ | 813 |

Cost is roughly flat for the first 4 minutes and **doubles in the final 30s**
as makers pull depth. $1k taker orders pay 4–9¢ of slippage — capacity is
structurally small, as the brief predicted. Hour-of-day variation is second-
order (~±20% depth around the UTC day; `results/phase1/cost_hourly_*.parquet`).

## 4. Taker vs maker aggregate P&L (on-chain fills, ground truth)

| family | fills | shares | taker P&L (net of fees) | maker P&L (gross) | fees paid |
|---|---|---|---|---|---|
| 5m (Feb–May, all fee-era) | 103.3M | 1.52B | **−$251k** | **−$1.33M** | $1.59M |
| 15m (Oct–May, mostly pre-fee) | 65.1M | 1.26B | **−$2.47M** | **+$2.15M** | $0.32M |

Identity check: taker + maker + fees ≈ 0 in both rows (✓).
- **15m tells the classic story**: makers earned +$2.1M gross off takers.
- **5m reverses it**: takers beat makers by +$1.33M *gross* (fast money picks
  off stale quotes in 5-minute windows), but fees ($1.59M) flip takers to a
  net −$251k. After ~20% maker rebates (~+$0.32M), makers still net ≈ −$1.0M.
  **In the 5m fee era, BOTH aggregate sides lose; the fee pool is the only
  structural winner.** Any surviving strategy must beat this baseline.

## 5. Serial dependence of window outcomes

| family | n | share Up | runs z | p | lag-1 autocorr |
|---|---|---|---|---|---|
| 5m | 25,909 | 0.504 | +3.09 | 0.002 | −0.019 |
| 15m | 20,492 | 0.501 | +6.12 | <0.001 | −0.043 |

Outcomes are **anti-persistent** (more alternations than chance) — statistically
decisive, economically tiny: fading the previous outcome implies ≈52.1% hit rate
(15m), which does not clear the 51.75% hold-to-expiry breakeven plus spread.
**Verdict for Phase 3 sizing: streak-based compounding has NO empirical basis;
if anything the sign is against it. It stays in the grid as a control only.**

## 6. The 50¢ post-mortem (current fees, 100 shares)

- Taker-buy at 50¢: fee **$1.75**; taker-sell at 55¢: fee **$1.73**.
- Taker→taker round trip captures $5.00 gross → **$1.52 net** (70% consumed by
  fees) before spread/slippage; subtracting the ~1¢ spread each way (~$2.00)
  makes the blind version **negative**.
- Taker-buy → maker-sell at +5¢ keeps $3.25 pre-rebate (maker leg fee-free) but
  bears non-fill risk in a 5-minute window.
- Hold-to-expiry from 50¢ needs a **51.75% win rate** to break even on fees
  alone; section 5 shows no free serial signal reaching that; section 1's
  0.55–0.70 pocket (+2.2¢) is the only calibration edge of comparable size and
  it sits below cost. **The legacy blind-50¢ strategy is dead under current
  fees; only a filtered (model-gated) variant could survive, to be tested in
  Phase 3.**

## GATE 1 verdict

All six sections have numeric answers → **PASS**. Key inputs to later phases:
the 0.55–0.70 calibration pocket, the stable 1.25s oracle lag (vs decaying
250–500ms odds lag), late-window cost doubling, anti-persistence (anti-streak),
and the both-sides-lose 5m fee-era baseline.
