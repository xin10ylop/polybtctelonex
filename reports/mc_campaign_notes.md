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
