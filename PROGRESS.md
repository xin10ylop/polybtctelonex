# PROGRESS — Polymarket BTC Up/Down Strategy Discovery

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
