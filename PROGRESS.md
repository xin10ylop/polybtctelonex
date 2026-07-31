# PROGRESS — Polymarket BTC Up/Down Strategy Discovery

**CURRENT STATE (2026-07-13) — READ THIS FIRST IN A NEW SESSION:**
- **The surviving strategy is "cheap+signal" (nix2)**, frozen in `bot/cheapsig.json`
  (v1 + pre-registered v2 with the book-imbalance gate). Buy the underpriced BTC 5m
  side (ask .44-.50) when the 1s pre-boundary Binance move confirms it (|z| .05-.40),
  depth >= stake, HOLD to resolution. In-sample: 53% wr, +9.2%/trade at $10
  skip-thin, daily t=2.98 (90 days Feb-May). BTC-ONLY: tested on eth/sol/xrp/bnb/doge
  over 95 days (results/coincs/) — no alt carries it, no adjustment survives
  train/val (reports/mc_campaign_notes.md tail has the full audit trail).
- **PAPER BOTS RUN 24/7 on the USER'S VPS** (165.227.83.238, NOT in any Claude
  container). `bot/live/` = nix2_live.py, pm.py, feeds.py, risk.py, settle.py,
  deploy/. Live accounts as of 2026-07-27:
    paper1 = v1 frozen rule, $10, touch price, skip-thin. THE CLEAN FORWARD
             TEST — never reset, never altered. TRAJECTORY (declining):
               Jul27  77 tr / 16 d  54.5% wr  +$85  t=1.37
               Jul28  82 tr / 17 d  53.7% wr  +$74  t=1.12
               Jul31  95 tr / 19 d  51.6% wr  +$43  t=0.92
             Still above the ~49% breakeven, risk engine calm (DD $52/$350),
             but every metric is sliding and t is moving AWAY from the 2.0 bar.
             *** SAMPLE-SIZE CORRECTION (my earlier "~2.5 weeks" was WRONG) ***
             Distinguishing a 53% edge from a 50% coin flip needs ~1100 trades
             (~7 months at 5/day). The early t=1.37 was a lucky opening run
             flattering the estimate. At the CURRENT effect size t=2.0 needs
             ~90 trade-days (~4.5 months). Do NOT re-promise short timelines.
             Base rate from this project: every edge found so far decayed
             within 2-3 months, so treat sliding numbers as the likely case,
             not as noise to wait out.
    paper4 = $50, --walk --realistic --slip-ticks 1. Max-size execution recon.
             EXECUTION VALIDATED (Jul31, 21 trades): fills matched paper1's
             prices EXACTLY at 5x size; 2 PARTIAL fills ($38.91, $22.78)
             priced and P&L'd on notional actually spent; 2 fills at 0.50 when
             the book moved (marketable limit absorbed it, cost ~$2 each);
             zero cant_fill / unfilled / walk_too_deep in 209 windows. So $50
             is MECHANICALLY fillable. P&L -$82 at 47.6% wr = the same fading
             signal, 5x sized — NOT an execution failure.
    paper2 = RETIRED 2026-07-27 (v2 qimb gate: 48.7% wr, -$5, it selected the
             losers — a history-fitted filter inverting live, same failure mode
             as the Appendix 11 calibration gate). Log kept as evidence.
  DO NOT change paper1's rule mid-test and DO NOT reset its counter (choosing a
  start date after seeing results is the same error as v2). Check results only
  via the user pasting settle.py output.
- **FILL AUDIT + RISK ENGINE (2026-07-28)**, see reports/mc_campaign_notes.md:
  edge survives 1s latency (t=2.28) and paying a full cent worse (t=3.23);
  book unchanged 87% of the time in the 250ms decision->fill gap. CAPACITY
  CORRECTION: the old "caps at $10-15" was a skip-thin artifact; walking the
  book holds ~8.9% ROI to $50/trade ($40/day vs $21 skip-thin). risk.py sizing
  = 1% of bankroll (NOT Kelly), halts on 35%-of-bankroll drawdown / 12 straight
  losses / rolling decay t<=-1.5 over >=250 trades — calibrated so it
  false-halts a LIVE edge only 3.7% per 800 trades (the naive setting did 38%).
  10/10 tests in tests/test_nix2_risk.py. MONITOR-only in paper (settle.py
  replays it); ENFORCE when real money goes live.
- **DERIVED DATA (committed, ready for analysis without ANY download):**
  results/nix_scalp6_rows.parquet (44k BTC 5m/15m boundary rows w/ features),
  results/coincs/ (5 alts x 98 days), results/mc/ (multicoin final-seconds
  campaign), results/nix_scalp*.parquet, results/nixflow|xtf|preopen stores.
