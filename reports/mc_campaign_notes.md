RESCHECK eth-5m 2026-07-06: 287/287 = 100.0%
RESCHECK eth-15m 2026-07-06: 95/95 = 100.0%
RESCHECK sol-5m 2026-07-06: 287/287 = 100.0%
RESCHECK sol-15m 2026-07-06: 95/95 = 100.0%
RESCHECK xrp-5m 2026-07-06: 286/287 = 99.7%
RESCHECK xrp-15m 2026-07-06: 95/95 = 100.0%
RESCHECK bnb-5m 2026-07-06: 286/287 = 99.7%
RESCHECK bnb-15m 2026-07-06: 95/95 = 100.0%
RESCHECK doge-5m 2026-07-06: 287/287 = 100.0%
RESCHECK doge-15m 2026-07-06: 95/95 = 100.0%
RESCHECK hype-5m 2026-07-06: 287/287 = 100.0%
RESCHECK hype-15m 2026-07-06: 95/95 = 100.0%
2026-07-06: windows 2304, pass 29, tape pnl $+6.21
AUDIT eth-5m Jul6: 4 tape trades $+1.92 (benchmark ~4/+$3.97) -> FAIL — INVESTIGATE
AUDIT RESOLVED (2026-07-09): eth-5m Jul6 hand-audit of wts=1783327500 from raw
data: signal EXACT match (z=-1.81, fair=0.9646). PnL gap vs lost-session
benchmark fully explained by fill convention: campaign uses the project-standard
conservative mirror (down fill = 1 - sell_avgpx_50, walks $50 of UP-notional =
~385 shares); hand-walk of the raw book for a $5-$50 DOWN-dollar order fills at
0.6702 vs campaign 0.8746. Campaign pnl = conservative FLOOR (Rule 3);
gate rows carry tob_ask/tob_usd so judgment can bracket realistic $5 fills.
Verdict: pipeline TRUSTED; benchmark superseded by this hand audit.
FEES VERIFIED ON-CHAIN (2026-07-09, manual — in-stream feecheck had a schema
bug, patched): coins share the BTC family fee schedule EXACTLY. eth 2026-05-01
implied r=0.0720 (4,089 fills) vs regime 0.072; eth 2026-05-12 r=0.0700 (4,272
fills) vs 0.07; Jul 6: eth 0.0700 (1,269), sol 0.0700 (326), hype 0.0700 (6).
April fills predate the taker_fee column (Apr 28+ only, same as BTC) — April
rates stand on the changelog schedule, now confirmed at both testable eras.
RESOLUTION VERIFIED: all 6 coins x {5m,15m} reconcile 99.7-100% vs coin
Chainlink feed on Jul 6 + Apr 2 (first-tick-at/after-boundary, close>=open).
2026-07-07: windows 2304, pass 20, tape pnl $-15.86
RESCHECK eth-5m 2026-04-02: 287/287 = 100.0%
RESCHECK eth-15m 2026-04-02: 95/95 = 100.0%
RESCHECK sol-5m 2026-04-02: 287/287 = 100.0%
RESCHECK sol-15m 2026-04-02: 95/95 = 100.0%
RESCHECK xrp-5m 2026-04-02: 287/287 = 100.0%
RESCHECK xrp-15m 2026-04-02: 95/95 = 100.0%
RESCHECK bnb-5m 2026-04-02: 287/287 = 100.0%
RESCHECK bnb-15m 2026-04-02: 95/95 = 100.0%
RESCHECK doge-5m 2026-04-02: 287/287 = 100.0%
RESCHECK doge-15m 2026-04-02: 95/95 = 100.0%
RESCHECK hype-5m 2026-04-02: 287/287 = 100.0%
RESCHECK hype-15m 2026-04-02: 95/95 = 100.0%
2026-04-02: windows 2304, pass 72, tape pnl $-20.61
2026-04-03: windows 2304, pass 88, tape pnl $-62.26
SPEEDUP (2026-07-09 11:2x): consolidation was the bottleneck (~15-18 min/day
-> ~26h campaign under rollback risk). consolidate_books gained final_only=N:
campaign now walks curves only over the last 30s before close (+30s after) —
the machine reads books solely in the final 3s. ~30-44x less walk work.
Semantic note: books resting unchanged for >30s before close now read
"nobook" instead of filling against the stale-but-live row; bias is AGAINST
edge (conservative) and measurable via gate=nobook counts (Jul6/Jul7/Apr2
were processed under FULL consolidation for comparison).
2026-04-04: windows 2304, pass 124, tape pnl $-52.23
2026-04-05: windows 2304, pass 93, tape pnl $+72.10
2026-04-06: windows 2304, pass 35, tape pnl $+16.41
2026-04-07: windows 2304, pass 47, tape pnl $-7.93
2026-04-08: windows 2304, pass 74, tape pnl $+0.62
2026-04-09: windows 2304, pass 68, tape pnl $-11.12
2026-04-10: windows 2304, pass 95, tape pnl $+15.19
2026-04-11: windows 2304, pass 107, tape pnl $-21.58
2026-04-12: windows 2304, pass 99, tape pnl $-60.30
FROZEN STACK PRE-REGISTRATION (2026-07-09 ~11:50 UTC, days Apr2-11 + Jul6-7
seen; Apr12-Jul5 UNSEEN): deployment stack = frozen machine + basis guard
(ask<0.50 & |basis|>5bp, from bot/config.json, BTC-era) + CALIBRATED EV gate
(bot/calibration.json: realized wr vs |z| fitted on BTC dev trades n=1397,
replaces Phi(z); same 2c margin). Root cause documented: Phi(z) says 0.99-1.00
where realized wr is 0.62-0.83 (all coins, 736 trades) — signal direction is
fine, confidence was inflated; BTC masked it with 83c books, coin books at
90-95c expose it. Peeked-days effect: raw 736tr/-$81.05 -> stack 190tr/-$18.09
(tape fills, conservative mirror convention). DEPLOY BAR (Rule 4): the stack
must be significantly positive on the UNSEEN Apr12-Jul5 days (both fill
conventions reported; tob-$5 variant bracketed) or the verdict is NO DEPLOY.
No further overlay variants will be evaluated pre-judgment.
2026-04-13: windows 2304, pass 63, tape pnl $+58.04
2026-04-14: windows 2304, pass 54, tape pnl $-10.21
2026-04-15: windows 2292, pass 50, tape pnl $+9.25
2026-04-16: windows 2288, pass 58, tape pnl $-1.39
FEED FIDELITY UPGRADE (2026-07-09 ~12:1x): A/B on BTC dev (41 days, frozen
machine): aggTrades nowcast +$1.51/tr t=7.6 wr84.6% vs 1s-klines nowcast
+$1.04/tr t=4.9 wr80.6% — candles cost ~1/3 of the edge. The live bot reads
tick WSS, so the sim must too (fidelity fix, NOT a parameter change; frozen
stack + deploy bar unchanged). Campaign restarted with tick nowcast for
eth/sol/xrp/bnb/doge (HYPE unchanged, anchor-only). Klines-variant run of the
first 16 days preserved at results/mc_klines/ for the record. aggTrades
parquets deleted per-day after use (disk).
RESCHECK eth-5m 2026-07-06: 287/287 = 100.0%
RESCHECK eth-15m 2026-07-06: 95/95 = 100.0%
RESCHECK sol-5m 2026-07-06: 287/287 = 100.0%
RESCHECK sol-15m 2026-07-06: 95/95 = 100.0%
RESCHECK xrp-5m 2026-07-06: 286/287 = 99.7%
RESCHECK xrp-15m 2026-07-06: 95/95 = 100.0%
RESCHECK bnb-5m 2026-07-06: 286/287 = 99.7%
RESCHECK bnb-15m 2026-07-06: 95/95 = 100.0%
RESCHECK doge-5m 2026-07-06: 287/287 = 100.0%
RESCHECK doge-15m 2026-07-06: 95/95 = 100.0%
RESCHECK hype-5m 2026-07-06: 287/287 = 100.0%
RESCHECK hype-15m 2026-07-06: 95/95 = 100.0%
FEECHECK eth-5m 2026-07-06: implied r=0.0700 regime=0.07 OK
FEECHECK sol-5m 2026-07-06: implied r=0.0700 regime=0.07 OK
2026-07-06: windows 2304, pass 29, tape pnl $-3.19
AUDIT eth-5m Jul6: 3 tape trades $-4.45 (benchmark ~4/+$3.97) -> FAIL — INVESTIGATE
TICK-RUN AUDIT RESOLVED (2026-07-09 12:2x): Jul6 tick vs klines window-level:
corr(z)=1.000, sign agree 99.8% over 1117 windows -> feed parsing verified.
Day-level delta (-$3.19 vs +$6.21) fully attributed: marginal |z|~1.5-2
boundary flips (tick brain fresher — correctly skipped a retraced klines
'winner'), BNB nofeed on real tick gaps (frozen construction requires b2>b1),
and ONE new -$5.30 eth loser at wts=1783316400 = the SAME 05:40 UTC Jul 6
cross-venue basis event as BTC's documented blowup (ask ~0.6 > guard's 0.50
floor, so not blocked). No bug; klines-tuned audit band superseded. Judgment
uses the full tick-run sample.
2026-07-07: windows 2304, pass 23, tape pnl $-11.68
RESCHECK eth-5m 2026-04-02: 287/287 = 100.0%
RESCHECK eth-15m 2026-04-02: 95/95 = 100.0%
RESCHECK sol-5m 2026-04-02: 287/287 = 100.0%
RESCHECK sol-15m 2026-04-02: 95/95 = 100.0%
RESCHECK xrp-5m 2026-04-02: 287/287 = 100.0%
RESCHECK xrp-15m 2026-04-02: 95/95 = 100.0%
RESCHECK bnb-5m 2026-04-02: 287/287 = 100.0%
RESCHECK bnb-15m 2026-04-02: 95/95 = 100.0%
RESCHECK doge-5m 2026-04-02: 287/287 = 100.0%
RESCHECK doge-15m 2026-04-02: 95/95 = 100.0%
RESCHECK hype-5m 2026-04-02: 287/287 = 100.0%
RESCHECK hype-15m 2026-04-02: 95/95 = 100.0%
2026-04-02: windows 2304, pass 63, tape pnl $-7.99
2026-04-03: windows 2304, pass 82, tape pnl $-38.94
2026-04-04: windows 2304, pass 107, tape pnl $-13.20
2026-04-05: windows 2304, pass 73, tape pnl $+0.69
2026-04-06: windows 2304, pass 40, tape pnl $-16.36
COIN SET FINALIZED (2026-07-09, user directive): exclude any coin without a
150ms tick feed. HYPE dropped entirely (not on Binance spot -> anchor-only,
measured negative like BTC broadcast-only). Tick coins with an aggTrades gap
on a given day now SKIP that coin-day (no 1s-klines fallback) rather than
trade on stale data. HYPE rows stripped from the 7 already-computed tick days
(16128->13440 rows). Deployable coin set = ETH, SOL, XRP, BNB, DOGE.
2026-04-07: windows 1920, pass 29, tape pnl $-5.66
2026-04-08: windows 1920, pass 47, tape pnl $+4.58
2026-04-09: windows 1920, pass 55, tape pnl $+11.11
2026-04-10: windows 1920, pass 76, tape pnl $+7.22
2026-04-11: windows 1920, pass 83, tape pnl $+34.03
2026-04-12: windows 1920, pass 67, tape pnl $-19.45
2026-04-13: windows 1920, pass 59, tape pnl $+3.33
2026-04-14: windows 1920, pass 41, tape pnl $+42.91
2026-04-15: windows 1910, pass 51, tape pnl $-0.08
2026-04-16: windows 1907, pass 43, tape pnl $-16.74
2026-04-17: windows 1920, pass 43, tape pnl $-12.53
2026-04-18: windows 1920, pass 46, tape pnl $-2.45
2026-04-19: windows 1920, pass 23, tape pnl $-27.93
2026-04-20: windows 1920, pass 38, tape pnl $-7.23
2026-04-21: windows 1920, pass 49, tape pnl $+134.26
2026-04-22: windows 1920, pass 54, tape pnl $+9.57
2026-04-23: windows 1920, pass 72, tape pnl $-9.96
2026-04-24: windows 1920, pass 53, tape pnl $-5.76
2026-04-25: windows 1920, pass 125, tape pnl $-7.80
2026-04-26: windows 1920, pass 45, tape pnl $+6.22
2026-04-27: windows 1920, pass 45, tape pnl $+13.58
2026-04-28: windows 1920, pass 38, tape pnl $+4.41
2026-04-29: windows 1920, pass 76, tape pnl $+229.90
2026-04-30: windows 1920, pass 147, tape pnl $+598.11
2026-05-01: windows 1920, pass 273, tape pnl $+4583.19
2026-05-02: windows 1920, pass 216, tape pnl $+1211.97
2026-05-03: windows 1920, pass 66, tape pnl $+936.35
2026-05-04: windows 1920, pass 36, tape pnl $+138.40
2026-05-05: windows 1920, pass 65, tape pnl $-19.30
2026-05-06: windows 1920, pass 26, tape pnl $+9.17
2026-05-07: windows 1920, pass 27, tape pnl $+2.45
2026-05-08: windows 1920, pass 49, tape pnl $+0.64
2026-05-09: windows 1920, pass 61, tape pnl $-11.13
2026-05-10: windows 1920, pass 49, tape pnl $-44.17
2026-05-11: windows 1920, pass 8, tape pnl $+3.50
2026-05-12: windows 1920, pass 14, tape pnl $-1.33
2026-05-13: windows 1920, pass 27, tape pnl $+2.85
2026-05-14: windows 1920, pass 18, tape pnl $-27.07
2026-05-15: windows 1920, pass 36, tape pnl $-8.01
2026-05-16: windows 1920, pass 47, tape pnl $+16.88
2026-05-17: windows 1920, pass 57, tape pnl $-34.37
2026-05-18: windows 1920, pass 16, tape pnl $+22.50
2026-05-19: windows 1920, pass 23, tape pnl $-9.87
2026-05-20: windows 1920, pass 23, tape pnl $-2.50
2026-05-21: windows 1920, pass 26, tape pnl $-21.72
2026-05-22: windows 1920, pass 37, tape pnl $-9.46
2026-05-23: windows 1920, pass 35, tape pnl $-13.31
2026-05-24: windows 1920, pass 32, tape pnl $-17.73
2026-05-25: windows 1920, pass 22, tape pnl $-24.72
2026-05-26: windows 1910, pass 18, tape pnl $-5.57
2026-05-27: windows 1920, pass 23, tape pnl $-23.69
2026-05-28: windows 1920, pass 19, tape pnl $+7.55
2026-05-29: windows 1920, pass 36, tape pnl $-9.88
2026-05-30: windows 1920, pass 45, tape pnl $-25.00
2026-05-31: windows 1920, pass 34, tape pnl $+21.19
2026-06-01: windows 1920, pass 15, tape pnl $+3.18
2026-06-02: windows 1920, pass 26, tape pnl $-15.02
2026-06-03: windows 1920, pass 27, tape pnl $-0.30
2026-06-04: windows 1920, pass 13, tape pnl $+5.54
2026-06-05: windows 1920, pass 6, tape pnl $+1.22
2026-06-06: windows 1920, pass 26, tape pnl $+4.21
2026-06-07: windows 1920, pass 16, tape pnl $+1.29
2026-06-08: windows 1920, pass 16, tape pnl $+6.92
2026-06-09: windows 1920, pass 27, tape pnl $-9.17
2026-06-10: windows 1920, pass 9, tape pnl $-4.26
2026-06-11: windows 1920, pass 5, tape pnl $+2.09
2026-06-12: windows 1920, pass 30, tape pnl $-23.63
"SOMETHING OFF" INVESTIGATION RESOLVED (2026-07-10, user-prompted). Three findings:
(1) Earlier "June books tightened" claim WRONG — winner-ask median flat 0.98 all
months. (2) The floor-fill June collapse (~1 trade/day) is a FILL-CONVENTION
ARTIFACT: noask rose (thin books make $50-mirror walk unusable) while
top-of-book stayed quoted; under $5 tob fills June fires 27 trades/day at 73%
wr — same wr as Apr/May. Feeds verified clean (1/s ticks, sigma estimator 1.0x
correct scale, delay ~1.1s normal; high |z| is the decided-window nature of the
trade, not a bug). (3) THE REAL DISEASE: the cheap-disagreement bucket (ask<50c)
— 23-29% of trades and the entire profit engine in Apr/May (wr 49-68% vs 40%
breakeven) — collapsed to 3% of trades in June and turned TOXIC (18% wr).
Rich bucket now 61-69% of trades at 79%/65% wr vs 85% breakeven = losing.
Same aggregate accuracy, no payment: adverse selection endgame — the only
cheap asks left are the ones the model is wrong about. Deployment-realistic $5
(tob, optimistic no-tape bracket): Apr +$67/day, May +$200/day, Jun +$2/day,
Jul -$17/day. BTC-fit calibration does NOT transfer (top-bin 0.90 vs realized
49-85% bucket-dependent). Deploy bar (clearly positive on recent months) is
FAILING unless Jun12-Jul5 reverses. Judgment must use bucket-level lens.
2026-06-13: windows 1920, pass 69, tape pnl $-67.26
2026-06-14: windows 1920, pass 51, tape pnl $-20.96
FEECHECK eth-5m 2026-06-15: implied r=0.0700 regime=0.07 OK
FEECHECK sol-5m 2026-06-15: implied r=0.0700 regime=0.07 OK
2026-06-15: windows 1920, pass 18, tape pnl $+2.34
2026-06-16: windows 1920, pass 20, tape pnl $+3.38
2026-06-17: windows 1897, pass 29, tape pnl $+29.65
2026-06-18: windows 1920, pass 14, tape pnl $-15.28
2026-06-19: windows 1920, pass 25, tape pnl $-9.67
2026-06-20: windows 1915, pass 25, tape pnl $-18.02
2026-06-21: windows 1920, pass 36, tape pnl $+24.48
2026-06-22: windows 1920, pass 27, tape pnl $+9.53
USER SCALP REDO (2026-07-10, src/nix_scalp.py, 611,712 trade-rows, 92 BTC days):
EVERY config negative. User's exact shape (taker<=51c @ open-10s, TP+4c, stop
open+10s): TP hits only 40%, stops 60% avg -$1.68 -> NET -$0.80/trade, t=-54.
HOLD variant (no stop): TP hits 88% (+$0.48-0.78) — THIS matches the user's
"wins 7+/10" experience — but the 12% full-stake wipeouts cost -$10 each ->
NET -$0.40 to -$0.62/trade, t=-11 to -15. Martingale touch math: entry 0.51,
TP 0.55 -> touch prob = 0.51/0.55 = 92.7% at ZERO edge; measured 88%. The
high win rate is structural, not alpha; expectancy = -(costs). No direction
signal helps (blind/momentum/fade 60s+300s all equally negative; ML found
nothing pre-open in Phase 3). The 10s stop makes it WORSE (-$0.80 vs -$0.51):
60% of trades pay spread+2 fees for a coin-flip exit.
2026-06-23: windows 1920, pass 33, tape pnl $-3.94
2026-06-24: windows 1920, pass 49, tape pnl $+12.33
2026-06-25: windows 1920, pass 35, tape pnl $+3.56
2026-06-26: windows 1920, pass 14, tape pnl $-7.75
2026-06-27: windows 1920, pass 35, tape pnl $-17.09
2026-06-28: windows 1920, pass 27, tape pnl $-11.43
2026-06-29: windows 1920, pass 12, tape pnl $-23.22
2026-06-30: windows 1920, pass 34, tape pnl $-5.92
2026-07-01: windows 1920, pass 10, tape pnl $-2.42
MAXIMAL DIRECTION PASS (2026-07-11, user-ordered "combine everything, think"):
src/nix_scalp_ml.py. (a) First run showed 65% OOS direction accuracy — CAUGHT
as selection leakage by the mandated verification (gt sample = TP-failed sides
=> features predicted which side was sampled, not the future; single-feature
check exposed it: all features 44-52% alone). Rule 1 works. (b) CLEAN test,
official labels, ALL 20,902 windows, walk-forward LGBM over book imbalance +
depth + taker flow (3 horizons) + whale flow + 15m market + prior windows +
Binance mom/vol + clock: OOS AUC 0.514; most-confident 7,098 windows = 52.4%
accuracy vs ~53% fee breakeven. Top features ARE order-book flow (flow_imb_10s,
q_imb, depth_imb) — the signal exists but is priced under the fee wall,
consistent with all six prior measurements (52.1% anti-streak, ML 46k windows).
(c) TP-hit path model (new target): AUC 0.558; best 5% slice 52.6% TP vs 77.8%
breakeven, still -$0.55/trade. (d) Strata (hour/vol/prior/15m): -$0.75 to
-$0.89/trade everywhere. Compounding at negative mean = faster ruin (math, not
opinion). The pre-open scalp is unfixable by direction selection at
retail-visible information.
2026-07-02: windows 1920, pass 32, tape pnl $-19.77
2026-07-03: windows 1920, pass 24, tape pnl $-5.85
2026-07-04: windows 1920, pass 32, tape pnl $+29.14

