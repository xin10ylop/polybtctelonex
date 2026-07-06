# Phase 0 — cross-source reconciliation (Telonex vs Polymarket CLOB API)

Generated 2026-07-06 15:25 UTC. Sampled windows: 250 (target >= 200). Comparable: 250.

- Comparison: CLOB `prices-history` (1-min fidelity) vs Telonex two-sided BBO mid: API price must occur in the Telonex mid stream within its preceding 75s bucket (bucket-timing convention verified on window 1781500800).
- Mean abs diff per window: median 0.0000, p95 0.0010, max 0.0046
- Windows within tolerance (mean diff <= $0.005): 250/250 (100.0%)

Worst 10 windows (for investigation):

| family | wts | points | mean_abs_diff |
|---|---|---|---|
| 15m | 1763180100 | 12 | 0.0046 |
| 15m | 1763179200 | 15 | 0.0020 |
| 5m | 1781537700 | 10 | 0.0020 |
| 15m | 1763193600 | 18 | 0.0019 |
| 15m | 1763167500 | 15 | 0.0017 |
| 15m | 1763164800 | 13 | 0.0015 |
| 5m | 1781514900 | 10 | 0.0015 |
| 15m | 1763172900 | 17 | 0.0012 |
| 15m | 1763185500 | 17 | 0.0012 |
| 15m | 1763190900 | 17 | 0.0012 |

Windows without comparable data: 0 (none)