- **RAW DATA (data/) IS GONE in a fresh container** — gitignored, never committed.
  Re-download per-day ONLY if tape-level work is needed: Binance from
  binance.vision (free, src/mc_campaign.py binance_aggtrades), Telonex via
  src/download_day.py + src/consolidate.py (needs TELONEX_API_KEY in .env —
  user must re-create .env; NEVER print the key).
- Earlier program: FINAL_REPORT.md Appendices 1-11 (main verdict: zero grid
  survivors; nix1 final-seconds edge holdout-passed then decayed to fee floor
  everywhere by July). HOLDOUT SPENT — never read data/HOLDOUT.

**Previous LATEST (2026-07-11): Appendix 11 — multicoin campaign complete (97/97
days, results/mc/, src/mc_campaign.py + src/mc_judge.py). Registered deploy
bar FAILED (frozen stack -$0.31/day on unseen Jun1-Jul7, t=-0.18): NO DEPLOY.
Post-mortem: the BTC-fit calibration gate inverted selection on alts (blocks
rich asks that win .95, keeps dead cheap bucket); basis guard behaved.
Scalp question closed 3 ways (fee audit vs 2.4M
fills exact; zero-fee counterfactual all-negative; REAL fee-free 15m era
all-negative) — reports/mc_campaign_notes.md.**

**Current phase:** COMPLETE + extensions. FINAL_REPORT.md (main verdict: zero grid
survivors) + Appendices 1-7. **HOLDOUT IS SPENT** — read exactly once (Appendix 6,
frozen oracle-trade configs). It must NEVER be read again; any further validation
uses only genuinely fresh post-2026-07-05 days.

**State of the one survivor line of work:**
- Appendix 6: oracle-feed final-seconds trade. Holdout one-shot: PAID feed variant
  PASS (+$0.32/trade, t=2.4); broadcast-only variant FAIL. Requires paid Chainlink
  Data Streams sub.
- Appendix 7: FREE hybrid nowcast (PM broadcast anchor + Binance leading return),
  frozen gates, src/oracle_hybrid.py. Dev n=1131 +$1.51/trade t=7.6; fresh-OOS
  2026-07-06: ZERO trades (books 98-99c at final seconds; plus a discovered
  Binance-Chainlink basis failure mode that fakes high |z| in calm windows —
  2 confidently-wrong signals, unfilled only by tape-validation luck).
  Fresh-OOS 2026-07-07: 3 trades +$1.61 (3/3 wins, 13/13 directions correct,
  10/13 EV-starved at 93-99c). Two-day fresh-OOS: ~$0.80/day at $5 stakes vs
  dev $20.9/day — signal alive, payment competed to the fee floor.

**NIXULTIMATE pass (Appendix 8, 2026-07-08):** 7 new game-theory families
(straddle, panic-harvest maker, near-resolution maker pm/hyb-gated,
cross-timeframe laggard maker, model-quoting maker, flow/depth grid incl.
pre-open flow triggers) = 2,133 mined configs, deflated bar 3.92, ZERO
survivors. Core finding: taker flow is informed (Binance-led) -> every
passive structure adversely selected; aggressive pays the fee wall. N8 =
nix1's frozen config transplanted to 15m (pre-registered, not mined): dev
n=266 +$2.11/trade t=5.8 (misses n>=300 bar), fresh-OOS Jul 6-7 ZERO trades
(15m final-seconds books now 99.5c+, same competition as 5m). Sims:
src/nix_{straddle,panic,near,xtf_maker,quote,grid,flow_cols,judge}.py,
src/nix_15m_lastsec.py; results/nix_*.parquet.

**Full-timeline audit (Appendix 9, 2026-07-08, user-ordered — includes a
flagged second read of the spent HOLDOUT, frozen params, audit only):**
combined $/day at $5 stakes: Apr $40.20, May $39.45, Jun $3.79, Jul1-7 $2.19,
Jul 6-7 zero. Decay mechanism: median final-3s ask 0.971->0.989. Risk engine
built and tested: bot/risk_engine.py + bot/config.json + tests/test_risk_engine.py
(16/16). Basis guard adopted (defensive overlay, +$21.79 net over timeline,
blocks the Jul 6 fake-signal class). src/nix_audit.py regenerates the audit.