## Zero-fee counterfactual of the user's scalp (2026-07-11)

User challenged the fee model ("are you sure you are not over-pricing fees?").
Two answers, both conclusive:

1. **Fee audit vs reality** (previous entry): 2,426,954 real on-chain fills at
   45-55c, 100% fee-bearing, implied r median 0.0700 = formula exactly
   (p90 0.0763 — model slightly under-charges if anything).

2. **Zero-fee counterfactual** (results/nix_scalp_5m_zerofee.parquet, same
   611,712 trade-rows, rate forced to 0): **every one of the 18 configs is
   still negative.** Best zero-fee shape = user's exact config (taker 51c,
   t0=-10s, 10s stop): -$0.270/trade vs -$0.810 with fees. Decomposition of
   the $0.81 loss: ~$0.54 fees (entry + stop taker legs), ~$0.27 spread +
   adverse selection. Maker-entry + hold rows are identical in both tables
   (maker legs already fee-free) — internal consistency check passes.
   Momentum-directing by m300 sign changes nothing (-$0.275 vs -$0.270 blind).

Verdict: fees are NOT the reason the scalp loses. Even on a zero-fee venue
the shape loses ~27c per $10 trade to adverse selection: the +4c TP fills
only 40% of the time vs the 77.8% breakeven the 10s-stop shape needs, and
resting-maker entries are filled precisely when the market moves against you
(maker50 zero-fee -$0.49 < taker51 zero-fee -$0.27).

