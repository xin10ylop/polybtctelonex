# FINAL REPORT — Polymarket BTC Up/Down Strategy Discovery

**Date: 2026-07-07. Data: Telonex tick data 2025-10-11 → 2026-07-05 (research
performed on the first 80%; the last ~20% — 2026-05-13 → 2026-07-05 — sits
untouched in `data/HOLDOUT/`).**

---

## VERDICT: Nothing survived.

**Out of 12,379 strategy configurations spanning ten strategy families, an
exhaustive per-feature signal-mining sweep, machine-learning probability
models, and a second-generation refinement pass, ZERO configurations passed
the validation gauntlet.** The best single configuration reached a validation
t-statistic of 1.69 — below the ordinary significance bar (3.0), far below the
multiple-testing-deflated bar (4.34), and below what pure luck alone would be
expected to produce from a search this size. No thresholds were loosened at
any point (Hard Rule 4). The holdout was never opened — nothing earned the
right to touch it.

**Plain-English meaning: with taker fees at their 2026 levels, a ~1¢ spread,
and ≥250ms home latency, the BTC 5-minute and 15-minute up/down markets on
Polymarket are efficient — no retail-accessible systematic edge was found in
9 months of complete tick data.**

---

## Why nothing survives — the microstructure explains it

The Phase 1 study (reports/phase1_microstructure.md) shows the negative result
is structural, not a search failure:

1. **The fee wall.** Since 2026, every taker pays `shares × r × p(1−p)` with
   r currently 0.07 (peak $1.75 per 100 shares at 50¢). A taker round trip at
   mid-prices costs ~$3.48 per 100 shares plus ~$2 of spread — a strategy needs
   a ~5.5¢ gross edge per trade to break even. The largest calibration
   anomaly found in 46,000 windows is 2.2¢.
2. **Both sides already lose.** On-chain, in the 5m fee era, takers netted
   −$251k and makers −$1.0M (after ~20% rebates) while the fee pool collected
   +$1.59M. The counterparty pool a new strategy must beat is *already losing
   to the house in aggregate*.
3. **The latency edge is gone at home scale.** Polymarket odds lag Binance by
   only 250–500ms and that correlation decayed ~45% between February and May.
   The stable edge (the resolution oracle lags Binance ~1.25s) is real, but
   monetizing it requires beating professional MMs to the same trade — at
   250ms+ latency the grid shows it does not clear fees. Latency stress
   (250ms vs 1s vs 3s) barely changed outcomes: best val-t 1.49 / 1.34 / 1.69 —
   i.e., no latency-sensitive alpha was being captured in the first place.
4. **Outcomes are anti-persistent** (runs-test z = +3.1/+6.1), killing
   streak/momentum sizing stories: fading streaks yields ≈52.1% hit rate —
   below the 51.75% fee breakeven once spread is added. Streak-based
   compounding was tested as a control and, as the data demanded, failed.

## What was searched (completeness statement)

