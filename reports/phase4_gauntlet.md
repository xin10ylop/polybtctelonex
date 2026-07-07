# Phase 4 — Validation Gauntlet

Generated 2026-07-07 14:14 UTC. Sources: grid_15m_l250.parquet, grid_15m_ml.parquet, grid_5m_ext.parquet, grid_5m_l1s.parquet, grid_5m_l250.parquet, grid_5m_l3s.parquet, grid_5m_ml.parquet, grid_5m_ml_preopen.parquet, grid_5m_preopen.parquet, grid_secondgen_l250.parquet.
All results post-fee (date-correct regimes) + real book-walk slippage, 250ms latency unless tagged otherwise. Flat $-notional per trade.

## The funnel

| filter | configs remaining |
|---|---|
| all configs evaluated | 13,737 |
| (1) >=300 validation trades | 10,212 |
| (2) val t>=3 AND pf>=1.15 | 0 |
| (3) val maxDD <= 35% of 20x notional | 0 |
| (4) val >= 50% of train, same sign | 0 |
| (5) deflated significance t>=4.37 (M=13737) | 0 |

## In-sample vs out-of-sample diagnostics

- corr(train mean P&L, val mean P&L) across 8,091 adequately-sized configs: **0.840**
- top train-decile configs' average VAL mean per trade: **$-16.43**
- share of configs with positive val mean: **1.2%**

## Per-family survival

| family tag | configs | val n>=300 | + t>=3&pf>=1.15 | best val t | best val pf | max val n |
|---|---|---|---|---|---|---|
| legacy_fv | 240 | 72 | 0 | 457.15 | inf | 466 |
| preopen_m15_down | 60 | 12 | 0 | 298.95 | inf | 5185 |
| preopen_prior_fade_up | 60 | 12 | 0 | 275.96 | inf | 4385 |
| preopen_prior_follow_down | 60 | 12 | 0 | 232.96 | inf | 4385 |
| preopen_prior_fade_down | 60 | 12 | 0 | 227.49 | inf | 4410 |
| preopen_prior_follow_up | 60 | 12 | 0 | 106.36 | inf | 4410 |
| preopen_m15_up | 60 | 12 | 0 | 76.19 | inf | 5350 |
| leadlag | 2052 | 0 | 0 | 37.80 | inf | 96 |
| preopen_blind_up | 60 | 16 | 0 | 36.67 | inf | 13936 |
| preopen_prior2_follow | 60 | 12 | 0 | 25.58 | inf | 7011 |
| secondgen | 80 | 63 | 0 | 11.10 | inf | 4125 |
| preopen_binance_5m | 60 | 16 | 0 | 4.53 | inf | 13920 |
| fv | 2280 | 2155 | 0 | 2.14 | 1.42 | 4458 |
| mined | 6308 | 5980 | 0 | 2.07 | inf | 15539 |
| ml_logit_all | 9 | 8 | 0 | 1.09 | 1.38 | 9866 |
| legacy_blind | 240 | 148 | 0 | 0.98 | 1.33 | 4602 |
| mom | 342 | 318 | 0 | 0.96 | 1.21 | 5957 |
| ml_logit_pm_only | 9 | 7 | 0 | 0.77 | 1.46 | 6145 |
| calib_pocket | 171 | 171 | 0 | 0.74 | 1.04 | 4246 |
| mrev | 342 | 318 | 0 | 0.66 | 1.09 | 5959 |
| preopen_prior2_fade | 60 | 12 | 0 | 0.61 | inf | 7011 |
| preopen_binance_1m | 60 | 12 | 0 | 0.60 | inf | 13502 |
| preopen_blind_down | 60 | 16 | 0 | 0.23 | inf | 13936 |
| legacy_gated | 240 | 148 | 0 | 0.19 | 1.02 | 4437 |
| xtf | 120 | 108 | 0 | 0.06 | 1.01 | 5732 |
| xtf_mined | 320 | 296 | 0 | 0.01 | 1.00 | 15539 |
| ml_lgbm_all | 9 | 9 | 0 | -0.25 | 0.97 | 13186 |
| maker_fv | 40 | 40 | 0 | -0.75 | 0.95 | 6077 |
| maker_bret_up | 40 | 40 | 0 | -0.76 | 0.98 | 6848 |
| maker_xtf_agree_up | 40 | 40 | 0 | -0.78 | 0.97 | 4989 |
| xtf_vel | 20 | 20 | 0 | -1.37 | 0.95 | 5506 |
| ml_lgbm_binance_only | 9 | 9 | 0 | -1.56 | 0.89 | 15457 |
| antistreak | 24 | 24 | 0 | -1.85 | 0.93 | 7798 |
| ml_lgbm_pm_only | 9 | 9 | 0 | -2.23 | 0.89 | 10872 |
| maker_none | 40 | 40 | 0 | -2.60 | 0.94 | 14061 |
| ml_logit_binance_only | 9 | 9 | 0 | -3.27 | 0.92 | 15494 |
| streak_ctl | 24 | 24 | 0 | -3.31 | 0.88 | 7803 |

## Verdict

**ZERO configurations survive the gauntlet.** Filters 6–10 (bootstrap, parameter plateau, regime robustness, fee stress, capacity) were not reached — no candidate cleared filters 1–5. Per Hard Rule 4 this is a valid outcome; see FINAL_REPORT.md.