## User's scalp on the 15m family, full 9-month history (2026-07-11)

results/nix_scalp_15m.parquet — 366,374 trade-rows, 2025-10-11 -> 2026-07-07
(15m daily coverage gap: full-window books thin after mid-May; Jul 6-7 fresh
days included). Same 18-config grid as 5m.

Headline: **zero positive config-months out of all config x month cells
(9 months x 18 configs), and every config negative in BOTH fee eras.**

- PRE-FEE era (Oct 4 - Jan 4, Polymarket charged NOTHING — this is a real
  zero-fee market, not a counterfactual): best config taker51/t-5/stop10
  = -$0.234/trade. User's exact shape -$0.263. TP rate 24% vs 77.8% breakeven.
- FEE era (Jan 5+): user's exact shape -$0.75 to -$0.83/trade, TP rate ~22%.
- 15m TP rates are LOWER than 5m (24% vs 40%): the +-4c TP from a ~50c open
  needs the same absolute odds move, but 15m books near open are stickier.

Combined with the 5m zero-fee counterfactual and the on-chain fee audit,
the evidence is now closed on the user's fee question from three independent
directions: (1) real fills price fees exactly as modeled; (2) removing fees
in simulation leaves every config negative; (3) a REAL fee-free era existed
on 15m and the shape lost there too. The scalp's loss is structural
(adverse selection / martingale touch identity), not a fee artifact.
2026-07-05: windows 1920, pass 28, tape pnl $+4.23
CAMPAIGN DONE

