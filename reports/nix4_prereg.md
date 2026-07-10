# NIXULTIMATE 4.0 — pre-registration (2026-07-10, before any 4.0 result exists)

User-ordered deep discovery pass: ML, market combinations, coin extensions, and a
definitive treatment of the user's pre-open 51c->55c scalp ("compute the highest
probability of up or down instead of guessing"). This document freezes the
protocol BEFORE any 4.0 computation runs. Rule 4 governs: negative results are
results; no threshold will be loosened after seeing outcomes.

**Context / blockers.** TELONEX_API_KEY was lost with the container (never in
git, by design). The mc campaign is paused at 78/97 days; the frozen-stack
judgment (Appendix 11) runs when the key returns and the remaining 19 days
stream in. Per the 2026-07-09 pre-registration, NO mining touches the
results/mc coin rows until Appendix 11 is written. Everything below is
key-independent or explicitly deferred.

## JOB A — BTC deep probability pass (committed stores; runs now)

- Data: results/{features,exec,maker,preopen,xtf,nixflow} — 5m Feb 12–May 12,
  15m Oct 11–May 12. Ends before the spent HOLDOUT; holdout is not touched.
- Splits (identical to all prior passes): TRAIN days <= 2026-03-19;
  VAL 2026-03-20..2026-05-12. Model selection (zoo + hyperparams) on TRAIN
  only via day-blocked purged CV; one frozen pipeline goes to VAL with
  expanding weekly refits + trailing isotonic calibration.
- Objective: P(up_won) at pre-open offsets {-30,-10,-3} and intra-window
  offsets {60,120,180,240,270}; strategy sims on top of p-hat:
  user's scalp (entry band 47..53c per-cent, maker exit +3/+4/+5c, hold to
  expiry if unfilled) and taker hold-to-expiry entries. Fees date-correct;
  entry fills bracketed conservative ($50 book-walk) / optimistic (top-of-book);
  maker exits strict trade-through (print beyond limit by >= 1 tick).
- Judgment: config count M_A logged; survivor bar = VAL t >= max(3, sqrt(2 ln M_total))
  AND profit factor >= 1.15 AND n >= 300, same as the main study. Any survivor
  additionally requires a one-shot on genuinely fresh days (>= 2026-07-08,
  after the key returns) before any deploy talk.
- Also delivered regardless of outcome: the "probability frontier" — OOS
  calibration of the best p-hat vs the breakeven-accuracy curve of the scalp
  structure, i.e. HOW GOOD a direction model must be vs how good any model
  measurably is.

## JOB B — Binance-only multi-coin direction study (free data; runs now)

- Data: Binance 1s klines, {BTC,ETH,SOL,XRP,BNB,DOGE}USDT, 2026-04-01..07-09.
- Per-window (5m/15m UTC grid) features strictly before the window open:
  multi-horizon returns (5s..3600s), realized vols, volume z, taker-buy ratio,
  trade intensity, and the SAME features for BTC (cross-coin lead), hour/dow.
- Walk-forward by day (expanding, min 21 train days), pooled-with-coin-feature
  and per-coin models (logit + LGBM at FIXED modest hyperparams — no tuning,
  so no selection to deflate). Report accuracy/AUC/Brier/calibration/abstention
  curves per coin/fam/month.
- This is a DIAGNOSTIC (no PM prices; no strategy claim). It bounds what any
  direction model can know at window open, vs the taker breakeven
  p >= ask + r*ask*(1-ask). Its per-window p-hat parquet is saved for later
  joining against PM books once the key returns.

## JOB C — full-market feature harvest + coin mining (needs key; deferred)

- Streaming per-window x per-offset feature store (pre-open books, post-open
  paths, tape, Binance + BTC-lead, Chainlink anchor/basis, cross-timeframe
  15m state), coins + BTC, Apr 2 onward, one parquet/day committed.
- Splits FROZEN NOW: TRAIN Apr 2–May 31; VAL Jun 1–30; FRESH one-shot Jul 6+
  (never in any fit; single read for survivors). Coin mining starts only
  after Appendix 11 is committed.
- Deflated bar over M_total = every 4.0 config across jobs A+C (running count
  kept in reports/nix4_notes.md).

## Deploy criteria (unchanged from the project)

Fees and book-walk slippage always on; look-ahead unit test must pass on any
new simulator; survivor => fresh-day one-shot => only then deployment talk
with the Appendix 9 risk engine. If nothing survives, the report says so.
