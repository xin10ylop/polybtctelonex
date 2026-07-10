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
2026-06-17: 3799 download errors, skipping day (LocalProtocolError: Illegal header value b'Bearer ')