## Scalp pass 2 — the user's reframed targets (2026-07-11, src/nix_scalp2.py)

New features: Binance microstructure (taker-flow imb 1/3/10/30s, 1-10s rets,
intensity, 1s-grid vol), Chainlink anchor basis/staleness/tick-rate, BBO
mid/spread/change-rate; side-relative signing. 51,622 side-rows, 90 days,
walk-forward LGBM, folds 2-6 OOS.

Q1 touch(+4c) by x: REAL predictability — AUC 0.60-0.63 all horizons.
Top-10% slice lifts touch 40.6%->58.1% (x=10s) yet money still negative
(-$0.44/tr vs -$0.81 unfiltered: model halves the loss, ceiling far below
the 77.8% breakeven).
Q2 direction: AUC 0.524. Confident tail on ALL windows 51-54% wr (LGBM
thread nondeterminism gives a 51.4-54.1% band across reruns) — near/above
the 52.76% breakeven. BUT on FEASIBLE rows (ask<=51c — the only ones the
scalp can buy) wr collapses to 49.5% FLAT at every confidence level;
pure-hold -$0.34/tr (t=-3). MECHANISM: the <=51c entry cap is an adverse
filter. When model AND crowd agree, ask>51c -> no entry. What remains
cheap is exactly where the crowd disagrees with the model, and the crowd
wins. The entry rule guarantees trading against better-informed flow.
(Fading the model on feasible rows: 50.5% vs 50.8% breakeven — also dead.)
Q3 drift_5s: user's 55-60% accuracy claim CONFIRMED — 59.7% on 30,653
confident OOS rows (AUC 0.585) predicting the token's first 5s repricing.
Not monetizable: expected |5s move| ~0.4c/share vs round-trip cost ~4.5c
(1c spread + 2x taker fee) — 10x+ short. Accuracy was never the obstacle;
cost structure is.

Verdict: the market grants accuracy precisely where it doesn't pay
(drift, touch-lift) and denies entry precisely where it would (direction
skill exists mainly on windows priced >51c). No positive slice.

## Scalp pass 3 — gated geometry grid (2026-07-11, src/nix_scalp3.py)

User's correction: he bail-out market-sold 10s after open, so misses cost
spread+drift, not -$10. Grid: {taker<=51, maker50 fee-free} x TP {2,3,4,6}c
x bail {5,10,20,30}s, each cell walk-forward LGBM-gated (pass-2 features).
Pre-declared bar: positive AND t>=3.5 (64 looks). Result: **0/64 survivors;
every ungated cell and every gated slice negative.** Best: m50+2c/stop20
top-decile -$0.108/tr (t=-4.5) at 81% touch.

Why the bail-out doesn't save it (measured): by the time the TP has failed,
the token has already fallen — maker50/TP4/stop10 misses exit at bid mean
0.436 / median 0.450 (entry 0.50); 27% of misses the bid is <=0.40 before
the bail-out fires. Realized miss cost ~$1.45/tr vs the ~$0.75 naive
envelope -> true breakeven touch ~64%, gated model reaches 53%.

Gates DO work as prediction: touch rates lift 49->73%, 66->83% across
cells, and pnl improves monotonically with gating (-0.70 -> -0.11) but
plateaus at a ~-$0.10/tr wall = the adverse-selection + spread tax that no
selectivity removes. Gate content (best cell, descriptive): model buys
BOUNCES — Binance down over 5m (b_ret_300s median -6bp), 15m market priced
against the side (xtf15_mid 0.27), prior window against (0.21), high vol.
It finds real 2c bounces at 81% frequency; the crashes in the other 19%
cost more than the bounces pay. Four passes now converge on the same
mechanism from four directions.

## Scalp pass 4 — boundary-print staleness trade (2026-07-11, src/nix_scalp4.py)

Mechanism-first (not mined): window open = first Chainlink print >= boundary;
print VALUES lag Binance ~1s (holdout-proven nix1 edge) -> a Binance move in
the final second tilts the open reference in the mover's favor. Signal =
pure 1s Binance return before T0 (basis-proof after smoke test caught the
cross-feed level gap being basis-contaminated, +2.8bp median venue basis;
same Jul-6 failure mode, now excluded by construction), z = g/sigma300.
Feed-era dev Apr2-May12, 32 pre-declared trade cells, bar t>=3.5.

MEASUREMENT — the mechanism is REAL:
- signal-side wr by entry timing (|z|>=0.05, uncapped): -5s 46.3%,
  -2s 49.6%, -1s 51.5%, -0.5s 53.8% (n=1089). Monotone gradient with a
  SIGN FLIP: pre-boundary spikes mean-revert at 5s but carry the open at
  0.5s. Coherent microstructure story, first which-side signal ever to
  clear the 52.8% breakeven at feasible entries.
