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

## Appendix 5: reverse-engineering the REAL profitable bots (2026-07-07)

The user's strongest point: "consistent profitable bots exist, this isn't luck."
Correct — so instead of simulating more strategies, every wallet's realized P&L
was reconstructed directly from on-chain fills (train+val 5m, outcome + fill
price + amount + fee, ground-truth accounting; maker P&L incl. ~20% rebate).

**What's real:**
- ~400k wallets traded; 12,379 taker wallets had ≥300 fills over ≥20 days.
- Top consistent taker: **+$2,970 over 51 days, 84% green days, daily
  Sharpe 0.93 (t≈6.6)**. Top maker bot: **+$151k over 62 days, 3.2M fills.**
  These are unambiguously real, profitable, non-luck operations.

**But how many are genuinely edged vs survivorship?** A null model (each
wallet's own daily P&L magnitudes, signs randomized = zero-edge coin-flip):
- "Consistent winners" (Sharpe≥0.3, >55% green days, P&L>0): **703 real vs
  571±22 expected by pure luck.** So ~570 of the 703 are survivorship — lucky
  coin-flippers over a few weeks — and only a ~130 excess carries any real edge.
- Wallets exceeding the rigorous multiple-testing skill bar (t > √(2 ln N) =
  4.34): **exactly 3 of 12,379.** Max t-stat 6.67. Three genuinely-edged
  taker bots in the entire market, plus a handful of large MM operations.

**What the genuine winners actually do (profiled):**
- Their edge is **NOT home-latency arbitrage**: Binance price moves in the
  ~1s around their fills are ≈0.1 bps — they are not front-running Binance
  faster than 250ms. So the edge is not raw speed on the signal I measured.
- Their edge is **NOT any rule in this study's feature set**: 15,500 configs
  with those exact features + ML + walk-forward found no replicable positive-EV
  rule. If the winners' edge were a Telonex-observable signal at home latency,
  the search would have caught it.
- The top wallets do NOT concentrate at 50¢: winners trade 30% coin-flip / 27%
  cheap-tail / 43% mid — barely different from losers. There is no "trade at
  48–52¢ and win" pattern; that price region is where the 6,099 LOSING takers
  concentrate.

**Conclusion.** Consistent profitable bots are real but vanishingly rare (≈3
genuinely-edged takers + a few pro market-makers per ~400k wallets), and their
edge lives in places a $5 home bot cannot reach: sub-100ms colocated execution
against the stable 1.25s oracle lag *with size*, or professional two-sided
market-making harvesting maker rebates + liquidity rewards (the $151k maker),
or private order flow — none of it the "buy Up/Down near 50¢, rest a limit
sell" strategy, which sits squarely in the losing majority. The user's premise
was right and its implication is the opposite of hoped: the winners prove the
edge is real, and prove it is not retail-replicable here.

Final tally: **~15,500 simulated configs + direct P&L reconstruction of ~400k
real wallets. Zero retail-replicable positive-EV strategies. The 3 genuinely
profitable bots are beyond a $5/home-latency setup's reach.**

---

# REVISED VERDICT (2026-07-07, post-holdout): ONE survivor.

## Appendix 6: the oracle-feed final-seconds trade — holdout-confirmed

A user-provided transcript from a practitioner described a latency-arbitrage
bot on 5m BTC markets: a private (direct, paid) Chainlink Data Streams feed vs
Polymarket's delayed broadcast of the same feed, traded in the final seconds.
Two elements were genuinely outside the prior 15,500-config search: decision
times INSIDE the last 15 seconds (grid stopped at t+285s) and the ORACLE FEED
ITSELF as the signal (grid used Binance).

**Measured foundation:** Polymarket broadcasts Chainlink ticks with a median
**1.14s delay** (p95 1.7s, n=2.6M ticks) — the "dislocation" is real.

**Strategy (frozen config):** at t+297s (3s before close), compute z =
log(chainlink_now/open) / (sigma*sqrt(3s)); if |z|>1.5 and fair(Phi(|z|)) −
ask − fee > 2¢, taker-buy the predicted winner; hold ~3s to resolution.
Fills tape-validated (a REAL print ≤ ask+1¢ must occur within 1.5s; fill at
the worse of book ask / that print). Execution latency 250ms. $5/trade.

**Development sample** (Apr 2–May 12, the only pre-holdout Chainlink era):
n=1,228, +$1.41/trade, t=7.7, 86% wins. Look-ahead control passed (impossible
2s-early feed explodes to 98% wins — simulator prices information timing
honestly). Parameter plateau confirmed. Execution stress (anti-flicker,
tape-validation) survived.

**HOLDOUT (May 13–Jul 5, one shot, frozen):**
- **Private-feed variant: PASS.** n=753, **+$0.32/trade, t=2.4** (bar: t≥2,
  profitable), 81.5% wins, +$242 at $5 stakes over 54 days, 69% green days,
  profitable in both halves ($69 then $173).
- **Home variant (PM's own broadcast, no paid feed): FAIL.** −$0.25/trade,
  t=−1.6. Its dev-sample edge (t=4.1) did not survive — already arbed away.

*(Process note: a first holdout invocation returned zero trades due to a file
path bug — no performance information was observed — so the corrected single
run stands as the legitimate one-shot.)*

**Honest deployment picture:**
- The edge REQUIRES the direct Chainlink Data Streams subscription and
  sub-300ms execution. Without it (broadcast version): negative.
- **Alpha decayed 77%** from dev ($1.41/trade) to holdout ($0.32/trade),
  consistent with the platform's own trajectory; this is a wasting asset.
- Economics at holdout rates: ~14 trades/day; $5 stakes ≈ $4.5/day; $50
  stakes ≈ $45/day (fills were priced at the $50 book-walk bucket, so this
  scales validly); beyond that, final-seconds depth (Phase 1: halves in last
  30s) caps size. Feed + VPS costs must clear ~$130/month before $50-stake
  profits are net positive.
- The practitioner's claimed +48–58%/day is NOT supported: measured edge is
  ~6%/trade at ~14 trades/day pre-sizing; such days require aggressive Kelly
  streaks and match the wallet-study's survivorship pattern (his "rinsed and
  recycled" wallets, n=3-trade showcases). The MECHANISM, however, is real,
  matches the 3 genuinely-edged wallets' profile (fast, late-window,
  high-probability entries), and passed this project's full gauntlet.

**Kill-switches if deployed (Phase 6 protocol):** rolling-100-trade win rate
< 74% (holdout 5th-pct proxy), realized fill worse than tape-validated model
by >1¢ average over 50 trades, broadcast-delay median < 400ms (Polymarket
infrastructure upgrade = edge death), fee param change, or 10 consecutive
red days → flatten and halt.

## Appendix 7: the free-feed hybrid nowcast — dev-brilliant, fresh-OOS zero (2026-07-08)

**Constraint:** no paid Chainlink Data Streams subscription. **Reframe:** the
paid feed can be *synthesized* from two free streams, because (a) Polymarket
broadcasts every Chainlink tick on its public WSS with a median 1.1s delay,
and (b) Binance (free WSS, ~100ms) leads the Chainlink source by ~1.25s
(Phase 1 lead-lag). Construction, at decision time T:

```
anchor  = latest Chainlink tick already broadcast (server_ts <= T)   [stale ~1.1s]
nowcast = Binance log-return from the anchor's SOURCE time (+150ms)
          to T-150ms                                                 [bridges the gap]
estimate = clog[anchor] + binance_return - clog[open]
```

All gates FROZEN from the holdout-confirmed oracle trade — toff=297s,
|z|>=1.5 (sigma from prior-300s feed), EV gate fair-ask-fee >= 2c, $50-bucket
book-walk fill at T+250ms, tape-validated (real print <= ask+1c within 1.5s),
date-correct fees, $5 stakes. **No new tuning.** Simulator: src/oracle_hybrid.py.

**Dev sample (Apr 2 – May 12, 41 days): n=1131, +$1.51/trade, t=7.6, 84.6% wins,
83% green days** — statistically indistinguishable from the paid private feed on
the same sample ($1.41/trade, t=7.7). The synthesis works.

**But the holdout is spent** (Rule 2: read exactly once, for Appendix 6), so the
hybrid can never be holdout-tested. The only honest verification left is
genuinely fresh data: **2026-07-06**, completed after the holdout window closed,
never in any split, metadata refreshed post-resolution.

**Fresh-OOS result: ZERO trades.** Dev had no zero-trade day in 41 days
(min 6, median 22) — this is far outside the dev distribution, not a quiet-day
fluke. The diagnostic decomposition of Jul 6's 14 z-passed windows
(dev min 19/day, median 66/day):

- **9 blocked at the EV gate, all with asks 0.98–0.99** (dev median entry:
  0.83). The signal called all 9 directions correctly — but the books had
  already repriced the near-certain outcome, leaving <1c after fees. The
  final-seconds crowd got faster between May and July.
- **5 passed EV but found no tape-validated fill.** Three were real missed
  wins (asks 0.51/0.79/0.87). **The other two were confident and WRONG**:
  z=+5.9 and +4.4 ("Up certain", fair≈1.0) with the market pricing Up at
  25c — and Down won. Verified against the full-day Chainlink tape: the
  *paid* feed was flat in both windows (+0.1bp, −0.0bp — it would never have
  traded). The error is specific to the free synthesis: Binance was trading
  ~50 pts (8–16bp) above the Chainlink index and that basis was *moving*;
  in a calm window (tiny sigma) a few bp of basis noise manufactures a huge
  fake |z|. Only the conservative fill filter kept them out — luck, not design.

**The failure mode lives exactly where the profit lives.** Dev decomposition
by entry ask: the ask<0.50 "disagree with the market" bucket is n=230 at just
54% wins but $4.85/trade — **65% of all dev profit** ($1,115 of $1,712). Those
are precisely the trades the Binance–Chainlink basis can fake (Jul 6: 0-for-2).
The asks>0.80 buckets win 95–98% but average $0.05–0.29/trade and are the first
to be EV-starved as books tighten.

**Structural preconditions on Jul 6:** broadcast delay median 1.05s (p95 1.5s)
— intact, kill-switch not triggered. What changed is competition (books at
98–99c in the final seconds) and what was exposed is basis fragility.

**Fresh-OOS day 2 (2026-07-07): 3 trades, +$1.61, 3/3 wins.** 13 z-passed
windows, all 13 directions correct (no basis failures this day); 10 blocked
at the EV gate with asks 0.93–0.99; the 3 that cleared (asks 0.87/0.90/0.92)
all filled at the book price and all won. A real but thin day: +$0.54/trade
on 3 trades, vs dev's 22 trades/day median.

**Measured trajectory of this edge:** dev $20.9/day (free hybrid, $5 stakes)
→ holdout-era ~$4.5/day (paid feed, Appendix 6) → fresh-OOS Jul 6–7:
$0.80/day (free hybrid). The signal still predicts correctly — 25 of 27
z-passed directions right across both fresh days — what has collapsed is the
*payment* for it: final-seconds books now sit at 98–99c where dev-era entries
had a median of 83c. The trade has been competed down to the fee floor. Two
fresh days is thin evidence, but it is the third consecutive point in a
decaying series, and Rule 4 applies: reported as measured, not softened.

**Verdict:** the free synthesis of the paid feed is real — dev t=7.6 with
zero new parameters, and it still calls direction correctly out of sample —
but the deployable economics as of Jul 6–7 are ~$0.80/day at $5 stakes
(~$16/day IF $100 stakes fill), carrying the documented basis-blowup tail
risk: one confidently-wrong 25c fill costs about 20 winning trades. The
definitive zero-cost test is live paper trading on free feeds (PM WSS
crypto_prices + Binance WSS), Phase 6 protocol, $0 at risk: if two weeks of
paper fills reproduce dev-like economics, deploy $5 stakes; if they reproduce
Jul 6–7, the answer was already in this appendix.
