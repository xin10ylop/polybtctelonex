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

## Appendix 8: NIXULTIMATE — the crowd-reaction hypothesis space, fully measured (2026-07-08)

**Brief:** find strategies that exploit Polymarket's human nature — odds driven
by people's taker flow reacting to BTC — using the order book, game theory,
limit orders, and position structure. Seven new families were built and run
under full discipline (train <= Mar 19 / val Mar 20 - May 12 or fit/validate
splits inside Apr 2 - May 12; strict trade-through maker fills; taker fees
date-correct; thresholds from train quantiles only; Jul 6-7 kept virgin).

**The families and what happened (M = 2,134 configs; deflated bar t >= 3.92):**

| # | Family (archetype) | Configs | Best honest result | Verdict |
|---|---|---|---|---|
| N1 | Whipsaw straddle — resting bids BOTH sides at L, both-fill locks 1-2L fee-free | 42 | every config negative; val_t −5 to −17 | DEAD |
| N4 | Panic-harvest — deep maker bids at mid−5/8/12c catching dumps; bracket variant locks 2k | 27 | all negative; best val_t +1.6 w/ negative train | DEAD |
| N7a | Near-resolution maker at 97-99c, crowd-gated (no Chainlink) | 36 | all val_t <= 0.95 | DEAD |
| N7b | Near-resolution maker, hybrid-nowcast-gated | 24 | SIGN FLIP: fit t −3.8, val t +6.0 — tail-risk clusters, unselectable | DEAD |
| N6 | Cross-timeframe laggard — 15m repriced, 5m lags; maker toward implied fair | 96 | 0 configs positive in both splits at n>=300 | DEAD |
| N5 | Model-quoting maker — hybrid fair − margin as resting quote mid-window | 108 | all negative at n>=300 | DEAD |
| N2/N3 | Flow/depth grid — signed taker flow, whale flow, queue & 5c-depth imbalance, pre-open 45-55c band gated by positioning flow; follow AND fade; hold/maker exits | 1,800 | 0 configs with train_t>0 and val_t>=3; best val_t 1.08 | DEAD |
| N8 | **nix1's frozen signal on the 15m market** (pre-registered transfer, not mined) | 1 | dev n=266, **+$2.11/trade, t=5.8, 88.7% wins**, $15.2/day, 70% green days | see below |

**Mined survivors at the deflated bar: ZERO (0 / 2,133).**

**Why every passive structure died — the game-theoretic core finding of this
project:** Polymarket 5m/15m taker flow is INFORMED. The "panicking humans"
are reacting to Binance, which leads everything; when they cross the spread
into a resting order, they are right on average. Measured five independent
ways: straddle single-fill win rates of 1-22%; panic-bid fill win rates
36-43% (need ~50%+); model-quote fills stale by construction (the crosser
has the newer Binance tick); near-resolution reversal clusters; and the
on-chain ledger itself (5m-era makers net −$1.0M, Phase 1). The mirror
finding: aggressive entries pay the fee wall (r=0.07 at p=0.5 ~ 1.75c/share)
which absorbs the typical mid-window edge (15,500-config gauntlet, Phase 4).
The market's design leaves exactly one profitable niche: faster information
in the final seconds — the nix1 lineage.

**N8, the one real discovery:** nix1's frozen config (unchanged: 3s before
close, |z|>=1.5, EV margin 2c, tape-validated $50-bucket fills, $5 stakes)
transplanted to the 15m market earned +$2.11/trade (t=5.8, 88.7% wins) over
Apr 2 - May 12 — better per-trade than the 5m's $1.51, with a LOWER fee rate
(0.0624). Caveats stated plainly: n=266 misses the pre-registered n>=300
bar, and the profit again concentrates in the low-ask disagreement bucket
(19% of trades, 69% wins, $357 of $562) which carries the documented
Binance-Chainlink basis tail risk.

**Frozen fresh-OOS one-shot (Jul 6-7, never touched by any fit): ZERO
trades on both days.** Diagnosis: 79 and 74 windows z-qualified, but the 15m
final-seconds books now sit at 99.5c+ (only 7 and 3 windows even quoted
below 0.995; all but one EV-blocked). The same competition that compressed
the 5m (Appendix 7) reached the 15m by July. In April both timeframes
combined paid ~$36/day at $5 stakes; in July both gates read shut.