- book does NOT price it: signal-side ask 0.505-0.508 in gated windows.

TRADE RESULTS:
- All 32 TP-shape cells NEGATIVE (user's +4c sell-limit forfeits the tail
  that pays for the ~46% losers; the tilt's value is 0.49->1.00, not
  0.49->0.53). 0/32 survivors.
- PURE HOLD at -0.5s: positive point estimate at EVERY gate (+$0.46 to
  +$0.78/tr, n=865..94) but t=0.75-1.32 — statistically unresolved; needs
  ~5k+ trades. Fresh Jul6-7: n=48, wr 47.9%, negative — no confirmation.

STATUS: registered as a candidate, NOT a result. Resolution paths: (a) let
fresh BTC days accumulate (holdout region unreadable, Rule 2); (b) port to
multicoin feeds (5x surface, books need re-download — natural next
campaign). Do NOT re-cut the dev era further.

## Scalp pass 5 — RENEW the boundary direction signal (2026-07-11, src/nix_scalp5.py)

Freed from the 51c/sell-limit rule (user instruction). Frozen pass-4 signal,
extended to 15m + pooled (44+44 days), 3 monetizations priced from raw rows,
cap sweep. Dev = Apr2-May12; fresh = Jul 6-8 (07-08 newly downloaded), sealed
May13-Jul5 untouched. Bar: mean>0 AND t>=3.0.

KEY FINDINGS:
1. The renewal thesis is VINDICATED as a diagnosis. Same signal, same windows
   (dev pooled |z|>=.05, t0=-0.5): hold_pure +$0.453/tr vs tp4_hold -$0.533 vs
   tp4_bail -$0.531. Dropping the +4c sell-limit and holding to resolution is
   a ~$1.00/trade swing from negative to positive — the +4c cap was throwing
   away the directional edge's payoff (win pays +100% at 50c, cap took +8%).
2. Every hold_pure cell at t0=-0.5 is POSITIVE: +$0.45 (|z|>=.05) rising to
   +$1.18 (|z|>=.3, cap0.7, wr 59.5%). The book does NOT price the tilt (ask
   ~0.505 even at |z|>=.30 where wr=59.5%) — that blindness is the edge.
3. MECHANISM CONFIRMED by sign-flip at the physically-motivated horizon:
   t0=-1.0 hold_pure = -$0.30/tr (t=-1.10); t0=-0.5 = +$0.20 to +$0.45. A
   noise variable would not flip sign exactly at the ~0.5s oracle-lag horizon.
4. BUT NO SURVIVOR at the pre-declared bar. Best pooled t=1.43 (|z|>=.05,
   n=1122); best any-cell t=1.68 (|z|>=.3 cap0.7, n=137). Point estimates
   strongly positive everywhere, variance too high to clear t>=3 (sd ~$10/tr).
5. Fresh OOS Jul 6-8 (untouched): hold_pure +$0.67-0.84/tr, total +$114-161 —
   BUT 2/3 days: 07-06 +$11, 07-07 -$24, 07-08 +$49. Consistent in sign, NOT
   clean replication; the sell-limit stays NEGATIVE on fresh too (-$0.15/tr).

VERDICT: the strongest lead in the project — positive on every dev cut,
mechanism-coherent (t0 sign-flip, book blindness), sell-limit sabotage proven
— but STATISTICALLY UNRESOLVED (t~1.4). Not a validated winner (Rule 4 holds).
Path to significance: dev is exhausted (oracle feed starts Apr2; May13-Jul5
sealed; holdout spent), so only forward paper days or a win-rate-lifting model
can resolve it. This is a live +EV signal to paper-trade, not yet a proven one.

## Scalp pass 6 — the decisive test on 3x data (2026-07-11, src/nix_scalp6.py)

Boundary direction signal on BOTH families, crypto_prices gate dropped
(signal is pure-Binance): 5m Feb12-May12 (90 days, 25.8k windows, PRIMARY,
independent) + 15m Oct11-May12 (214 days, 18.4k) + pooled. Plus Option B:
walk-forward LGBM (expanding month folds) on book/flow features to lift wr.
Holdout-safe (loader excludes it; sealed May13-Jul5 empty). Bar t>=3.0.

VERDICT: **0 survivors. The pass-5 edge does not replicate on 3x data.**
- 5m primary monthly wr: Feb 50.1%, Mar 53.2%, Apr 53.4%, May 55.6% — pass 5's
  +$0.45/tr came from the Apr-May window (the two best months). Adding Feb and
  the full 15m history washes it to ZERO: |z|>=.05 cap0.53 = +$0.09/tr t=0.47
  (5m), +$0.08 t=0.46 (pooled). Not distinguishable from zero. Higher |z|
  gates go NEGATIVE (pooled |z|>=.15 -$0.49 t=-2.6). This is the signature of
  regime luck dissolving under more data — Rule 4 working as designed.
- 15m monthly wr: 5 of 8 months BELOW breakeven (Oct/Nov 50.0, Dec 47.4,
  Feb 51.3, Mar 51.4, Apr 48.1; only Jan 55.4, May 57.4 above). No trend,
  no consistent edge across the 8-month history.
- Option B (the model): OOS AUC 5m 0.528, 15m 0.513, pooled 0.517 — essentially
  NO SKILL. Every model-gated slice NEGATIVE (t=-4 to -7). Book/flow features
  do not predict the resolution direction beyond noise.
- Fresh Jul6-8 positive but tiny (5m n=76 +$0.30; 15m n=20 +$0.67) — within
  noise, and "works only recently" is a post-hoc retune Rule 4 forbids.

CONCLUSION: after 6 passes (touch-by-x, direction ML, drift, gated geometry,
boundary staleness, and now boundary at 3x scale + model), the pre-open scalp
has NO edge that survives honest out-of-sample testing at scale. Pass 5's
promising +$0.45/tr was an Apr-May small-sample mirage. The scalp is closed.

## Pass 6 deep diagnostic — where the win rate fails/holds (2026-07-11, nix_scalp6_diag.py)

WHAT DROPS IT: win rate is NON-MONOTONIC in |z|. Peaks ~53.9% at |z| .05-.10,
then CRASHES to 44.7% at |z|>=.40 — and those are calm-market spikes (low sig
~6.5, biggest 5s move). Mechanism: a sharp move in a quiet market REVERTS, so
the boundary signal inverts there. Real, interpretable — but a fade of a tiny
bin (n=360), only visible in validation not train, so a hypothesis not a rule.
DEAD conditioning vars: 5s-momentum agreement (50.0 vs 49.8), book-imbalance
agreement (50.2 vs 49.6) — no information.

ENFORCEABILITY (5m |z|>=.05, clean forward test Feb-Mar -> Apr-May):
  TRAIN Feb-Mar: wr 51.9% (CI 49.8-54.1) — AT breakeven (51.8%), no edge to lock
  VALID Apr-May: wr 54.0% (CI 51.1-56.9) — CI still includes breakeven
Month trend Feb 50.1 -> Mar 53.2 -> Apr 53.5 -> May 55.6 -> Jul 53.9: an upward
drift, consistent with an emerging edge OR recent-regime luck — indistinguishable
in-sample. The training period sits at breakeven, so there is NOTHING to enforce;
the recent lift cannot be separated from regime. No enforceable parameter found.

