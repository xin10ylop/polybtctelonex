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