**Verdict — everything on the table:**
1. The crowd-reaction space (order-book imbalance, flow triggers, straddles,
   panic harvesting, cross-timeframe lag, maker quoting): fully measured,
   uniformly negative, mechanism understood. Not "we didn't find it" —
   we measured WHY it isn't there.
2. The only strategy class that ever worked on this data is the final-seconds
   information trade (nix1 on 5m, N8 on 15m). It was genuinely profitable
   on BOTH timeframes through mid-May and is fee-floor-dead on both as of
   Jul 6-7.
3. The edge is REGIME-DEPENDENT, not gone forever: it exists whenever
   final-seconds books leave >2c after fees — a state that reopens when
   competitors lapse, volatility spikes, or new market families launch.
   The zero-cost play: a live paper bot on free feeds watching BOTH
   families' EV gates in real time, trading only when a gate opens.
   That is the deployable NIXULTIMATE: nix1 + N8 + a gate monitor.

## Appendix 9: full-timeline audit + deployment risk engine (2026-07-08)

**Audit note:** at the user's order, the frozen nix1/N8 configs were evaluated
across the ENTIRE Chainlink-feed era (Apr 2 - Jul 7), which includes a second,
clearly-flagged read of the spent HOLDOUT period (May 13 - Jul 5). Parameters
are frozen; nothing was or may be retuned from these results. Purpose:
time the edge's decay and calibrate kill-switches. The audit pipeline
reproduces the dev-era results exactly (5m Apr 2 - May 12: n=1131, $1,711.96
— identical to Appendix 7's run). The pre-April era cannot be simulated by
ANY oracle-feed strategy: the crypto_prices feed begins 2026-04-02.

**Month by month, $5 stakes, frozen gates (src/nix_audit.py):**

| Month | 5m: n / $/trade / t / $/day | 15m: n / $/trade / t / $/day | Combined $/day | 5m median final-3s ask |
|---|---|---|---|---|
| Apr | 844 / $1.16 / 5.0 / $33.71 | 156 / $1.21 / 3.7 / $6.49 | **$40.20** | 0.971 |
| May | 587 / $1.44 / 6.4 / $27.30 | 157 / $2.40 / 4.3 / $12.15 | **$39.45** | 0.980 |
| Jun | 333 / $0.29 / 1.4 / $3.20 | 64 / $0.28 / 1.0 / $0.59 | **$3.79** | 0.989 |
| Jul 1-7 | 78 / $0.30 / 0.8 / $3.35 | 9 / −$0.90 / −1.1 / −$1.16 | **$2.19** | 0.974* |

*small-n; Jul 6-7 alone: zero qualifying trades on both markets.

**Reading:** the edge did not flip off — it decayed ~90% in one step between
May and June and kept sliding. The mechanism is visible in the median ask of
z-qualified windows (0.971 -> 0.989) and the trade count (1431 -> 397 -> 87
per month combined): competitors reprice the final seconds harder every
month. June was still (insignificantly) positive at ~$3.8/day; Jul 6-7 read
zero. Deployment must therefore assume the CURRENT rate is ~$0-4/day at $5
stakes unless live paper data shows otherwise; April-May economics return
only if the competition regresses.

**Risk engine (bot/risk_engine.py + bot/config.json + tests, 16/16 passing):**
pure-logic engine the live bot must route every trade through.
- Pre-trade: frozen EV gate; tape confirmation required; **basis guard** (see
  below); post-only sanity on ask range; max 2 concurrent positions;
  stake = ladder rung capped at bankroll/20 (dev max drawdown was 8.5x stake).
- Kill-switches (auto-halt, operator-only reset, reset demotes to $5):
  broadcast delay median < 0.4s; rolling-100 win rate < 75%; mean fill
  slippage > 1c over 50 trades; any fee-param change; 10 consecutive red
  days. Daily loss > 6 stakes = pause until next UTC day.
- Stake ladder $5 -> $25 -> $100 -> $300 (paper first): promotion needs >= 7
  days AND >= 100 trades on the rung, positive rung P&L, rolling wr >= 78%,
  bankroll >= 20x next stake, and no halt/pause that week; a losing week
  demotes one rung. Measurements advance the ladder, never the calendar.

**Basis guard (improvement, adopted):** skip contrarian entries (ask < 0.50)
when |Binance - Chainlink-anchor| > 5bp at decision time — the exact
signature of the two Jul 6 fake signals (both blocked by the guard in unit
tests; genuine low-ask winners pass). Full-timeline cost-benefit: 5m
+$30.85 BETTER with the guard on (the blocked set was net-losing, 34% wr);
15m costs $9.06 over 3 months. Net +$21.79 AND it removes the documented
catastrophic tail. This is a defensive overlay in the risk engine — the
frozen signal itself is untouched.

**Candidate improvement, NOT adopted (flagged for paper-mode A/B only):**
aligning the Binance nowcast interval by the measured ~1.25s Binance->
Chainlink lead time (instead of symmetric 150ms trims) — a signal change,
so it must earn its way through live paper A/B, not through re-backtesting
spent data.

## Appendix 10: the 1h family — full 9-month study and the spent reserve (2026-07-09)

Telonex holds full order books for the hourly series across its entire
window (the Apr-6 "end" was a slug rename). All 270 days downloaded and
consolidated (src/hourly_bulk.py). Resolution = Binance 1H candle direct
(765/765 verified); fees on-chain verified (0 pre-Mar-6, then 0.0624 /
0.072 / 0.07 from May 7). Pre-registered splits; book-walk fills.

**Final-seconds frozen transfer (src/nix1h_lastsec.py):**
TRAIN (Oct-Mar 19, mostly fee-free): n=142, +$2.01/trade, t=8.56, 99.3% wins
VAL (Mar 20-May 12): n=57, +$0.49/trade, t=1.59, 89.5% wins
**RESERVE ONE-SHOT (May 13-Jul 7, single read, now spent): n=38,
−$0.53/trade, t=−1.28, 78.9% wins, −$0.36/day. FAIL.**
The 1h family followed the same arc as 5m/15m: rich in the fee-free winter,
compressed through spring, negative in the current regime.

**Mid-hour stale-quote sniper (calibrated win-prob, TRAIN-only isotonic,
283,438 decision points): TRAIN t=0.44/0.63, VAL t=0.34/−0.39 — nothing.**
The hourly market is efficient mid-window even without bot competition.
EV-only lottery variant: one $495 December win, statistically nothing.

**Current-regime bottom line across all three markets at $5 stakes:
5m ~$0-3/day, 15m ~$0/day, 1h negative. The final-seconds edge is real,
was worth $40+/day as recently as May, and is at or below the fee floor
everywhere as of July. Deployment decisions must use these numbers, not
the historical averages.**

### Appendix 10 addendum: the crossed-book "pure arbitrage" check (2026-07-09)

The last untested archetype from the user's research (Up+Down < $1). On
mirror-consistent books this requires a crossed BBO (bid > ask). Scan across
5m/15m/1h: crossed states appear in 1-3% of BBO rows but are transient
(median life ~0ms). Filtering to executable events (>=250ms life, >5 shares
both sides, net of fees positive): 5m zero everywhere; 15m/1h show hundreds
per day ONLY on 2026-01-15 — inside the documented pre-Jan-19 collector-gap
era — and 0-2/day in the clean era, none confirmed by trade prints inside
the crossed interval. Verdict: data artifacts, not arbitrage. With this,
all six archetypes of the published bot taxonomy are tested on this data:
two are the real edge we already built (repricing + near-resolution = nix1
lineage), four are measured dead, and the ledger (Appendix 5) shows who
actually gets paid: the 3 fastest wallets out of 12,379.

## Appendix 11: the multicoin campaign — 5 coins x 2 families x 97 days (2026-07-11)

**Question.** Does the frozen nix1 machine, transplanted unchanged to the
neglected coins (ETH/SOL/XRP/BNB/DOGE, 5m + 15m, coins' own Chainlink
broadcast + own Binance tick nowcast, HYPE excluded for lacking tick data),
still earn in the months BTC died — and does the pre-registered deployment
stack pass its bar on the unseen Jun-Jul days?

**Data.** 97 days (2026-04-02..07-05 + fresh 07-06/07), 186,179 windows,
4,102 signal passes at frozen gates (|z|>=1.5, EV>=0.02, T=close-3s).
Streaming pipeline: per-day download -> process -> tiny results -> push ->
delete (results/mc/, src/mc_campaign.py). Fees on-chain-verified per coin
(implied r = 0.0720/0.0700 exactly); resolution rule verified 99.7-100% per
coin; fills at $5 top-of-book only when >=$5 rests at the touch ("C"),
with book-walk ("A") and tape-validated ("B") conventions as brackets.

### Monthly economics ($5 stakes, convention C, all coins+fams)

| month | trades | wr | total | $/day |
|---|---|---|---|---|
| Apr | 1,247 | .880 | +$2,501 | +$86 |
| May | 1,292 | .897 | +$6,819 | +$220 |
| Jun | 625 | .878 | +$147 | +$4.9 |
| Jul 1-7 | 132 | .886 | +$45 | +$6.4 |

The April-May regime was real and enormous relative to stake — and it is
over. The decay that killed BTC in June hit the alts in June too. The May
number is dominated by cheap-disagreement trades (ask<0.50 bucket: +$6,144
of the +$6,819) — the same adverse-selection endgame documented for BTC:
that bucket fell to wr .293 in June (breakeven ~.32) and 6 trades in July.

### The pre-registered deploy bar: **NO DEPLOY**

The frozen stack (basis guard + BTC-calibrated EV gate, frozen 2026-07-09
before any Jun+ coin data was seen) on unseen Jun-1..Jul-7:
**166 trades, -$11.0 total, -$0.31/day, daily t=-0.18.** The bar demanded
clearly positive. It is not. Per pre-registration: NO DEPLOY.

### Post-mortem decomposition (same unseen window, reported for honesty)

| variant | n | wr | $/day | daily t |
|---|---|---|---|---|
| raw frozen signal, no overlay | 757 | .880 | +$5.17 | +2.08 |
| + basis guard only | 723 | .909 | +$4.81 | +2.87 |
| + calibrated EV gate only | 180 | .661 | +$3.08 | +1.32 |
| full stack (registered) | 166 | .663 | -$0.31 | -0.18 |
| trades the cal gate blocked | 575 | .951 | +$2.55 | +2.71 |

The calibration overlay is the component that failed, and it failed by
non-transfer in the conservative-looking direction: the frozen BTC bins cap
predicted wr at 0.90, so the gate blocks every rich-ask trade (alts realize
.933-.948 there — every frozen bin UNDER-predicts alt wr) while keeping the
cheap trades whose regime had just died. A guard fit on one asset's dev era
inverted the selection on another asset's new regime. The basis guard, by
contrast, behaved as designed (blocked 92 windows at wr .326; saved money in
June; 3/88 events were cross-coin simultaneous).

The raw signal + basis guard at $5 ToB was +$4.81/day (t=2.87) on the unseen
window, concentrated in the 15m family (+$3.97/day t=2.44 vs 5m +$1.31/day
t=0.63). **This is a post-hoc observation, not a validated strategy** — the
registered stack failed, and picking the variant that worked after seeing
the window is exactly the retuning Rule 4 forbids. It is hereby
pre-registered as the next one-shot hypothesis: raw frozen signal + basis
guard, NO calibration gate, $5 ToB fills, validate only on days AFTER
2026-07-07, bar = positive with daily t>=2 over >=20 trade-days.

### Tail, concentration, capacity

Full-timeline frozen-stack pnl is 89% top-5-days (one May day +$4,440);
worst day -$25, max drawdown $62 at $5 stakes. Capacity is the binding
constraint: on stack-passing windows the touch holds median $24, p25 $7 —
$5 stakes are near the practical ceiling per market; scaling is horizontal
(more coins/families/wallets) not vertical. Bankroll projections at the
LATEST-regime rate (Jun-Jul): registered stack -$0.31/day -> negative at any
size — NO DEPLOY stands. The unregistered raw+guard variant would project
$100 bankroll ~+$4.8/day gross, but per above it must first survive its
one-shot on fresh days.

### Verdict

1. The signal transfers: direction wr .88 on alts through July, on brand-new
   feeds, with frozen parameters. The look-ahead discipline held end-to-end.
2. The economics decayed on schedule: the alts repeated BTC's Apr->Jul arc
   with ~2 months' lag. Money printed in Apr-May; fee-floor by June.
3. The registered deployment stack FAILS its own bar: NO DEPLOY.
4. One honest thread remains: raw signal + basis guard on 15m alts, still
   t~2.4-2.9 positive on unseen Jun-Jul at tiny size. Pre-registered above;
   decided by fresh post-Jul-7 data or not at all.