FINAL: the boundary win rate is fundamentally ~50-54%, hovering at breakeven,
with CIs that include it even in the best period. No conditioning variable lifts
it to a confident, enforceable edge. The only clean way to test the "emerging
recent edge" hypothesis is forward paper trading — not more in-sample slicing.

## THE 'CHEAP + SIGNAL' EDGE — the hidden structure (2026-07-11, nix_cheapsig.py)

REFRAME: EV is win rate vs ENTRY PRICE, not win rate alone. Win rate by
signal-side ask shows the book is efficient-minus-fees at every price EXCEPT
one interaction: cheap side (ask<0.50) AND boundary signal agrees (|z|>=0.05)
-> 5m 51.5% wr at 0.468 entry = +$0.607/tr (+6.1%). Same cheap WITHOUT signal
= 44.5% (t=-3.1, toxic). The signal DISCRIMINATES mispriced-cheap from
toxic-cheap; the EV comes from PRICE LEVERAGE, not direction skill.
5m: 987 trades/90d (11/day), total +$599, $6.66/day @ $10; daily t=2.47
p=0.016; win rate IDENTICAL train(51.1) vs val(51.1); every month positive
(Feb+.93 Mar+.20 Apr+.71 May+1.19); fresh Jul6-8 +$0.68/tr. Compounding
$100->$452/90d in-sample. HONEST CAVEATS: pooled w/ 15m daily p=0.34 (older
era dilutes); NOT pre-registered (6 passes -> discount p, treat as best
candidate not proof); fill CAPACITY at <0.50 unverified (recorded ToB ask,
cheap sides may be thin). This is the strongest, most stable, mechanistically
coherent result in the project and the first to reach daily significance.
NEXT to confirm: capacity/fill-depth at the cheap ask; forward paper or fresh
days; pre-registered one-shot on days > Jul 8.

## Capacity + hit/miss dissection of cheap+signal (2026-07-11, nix_capacity.py)

HIT/MISS METRICS (what makes it work): deep discounts are TOXIC not cheap —
ask [.30,.44) wins 35.5% (-6.4pp vs breakeven), ask [.44,.50) wins 51-53%
(+3-4pp). |z|>=.40 (calm-market spike) inverts to 44%. Book leaning AWAY from
our side wins MORE (53.0 vs 49.9) = mispricing signature. Refined rule
ask[.44,.50) & |z|[.05,.40): 5m 53.9% +$0.99/tr — but the lift is val-heavy
(train Feb-Mar 52.2% p=0.29, val Apr-May 56.9% p=0.028), so refinements are
mechanistically-motivated bonuses, NOT proven multipliers. Base rule stays
the headline.

CAPACITY (reload of real book depth at the signal-side touch, 987 5m windows):
ToB $ at touch: p50 $27, p25 $7, p10 $2. Windows with >=$5: 80%, >=$10: 70%,
>=$25: 51%, >=$50: 36%. $50 walk slippage median 0.48c (p90 1.9c).
REALISTIC fills (walk book to stake, daily-t):
  $5  all:  EV +$0.286/tr (+5.7%) t=2.38 p=0.019
  $10 all:  EV +$0.540/tr (+5.4%) t=2.30 p=0.024
  $10 SKIP-IF-THIN (only trade >=$10 at touch): n=687, wr 53.0%,
       EV +$0.923/tr (+9.2%), daily-t=2.98, p=0.004  <-- BEST, deployable rule
  $25 skip-thin: t=1.43 (capacity binds — deployable size is ~$5-10, not more)
The operational skip-thin rule (only trade fillable windows) IMPROVES the edge
because thin windows overlap the toxic deep-discount tail. Small-capacity edge:
~7.6 trades/day 5m at $10 = ~$7/day EV. STILL: not pre-registered (discount p),
5m-recent-era only, needs a clean forward one-shot on days > Jul 8.

## Cheap+signal across all 5 coins (2026-07-12, coin_cheapsig.py) — Apr2-May12, 5m

Re-downloaded ETH/SOL/XRP/BNB/DOGE book (full, pre-open) + coin Binance ticks,
applied the FROZEN BTC rule (ask<0.50 & |z|>=0.05, hold). Fee ~0.07 (slightly
optimistic vs 0.072 pre-May-7). Daily-EV t-test, 41 days.

  coin   n    wr     EV/tr   daily_t   p
  eth   381  54.1%  +$1.15   +1.47   0.149   positive hint, NOT significant
  sol   573  49.7%  +$0.03   -0.03   0.974   dead
  xrp   408  47.1%  -$0.54   -0.58   0.567   negative
  bnb   104  57.7%  +$1.55   +1.56   0.131   positive hint, tiny n
  doge  442  46.8%  -$0.63   -1.14   0.262   negative
  POOL 1908  49.8%  +$0.06   +0.12   0.902   FLAT (positives & negatives cancel)
  BTC*  386  52.3%  +$0.85   +2.00   0.052   (*same Apr-May window, reference)

VERDICT: the cheap+signal edge does NOT robustly generalize. BTC is the edge;
ETH shows a positive hint of comparable magnitude (+$1.15/tr) but insignificant
on 41 days; BNB positive but n=104; SOL flat; XRP/DOGE negative. Pooling all
coins is FLAT — you cannot blindly run all 5. Scaling lever is BTC + ETH (maybe
BNB), i.e. ~2-3x BTC alone, NOT 5x. Refined rule same picture. Deploy candidates:
BTC (confirmed-ish, t=2.98 full sample), ETH (worth paper-testing to grow n).
Do NOT deploy SOL/XRP/DOGE.

## Coin cheap+signal, FULL Apr2-Jul8 (2026-07-12) — 95 days, per-month + recent OOS

Extended the test (user challenge: 41 days wasn't enough). Now 95 days incl. the
May13-Jul8 window where the alt-decay-lag hypothesis predicted the alts might
carry the edge after BTC's died. Fee ~0.07.

FULL Apr-Jul per coin (cheap+signal ask<0.50 & |z|>=0.05, $10 hold):
  eth  n=873  wr49.8% EV+$0.19 t+0.48   flat
  sol  n=1255 wr49.5% EV-$0.07 t-0.58   flat
  xrp  n=795  wr49.3% EV-$0.12 t-0.07   flat
  bnb  n=139  wr52.5% EV+$0.51 t+0.09   noisy, tiny n
  doge n=653  wr46.2% EV-$0.77 t-2.12   SIGNIFICANTLY NEGATIVE

PER-MONTH: the alt-lag hypothesis is FALSE. eth's edge was in APRIL (+$0.90
t=2.26) and DIED May->Jul (-$0.57,-$0.78) — same arc as BTC, no 2mo lag. bnb
Apr +$2.13(t2.86) then May -$3.71 = fluke. sol/xrp/doge no consistent month.
RECENT May13-Jul8 (OOS): ALL flat-to-negative (eth-0.55, sol-0.16, xrp+0.33,
bnb-2.57, doge-1.06). Nothing alive recently on any coin.

VERDICT (now well-supported, not premature): cheap+signal is BTC-specific. No
alt carries it over 95 days, and none revives in the recent window. "Do not
deploy SOL/XRP/DOGE" now stands on real data. SOBERING: eth (BTC's closest
cousin) shows the SAME Apr-peak-then-decay arc, so the cheap+signal family may
be a fading regime — BTC's own edge must be re-checked forward (post-Jul-8
one-shot) before trusting it; the alts dying in Jun-Jul is a warning it may too.