**NIXULTIMATE 2.0 (1h family) IN PROGRESS:** hourly series ALIVE (slug rename Apr 6 fooled Phase 0); FULL Telonex book coverage Oct11-Jul7 downloaded+consolidated (data/processed/daily/1h/, 3.1GB, 270 dates, src/hourly_bulk.py); fees: 0 pre-Mar-6, then 0.0624/0.072/0.07 (configs updated, on-chain verified); resolution = Binance 1H candle direct (765/765); mirror exact. Splits for 1h: TRAIN<=Mar19, VAL Mar20-May12, RESERVE May13+ SEALED (loader guard; one-shot only). src/nix1h_lastsec.py (books-based, book-walk fills standard): frozen transfer TRAIN n=142 +$2.01/tr t=8.56 wr99.3%; VAL n=57 +$0.49/tr t=1.59; evonly variant = 1 lottery win, insignificant. NEXT (task 14, run without asking): (a) mid-hour stale-quote sniper — per-minute Binance fair vs 1h book asks, walk-forward calibrated win-prob (isotonic on TRAIN only), taker fills from bookcurves, hold to close; (b) near-resolution maker on 1h (9-month tail power); (c) straddle/panic/flow ports if warranted; then judge at deflated bar, one-shot RESERVE for survivors, Appendix 10, commit.

On "continue": Appendices 7-9 are final. To extend fresh-OOS by another day D:
fetch Binance (bulk_binance.do_klines/do_aggtrades), process_day(D, rm_raw=True),
refresh markets metadata (`curl -sSL
https://api.telonex.io/v1/datasets/polymarket/markets -o
data/raw/telonex/polymarket_markets.parquet`), then
`.venv/bin/python src/oracle_hybrid.py D --diagnose` (5m) and
`.venv/bin/python src/nix_15m_lastsec.py D` (15m). Next decision point: user
chooses whether to build the Phase 6 live paper bot (free feeds, $0 risk):
nix1 + N8 signals with a real-time EV-gate monitor on both families —
trades only when final-seconds books leave >2c after fees again.

## Environment facts (verified)

- Remote ephemeral container. Branch `claude/polymarket-btc-strategy-ys9coc`. Data does NOT
  survive container reclamation — only committed files. All downloads resumable by design.
