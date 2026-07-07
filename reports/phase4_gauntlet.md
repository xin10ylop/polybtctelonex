# Phase 4 — Validation Gauntlet

Generated 2026-07-07 13:41 UTC. Sources: grid_15m_l250.parquet, grid_15m_ml.parquet, grid_5m_l1s.parquet, grid_5m_l250.parquet, grid_5m_l3s.parquet, grid_5m_ml.parquet, grid_secondgen_l250.parquet.
All results post-fee (date-correct regimes) + real book-walk slippage, 250ms latency unless tagged otherwise. Flat $-notional per trade.

## The funnel

| filter | configs remaining |
|---|---|
| all configs evaluated | 12,379 |
| (1) >=300 validation trades | 9,454 |
| (2) val t>=3 AND pf>=1.15 | 0 |
| (3) val maxDD <= 35% of 20x notional | 0 |
| (4) val >= 50% of train, same sign | 0 |
| (5) deflated significance t>=4.34 (M=12379) | 0 |

## In-sample vs out-of-sample diagnostics

- corr(train mean P&L, val mean P&L) across 7,399 adequately-sized configs: **0.834**
- top train-decile configs' average VAL mean per trade: **$-17.38**
- share of configs with positive val mean: **1.4%**

## Per-family survival

| family tag | configs | val n>=300 | + t>=3&pf>=1.15 | best val t | best val pf | max val n |
|---|---|---|---|---|---|---|
| legacy_fv | 240 | 72 | 0 | 457.15 | inf | 466 |
| leadlag | 2052 | 0 | 0 | 37.80 | inf | 96 |
| secondgen | 80 | 63 | 0 | 11.10 | inf | 4125 |
| fv | 2280 | 2155 | 0 | 2.14 | 1.42 | 4458 |
| mined | 6308 | 5980 | 0 | 2.07 | inf | 15539 |
| ml_logit_all | 6 | 5 | 0 | 1.09 | 1.38 | 9866 |
| legacy_blind | 240 | 148 | 0 | 0.98 | 1.33 | 4602 |
| mom | 342 | 318 | 0 | 0.96 | 1.21 | 5957 |
| ml_logit_pm_only | 6 | 4 | 0 | 0.77 | 1.46 | 6145 |
| calib_pocket | 171 | 171 | 0 | 0.74 | 1.04 | 4246 |
| mrev | 342 | 318 | 0 | 0.66 | 1.09 | 5959 |
| legacy_gated | 240 | 148 | 0 | 0.19 | 1.02 | 4437 |
| ml_lgbm_all | 6 | 6 | 0 | -0.25 | 0.97 | 13186 |
| ml_lgbm_binance_only | 6 | 6 | 0 | -1.56 | 0.87 | 15457 |
| antistreak | 24 | 24 | 0 | -1.85 | 0.93 | 7798 |
| ml_lgbm_pm_only | 6 | 6 | 0 | -2.23 | 0.89 | 10872 |
| streak_ctl | 24 | 24 | 0 | -3.31 | 0.88 | 7803 |
| ml_logit_binance_only | 6 | 6 | 0 | -7.82 | 0.83 | 15494 |

## Verdict

**ZERO configurations survive the gauntlet.** Filters 6–10 (bootstrap, parameter plateau, regime robustness, fee stress, capacity) were not reached — no candidate cleared filters 1–5. Per Hard Rule 4 this is a valid outcome; see FINAL_REPORT.md.