## Per-coin RE-OPTIMIZATION with train/val discipline (2026-07-12)

User: "with adjustments you can make it work for the coins." Tried rigorously:
per coin, swept ask band (lo 0/.3/.4, hi .45-.60), |z| gate (0/.05/.15),
direction (signal vs fade); picked best-EV config on TRAIN(Apr-May), tested the
SAME config on VALIDATION(Jun-Jul). CAUGHT A FALSE POSITIVE: ETH fade looked
like it held OOS (t=2.4) but that used a fade PRICING BUG (bought winning
outcome at the cheap side's ask). Corrected (fade entry = 1 - signal_ask = the
expensive mirror side): ETH fade TRAIN -$0.18 / VAL -$0.04 = dead breakeven.
ETH cheap+signal: TRAIN +$0.66 but VAL -$0.73 (overfit/decay). SOL/XRP/BNB/DOGE
all fail OOS. NO coin, NO adjustment survives validation. Why tuning can't fix
it: OOS (Jun-Jul) win rates are ~50% for all coins regardless of gate — there
is no signal to sharpen, so re-tuning only relabels noise. (Note: coins DID
have a different, real edge — the final-seconds nix1 nowcast, Apr +$86/May
+$220/day per mc_judge — also dead since June.) Verdict stands: cheap+signal is
BTC-only; no live coin edge by any strategy now.

## v2 improvement research (2026-07-13) — disciplined, forward test untouched

4 candidate filters on the refined 5m cell (train Feb-Mar / val Apr-May) + 1
exit variant on the tape:
- book-leans-away (q_imb<-0.05): SURVIVES both halves (53.6/50.8 train,
  59.0/54.8 val, EV ~2x/trade) — mechanism = crowd piled other side. -> V2.
- tight-spread: sign flips train/val -> noise, rejected.
- z sub-band [.05,.10): no val lift -> rejected.
- hour-of-day: sign flips -> rejected.
- late-TP 0.95 maker exit: EV identical to hold (+1.016 vs +1.013), sd 9.90
  vs 10.49 — martingale optional-stopping confirmed empirically; rejected
  (complexity for nothing).
Bot: book_summary() (bid+ask+q_imb, live-verified mirror-consistent), q_imb
now logged on every decision (v1 diagnostics unchanged), --qimb-max flag =
v2 gate. v2 pre-registered in bot/cheapsig.json; runs as parallel paper2.

## FILL AUDIT + RISK ENGINE (2026-07-28) — deployability, not alpha

src/nix_fillaudit.py, bot/live/risk.py, src/nix_riskcal.py, tests/test_nix2_risk.py.
All research on HISTORICAL data only; the 76 live forward trades were never
tuned on (that is the only clean evidence and fitting it would burn it).

FILL AUDIT (810 gated windows, 90 days). Gate on the book AS SEEN at T0,
fill at T0+L — the live bot observes then its order arrives later:
  latency  0ms  EV +$1.278 t=3.32 |  250ms +$1.208 t=3.70
          500ms      +$0.911 t=2.15 | 1000ms +$0.989 t=2.28 | 2000ms +$0.832 t=1.64
  queue risk (pay a full cent worse): 250ms +$0.969 t=3.23; 1s +$0.754 t=1.86
  book stability T0->+250ms: 87% unchanged, mean drift +0.09c (worse 9%)
  depth at touch: p50 $30, >= $10 in 74%, >= $25 in 55%, >= $50 in 39%
  -> DEPLOYABLE. A VPS at 100-200ms sits far inside the safe zone, and the
     edge survives even always missing the touch by a cent.

CAPACITY — CORRECTION to the earlier "max $10-15, profit peaks $25-30" claim.
That was an artifact of the skip-if-thin convention (it DROPS windows as the
stake grows: 596 -> 443 -> 314). Walking the book instead keeps all 809:
   stake   skip-thin@touch        walk-the-book (conservative walk50 price)
   $10     $8.00/day t=3.70       $8.02/day t=2.31
   $25     $14.35/day t=2.23      $20.04/day t=2.31
   $50     $21.03/day t=1.56      $40.09/day t=2.31
  ROI holds ~8.9% from $5 to $50; walk slippage median +0.39c. So capacity is
  ~$50/trade, NOT $10-15. At $10 the two conventions tie, so NO change to the
  running test is warranted; the walk convention matters only when scaling.

RISK ENGINE — two of my own bugs caught by calibration:
  1. drawdown halt was a stake-MULTIPLE (40 stakes) = 160% of bankroll at the
     intended sizing: it could never fire before ruin. Now a bankroll fraction
     (35%).
  2. the naive decay detector (t<-1.5, n>=60, window 120) halted a genuinely
     PROFITABLE edge 38% of the time — sequential testing, evaluated every
     trade. Swept properly: (t<-1.5, n>=250, window 400) gives 3.7% false-halt
     while still catching a -$0.50/tr dead edge 78-94% of the time.
  Validated: replaying the real profitable cell -> no halt (596/596 traded).
  Sizing is NOT Kelly (8-11% tolerates ruinous DD); 1% of bankroll, from the
  measured DD distribution (bootstrap p99 = 30 stakes). $10 stakes therefore
  need a ~$1000 bankroll (earlier "$600-800" was light). 10/10 tests pass.

## REALISTIC EXECUTION (2026-07-28) — paper fills made honest

Flaw found in the paper bots: they fill at the ask OBSERVED at decision time
(T0 = B-500ms) even though the order is only submitted at B-250ms. That
assumes the liquidity waited for us. Fixed behind --realistic:
  - RE-FETCH the book at fill time; fill against what is actually there
  - fill as a marketable LIMIT at observed_ask + slip_ticks (default 1c),
    so a book that moved away gives a PARTIAL fill or NO fill
  - pm.walk_price() gained limit_px; settle.py now uses the notional actually
    spent (fill.spent) rather than the intended stake, and flags PARTIAL
v1/v2/v3 unchanged (flag is opt-in) so the frozen forward test stays clean.
REMAINING un-modellable gap: competition. The book shows what IS resting, not
how other bots react to us repeatedly taking it. Paper stays an UPPER BOUND at
$25-50; only small real orders can settle that.

## FORWARD TEST STATUS (2026-07-31) — not confirming

paper1 (the clean frozen test) across three checks:
  Jul27  77 tr / 16 d  54.5% wr  +$85  t=1.37
  Jul28  82 tr / 17 d  53.7% wr  +$74  t=1.12
  Jul31  95 tr / 19 d  51.6% wr  +$43  t=0.92
Last 13 trades went 5W-8L. Still above the ~49% breakeven and the risk engine
is calm (drawdown $52 of $350), but t is moving AWAY from the 2.0 bar.

SAMPLE-SIZE CORRECTION (an error of mine, recorded so it is not repeated):
telling the user "~2.5 weeks to a verdict" was wrong. Separating a 53% edge
from a 50% coin flip at t=2 needs ~1100 trades ~ 7 months at 5 trades/day.
95 trades cannot distinguish "small real edge" from "no edge" — 51.6% sits
0.27 SE below 53% AND 0.31 SE above 50%; both hypotheses fit. The early
t=1.37 was a lucky opening run, and I extrapolated from it. At the current
observed effect size t=2.0 needs ~90 trade-days (~4.5 months).