- Disk: ~31 GB available (< brief's 120 GB threshold — hence the confirmation gate).
  Measured footprint of compressed pipeline: ~17 GB total (see "Storage design" below).
- 4 cores, 15 GB RAM, Python 3.11 venv at `.venv/` (polars, duckdb, xgboost, lightgbm,
  sklearn, scipy, statsmodels, matplotlib, pytest, telonex SDK 0.4.0 all installed).
- Telonex API schema verified from SDK source; endpoints in src/telonex_dl.py docstring.
  Key facts: Up/Down books are exact mirrors (only Up needed); crypto_prices (Chainlink
  btcusd) exists 2026-04-02→now; markets metadata parquet is free and includes result_id
  (resolution), asset ids, and per-channel coverage dates.
- Fee ground truth (docs + live CLOB + on-chain fills all agree):
  fee = shares × r × (p(1-p))^e, taker-only; currently r=0.07, e=1 for all btc-updown.
  Live snapshot: configs/fee_params_snapshot_2026-07-06.json. Pre-2026-01-05: no fees
  (2025-11-15 fills files have no taker_fee column at all).
  NOTE: the brief's formula (extra ×p) was wrong; official docs table verified exactly.
- Resolution rule (official + verified 288/288 on 2026-06-15): first Chainlink tick
  (source `timestamp_us`) at/after boundary; close >= open → Up (result_id "0").
- Coverage (reports/phase0_coverage.md): 15m tick data 2025-10-11→now (~9mo);
  5m 2026-02-12→now (~5mo); 4h 2025-10-15→now; hourly series ENDED 2026-04-06.

## Storage design (measured on real days)

Raw is ~1.5 GB/day (5m era) — consolidated via src/consolidate.py to ~62 MB/day:
quotes = BBO price-change rows only (prices full fidelity, 96% of updates are size-only
jitter); books = cost-to-fill curves ($50/$200/$1k/$5k both sides) + depth on 250ms grid;
trades/fills full res; raw deleted after consolidation (--rm-raw). 15m era ≈ 19 MB/day.
Estimated totals: Telonex ~12 GB + Binance ~4 GB. Bulk runtime est. 8-14 h.

## Done (session 1)

- [x] .env with key (gitignored); .gitignore; dir layout; venv
- [x] 0.2 coverage audit → reports/phase0_coverage.md
- [x] 0.3 one-day pipeline validation (2026-06-15 full 5m day + 15m-era day 2025-11-15):
      download → consolidate → windows → outcomes 288/288 vs result_id
- [x] Downloader (src/telonex_dl.py), day worker (src/download_day.py, resumable,
      marker files), consolidation (src/consolidate.py, schema-evolution aware)
- [x] 0.5 windows builder (src/windows.py) with >= tie rule
- [x] 0.6 fee model (src/fees.py) + live param snapshot + dated regimes (empirical
      refinement script src/fit_fee_history.py ready, runs post-bulk)
- [x] Execution primitives (src/execution.py): book-walk taker + trade-through maker
- [x] Loader with HOLDOUT guard (src/loader.py); splitter ready (src/split_holdout.py)
- [x] GATE 0 unit tests ALL PASSING (15): fee worked examples exact, book-walk vs hand
      values, vectorized walk vs reference, maker fill rules, look-ahead shift test
      (shifted feed flips ~50% of outcomes; unshifted matches ≥99.9% of resolutions)
- [x] Binance pipeline validated; bulk scripts ready (src/bulk_download.py, bulk_binance.py)
- [x] Cross-source reconciliation vs Polymarket CLOB prices-history API
      → reports/phase0_reconciliation.md (250 windows sampled)

## GATE 0 status

- Outcomes ≥99.9%: PASS (288/288 on validation day; full-history check re-runs post-bulk)
- Look-ahead test: PASS
- Coverage report: DONE (gaps explained: 5m listing gap Jan27-Feb11 predates tick coverage)
- Fee worked examples: PASS (exact vs official docs table)
- Cross-source reconciliation ≥200 windows: see reports/phase0_reconciliation.md
- Unit tests (fees, slippage, maker fills): PASS (15/15)

## Next

- [ ] USER CONFIRMATION for bulk (disk 31 GB < 120 GB brief threshold; plan fits in ~17 GB)
- [ ] 0.4 bulk (Telonex + Binance) → fee fit → windows.parquet → 0.7 holdout split → GATE 0 full → Phase 1

## NIXULTIMATE 3.0 CAMPAIGN (2026-07-09, IN FLIGHT — continue without asking)

WHY: BTC decay = retail crowd LEFT (on-chain: final-secs takers 13.9k->5.4k
Apr->Jul), competition never arrived. The April-state persists on neglected
coins. Jul 6 diagnostic (fresh day): winner-ask@T-3s median — ETH 0.940
(q25 0.785!), SOL 0.970, BNB 0.960, XRP 0.980, DOGE/HYPE 0.990 w/ 22-24%
<0.95 (BTC: 0.99, dead). Frozen machine on ETH Jul 6 (real ETHUSDT klines
signal, size-checked): 4/4 wins +$3.97 at $5. Committed: src/mcdiag.py.

RUNNING: src/multicoin_bulk.py (nohup, logs/multicoin_bulk.log) — 6 coins x
{5m,15m}, Apr2-Jul7, book25+trades Up-only -> data/processed/daily/{coin}-{fam}/,
coin Chainlink broadcasts -> data/processed/coin_prices/{sym}/, Binance 1s
klines -> data/processed/binance/klines_1s_{SYM}/ (HYPE not on Binance spot
— expected 404, coin gets no nowcast leg). Resumable via .mc_done_ markers.
Plumbing DONE: consolidate/windows handle coin families ({coin}-5m etc.).

WHEN BULK DONE (est. ~11h), in order:
1. VERIFY resolution per coin: build_windows("{coin}-5m", [2 sample days])
   reconciliation vs result_id using coin_prices feed (expect ~100%; loader
   load_crypto_prices is btc-only — read data/processed/coin_prices/{sym}/
   directly).
2. VERIFY fees per coin: onchain_fills sample (2 markets/coin) implied r
   (expect 0.07; add {coin}-5m/{coin}-15m regimes to configs/fee_regimes.json
   — currently missing! fees.params will KeyError otherwise).
3. RUN frozen machine per coin x fam: generalize src/oracle_hybrid.py run_day
   (anchor = coin_prices server_ts; nowcast = klines_1s_{SYM} 1s closes;
   frozen gates unchanged; book-walk 50 fills + top-of-book $5 check;
   report BOTH with/without tape validation). Monthly tables Apr-Jul.
4. AUDIT: ETH Jul 6 must reproduce ~4 trades/+$3.97 (inline test benchmark);
   BTC pipeline sanity already reproduces. Spot-check 5 trades vs raw books.
5. Judge honestly (frozen transfer, not mined). Then 3-month P&L projection
   from $100 bankroll (stake=bankroll/20, min $5 PM order): use LATEST-month
   per-coin rates, not averages; scenarios bear/base/bull; ladder mechanics.
6. Appendix 11 + commit + report to user.