| block | configs |
|---|---|
| Fair-value/EV (Gaussian fair value vs book, taker/maker/taker-exit grids) | 720 |
| Lead-lag / latency (Binance-move + quiet-odds gates) | 540 |
| Odds momentum + mean-reversion | 480 |
| Legacy price-level entries at 20/30/50/60/70¢ (blind, signal-gated, FV-gated) | 450 |
| Calibration-pocket (Phase 1's 0.55–0.70 anomaly) | 90 |
| Anti-streak + streak controls | 24 |
| **Exhaustive signal-mining: every feature × train-quantile thresholds × direction × decision-time grid** | ~7,600 |
| Capacity variants ($50/$1,000 notionals on key families) | ~1,300 |
| ML: LightGBM + logistic × 3 feature sets × margins, purged walk-forward CV + isotonic calibration | 36 |
| Second-generation pass (±15/30% parameter neighbors of top TRAIN configs) | 80 |
| **Total** | **12,379** |

Execution realism throughout: real order-book-walk fill prices as-of decision
time + latency, date-correct fee regimes (verified three ways against official
docs, live CLOB parameters, and on-chain fills), conservative strict
trade-through maker fills, one trade per window. Engine verified by GATE-3
audits: 25/25 randomly sampled trades re-derived independently to the cent;
outcome-shift look-ahead test passed (12/12 configs).

## The funnel

| filter | remaining |
|---|---|
| all configs | 12,379 |
| ≥300 validation trades | 9,391+ |
| validation t ≥ 3 AND profit factor ≥ 1.15 | **0** |
| (filters 3–10 never reached) | — |

IS-vs-OOS correlation of per-trade means: **+0.83** — train results replicate
out-of-sample faithfully; they are just consistently unprofitable. This is a
cost-dominated market, not a noisy one.

## Sizing analysis (moot, but the data answered anyway)

With no positive-edge strategy, Kelly-vs-compounding comparisons have no
subject. The serial-dependence study settles the underlying question: window
outcomes are mildly ANTI-persistent, so streak-compounding (betting more after
wins on the same side) is directionally *wrong* here, independent of sizing math.

## What would make this verdict stop being true

- **Fee cuts or maker-rebate expansion.** At r=0.03 the breakeven gross edge
  roughly halves; several near-survivors (val t ≈ 1.3–1.7, pf ≈ 1.1–1.2)
  would deserve a re-run. Watch `getClobMarketInfo` fee params.
- **Sub-100ms colocated execution** near Polymarket's infrastructure would
  reopen the oracle-lag trade (stable 1.25s Binance→Chainlink lag) — this is
  an institutional MM business, not a home setup, and capacity is small
  ($200 orders already pay 1.5–4.7¢ slippage; $1k pays 4–9¢).
- **New market structures** (the hourly series died in April; new durations or
  tick sizes change the calculus) or a liquidity regime change.
- **Maker-side market making with rebates** is the one family this study
  simplified (conservative trade-through fills, no queue modeling, no two-sided
  inventory engine). On-chain aggregates show makers losing net of rebates in
  the 5m era, so the prior is negative, but a dedicated MM study with queue
  simulation remains the strongest open question.

## Honest limitations

- Book depth was stored as cost-to-fill curves on a 250ms grid (prices exact,
  sizes ≤250ms stale); maker fills used the conservative trade-through rule.
- The 4h family and cross-timeframe (5m↔15m) signals were computed as features
  but not gridded as standalone families; the hourly series ended 2026-04-06.
- ML used 3 feature sets × 2 model classes at 200 trees; a larger model zoo
  is conceivable, but the OOF/VAL gap pattern gives no reason for optimism.
- Chainlink-based fair value exists only from 2026-04-02 (feed availability).

## Recommendation

**Do not deploy capital.** Phase 6 (live deployment) should not proceed — there
is no survivor. If you want to trade these markets anyway, the only defensible
role by the data is passive maker with rebate capture — and the on-chain
aggregates show even that pool losing net in the 5m era. Re-run this pipeline
(everything is reproducible: config + seed + data version logged) if fees drop
materially or you obtain sub-100ms infrastructure.

*The holdout (2026-05-13 → 2026-07-05) remains sealed and unused. If a future
re-run under changed conditions produces survivors, it is still valid for a
one-shot final test.*

---

## Appendix: user-requested extension pass (2026-07-07)

At the user's request, three further hypothesis spaces were tested under the
same gauntlet (thresholds unchanged, multiple-testing count updated):

1. **Cross-timeframe (5m × concurrent 15m market)** — 5m entries gated by the
   concurrent 15m market's implied probability, velocity, and agreement with
   the 5m price, plus an exhaustive mined pass over all four new features
   (~560 configs). Best validation t-stat: **0.06**. Nothing.
2. **Maker-entry family (fee-free entries)** — resting limit entries at
   join/behind/mid−2¢/mid−3¢, gated by fair value, 15m agreement, or Binance
   momentum, filled under the conservative strict trade-through rule (~160
   configs, thousands of validation fills each). Every configuration is
   **negative** (val t −0.7 to −0.9). This is adverse selection measured
   directly: resting orders fill precisely when the market moves against
   them, and the loss exceeds the fee saved — consistent with the on-chain
   finding that makers in aggregate lose net of rebates in the 5m era.
3. **$5 bet sizing** — per-trade t-statistics are scale-free and all fills
   were priced with the $50-bucket book walk, which upper-bounds a $5 order's
   cost. These results therefore ARE the $5-bet results. For context, even the
   single best (non-significant) config's mean edge translates to ≈ **$0.30
   per $5 trade before any infrastructure costs**, indistinguishable from luck.

Updated totals: **~13,100 configurations, best validation t-stat still 1.69,
zero survivors.** The extension pass strengthens the original verdict.

## Appendix 2: pre-open pass (user-specified strategy shapes, 2026-07-07)

The user proposed: enter ~20s BEFORE window open near 50¢, immediately rest a
maker sell at +5¢, $5 stake, direction from the 5m market itself / the
previous window / the 15m market / Binance candles, with and without ML.
This region (negative decision offsets) was genuinely untested. Results
(720 rule configs + 36 ML configs at offsets −30/−10/−3s):

- **Pre-open books are already professional**: 99.6% of windows are quoted
  before open at the same 1¢ median spread. There is no sleepy pre-open gap.
- **"Buy at 20¢ pre-open" is structurally impossible**: before open the BTC
  delta is zero by definition, so the market always sits near 50¢ — the 20¢
  band produced ZERO pre-open trades in 90 days.
- **The exact 50¢→55¢ maker-scalp**: wins ~85% of the time (the +5¢ sell
  fills), but the ~15% of unfilled positions ride to expiry as ~50¢ losers and
  the taker entry fee eats the scalps: with prior-window direction signals,
  val t = **−6.1 to −7.4** over ~2,000 trades each; blind versions val t
  −2.5/−2.8 (profit factor 0.49–0.60). A textbook negative-skew scalp.
- Direction sources: Binance candles (t −1.0), 15m market (thin samples,
  nothing), previous-window follow AND fade (both negative — consistent with
  near-zero serial dependence), blind up (best: t +1.02, i.e., luck-sized).
- **Pre-open ML** (logit+LGBM, walk-forward, isotonic, 3 feature sets):
  every configuration negative in validation (best val t −2.19).

Updated totals: **~13,700 configurations. Zero survivors. Verdict unchanged.**

## Appendix 3: fine-grained close-out (2026-07-07)

Final user-requested sweeps, all under unchanged gauntlet thresholds:

1. **Per-cent entry bands 47¢…53¢** (not lumped) × offsets {−10s, −3s, +5s,
   +20s, +60s} × 7 direction sources (blind both ways, Binance 1m/5m candles,
   15m market sign, prior-window follow AND fade) × maker exits +3¢/+5¢ —
   980 configs, 640 with ≥300 validation trades: **every single one negative**
   (best val t −1.92; profit factors 0.53–0.76 at 85–88% win rates).
2. **Optimistic fill rule** (resting sell fills the moment price merely
   touches the limit — the most generous assumption possible for small
   orders): results are near-identical to the conservative rule and still
   uniformly negative. Fill generosity is not the binding constraint;
   the win/loss asymmetry plus the entry fee is.
3. **Combined pre-open ML** (one model given 5m book + 15m market +
   prior-window live price + Binance candles + volatility + VWAP, with
   confidence-margin abstention as the "when to avoid" dial): all margins
   negative out-of-sample. The high-abstention variant is the study's
   definitive overfitting exhibit: **train t +2.64 / pf 1.80 / 63% wins →
   validation t −2.48 / pf 0.62 / 37% wins.**

Final totals: **~14,800 configurations. Zero survivors. The search is closed;
further passes on this dataset would only manufacture false positives.**

## Appendix 4: stop-loss / early-exit pass (2026-07-07)

User question: does a stop-loss help — if the maker sell hasn't filled after
X seconds, cut the position at market instead of holding to expiry? Simulated
on real second-by-second intra-window price paths (src/stop_sim.py), $5/trade,
entry offsets {−10s, +20s, +60s}, direction from blind / Binance 1m candle /
15m market, maker target +3¢/+5¢, stop times {5s, 10s, 20s, hold}.

**Every stop-loss variant made results WORSE, not better.** Averaged across 24
configurations: hold-to-expiry −$0.38/trade → stop-5s −$0.49 → stop-10s −$0.50
→ stop-20s −$0.48. Best single config (entry +60s, 15m-direction, +5¢): hold
−$0.28/trade (~−$10.53/day) vs stop-10s −$0.49/trade (~−$18.21/day).

Mechanism: a resting +N¢ sell fails to fill precisely *because* price moved
against the position, so the stop-out taker-sell executes BELOW entry AND pays
a second taker fee. Because 5-minute BTC is near-symmetric, the stop cuts as
many would-be recoveries as genuine losers, while charging an extra fee on
every cut. Confirms the general result: in a fee-dominated efficient market,
every added execution (stop, take-profit, re-entry) is another place to pay
the fee — and the fee is the entire edge. No exit rule rescues a negative-edge
entry.

Final totals: **~15,500 configurations across entries, directions, ML/no-ML,
timeframes, fill assumptions, sizings, and now exit/stop-loss rules. Zero
survivors.**