paper4 EXECUTION VALIDATED (21 trades, 209 windows): fill prices exactly 5x
paper1's at $50; first PARTIAL fills appeared ($38.91, $22.78) and are priced
on notional actually spent; two fills at 0.50 where the book moved between
decision and order (the marketable limit absorbed it, ~$2 cost); zero
cant_fill/unfilled/walk_too_deep. $50 is mechanically fillable; its -$82 is
the same fading signal at 5x size, not an execution problem.

VERDICT STANCE: paper1 reaches its 20-trade-day evaluation point imminently
and will NOT clear the pre-registered bar (needs t>=2.0, has 0.92) -> NOT
CONFIRMED. That is not "proven dead", it is "do not fund". Cost of continuing
is zero, so keep observing, but as a months-long watch, not a countdown.

## LIVE-PATH AUDIT (2026-08-02) — independent Fable-5 audit, findings CONFIRMED

An independent adversarial audit of the live order path, plus my own Telonex
verification. All five blockers below were re-verified directly in source.

TELONEX VERIFICATION (my pass) — the paper record is HONEST:
  - settlement: 18/18 of paper1's recent win/loss calls match Telonex
    result_id (settle.py uses gamma outcomePrices — an independent source).
  - prices: downloaded the real book_snapshot_25 for 7 traded windows;
    the ask the bot recorded matched Telonex EXACTLY 7/7.
  - depth at those touches $13-$378, which explains paper4's partial fills.
  - feed fidelity: Coinbase-live z-gate pass 14.4% (30/209) vs Binance-hist
    11.1%; z=+1.52, p=0.13 -> CONSISTENT. (An earlier "MISMATCH" print of
    mine used an arbitrary threshold and was wrong.)
  - unexplained: paper1 trades 5.0/day vs 6.7/day expected after the depth
    filter (25% short). Regime or restarts; not resolved.

LIVE-PATH BLOCKERS (confirmed in source, all in code I wrote):
  1 AUTH: pm.py post_order requires L2 creds (SDK assert_level_2_auth);
    nix2_live treats PM_API_* as optional and never derives them.
  2 WALLET: ClobClient built with no signature_type/funder -> EOA signing;
    funded accounts normally hold USDC in a proxy wallet -> rejects.
  3 RECORDS: `rec["fill"] = execu.buy(...)` is unguarded (nix2_live.py:140)
    and buy() returns the INTENDED price/shares without inspecting resp;
    the loop's blanket except means killed orders leave no record at all.
  4 ORDER TYPE: live posts OrderType.FOK (all-or-nothing) while the
    --realistic sim models PARTIAL fills. paper4's observed partials are
    IMPOSSIBLE live; the FOK limit is also the walk AVERAGE, which can round
    below the level the walk consumed. => paper4's "$50 is mechanically
    fillable" does NOT hold for the live code as written. Fix: OrderType.FAK
    with limit = observed ask + slip_ticks.
  5 RISK: bot/live/risk.py has ZERO references in nix2_live.py. A real-money
    run would have no drawdown/decay/streak halt and no bankroll sizing.
  Also SERIOUS: no redemption of winning CTF tokens (EOA mode -> bankroll
  drains while "winning"); no crash/position reconciliation; ~250-700ms of
  unmodelled order latency (per-token SDK caches are always cold on a new
  5m market) which pushes the real fill to ~B+0..B+500ms vs paper's B-250ms
  — the author's own latency curve prices that at -$0.20..-$0.40/trade.
  CLEAN (verified, no action): fee model exact (0.07, matches 4,661 on-chain
  fills 2026-07-31), min size 5 / tick 0.01 agree across gamma+CLOB, token
  ordering correct.

ACTION TAKEN: --live is now HARD-LOCKED in nix2_live.py with the blocker list
inline. Paper mode is untouched. Unlocking requires fixing the blockers AND
the forward test actually passing its bar (it is not: t 1.37->1.12->0.92).

## WHY 5m AND NOT 15m (2026-08-02) — same rule, both families, identical gates

  family    n   days   win rate   EV/trade      t
  5m      809     90      53.9%     +0.989   +2.45
  15m     408    169      51.2%     +0.664   +0.48

15m is DIRECTIONALLY the same (positive, same sign) but far weaker and not
significant, and it fires ~2.4 trades/day vs 5m's 9.0. Looser gates make 15m
worse, not better (|z|>=0.02: 48.3% wr, t=-0.98).

MECHANISM (this is why, and it is not a fitting artifact): the edge is a
~1-second head start on a lagging oracle. z = g / (sigma * sqrt(duration)),
so a 15m window carries sqrt(3)=1.73x more total uncertainty than a 5m one —
the SAME one-second peek is a proportionally smaller fraction of what the
window can still do. Measured: 15m passes the z-gate 6.5% of the time vs 5m's
11.1%, and offers 86 windows/day vs 287.
=> shorter window = bigger edge. 5m is the SHORTEST family Polymarket offers
(5m/15m/1h/4h), so we are already at the optimum; 1h and 4h are predicted
worse still by the same sqrt(duration) argument.
COHERENCE CHECK PASSED: the effect shrinks in the direction and roughly the
magnitude the mechanism predicts, which is mild independent support that the
5m result is a real effect rather than a fitted one.

COINS: tested on 5m across eth/sol/xrp/bnb/doge, 95 days (results/coincs/) —
none carry it (eth/sol/xrp flat, bnb noisy small-n, doge significantly
negative), and no re-tuning survived train/val. Coins on 15m are UNTESTED and
low prior: it is the intersection of two conditions that each already failed
(coin 5m dead, BTC 15m insignificant). Would need a fresh multi-hour download.

## LIVE FEED SPARSITY vs RESEARCH FEED (2026-08-02)

The live fleet runs `--venue coinbase`; the frozen rule's evidence was built on
Binance 1s klines. Measured the signal's zero-rate on both:

    research (Binance 1s klines, 90 days, n=25,820):  g == 0 in 48%
    live     (Coinbase ticker, 300 windows):          z == 0 in 59%
                                                      difference: +11 pp

Reading:
  * ~48% is INHERENT, not a defect. BTC's 1-second return is exactly zero
    about half the time even on a dense tick feed — that is what a 1s
    lookback looks like, and the rule was built on top of it.
  * The +11 pp gap IS real (SE 2.8pp at n=300, so z ~ 3.9). On Coinbase a
    zero can mean "genuinely flat" OR "no trade arrived, so both price_at()
    lookups returned the same stale tick". The second case is information
    loss and costs ~11% of windows.
  * Net: live sees ~41% usable windows vs ~52% in research, i.e. ~21% fewer
    opportunities than the research feed implies.

DECISION: do NOT switch venue now. paper1-4 are pre-registered forward tests
and changing the signal's input feed mid-flight voids them (Rule 2).

Two reasons this is not urgent:
  * The published timeline ("~33 more trade-days to t>=2.0") derives from
    paper1's OBSERVED live rate of 5.0 trades/day, which already carries this
    handicap. No recalculation needed.
  * The sign of the effect on edge QUALITY is unknown — the windows Coinbase
    drops may be the least informative ones. No evidence either way.

Revisit only after paper1 reaches its verdict. If it passes, aligning the
deployment venue to the research feed (--venue binanceus) is a candidate for
its own pre-registered test, never a silent switch.
