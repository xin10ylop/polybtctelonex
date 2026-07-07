# PROGRESS — Polymarket BTC Up/Down Strategy Discovery

**Current phase:** 3 (Strategy grid) — Phases 0, 1, 2 COMPLETE
**Current step:** Build Phase 3: vectorized backtest engine over results/features +
bookcurves (taker fills via buy/sell_avgpx curves as-of T+latency, maker fills via
trade-through on trades tape), programmatic grid (10 families + auto signal-mining over
every feature x threshold-grid x horizon x direction), sizing grid, latency 250ms/1s/3s.
Then GATE 3 (look-ahead re-test on config sample, 25-trade evidence-chain audit,
leaderboard) -> Phase 4 gauntlet.
GATE 2 PASSED: 305 feature-day files (5m 90d, 15m 214d, holdout-dated file removed),
leakage scan clean, 20/20 manual as-of spot-checks exact.

On "continue": check logs/bulk_status.json + `tail logs/bulk_download.log`.
Liveness check MUST be exact-match (pgrep -f false-positives on its own shell wrapper):
  `ps -eo pid,cmd | awk '$2==".venv/bin/python" && $3=="src/bulk_download.py"'`
If not "BULK DONE" and truly dead, relaunch:
  `nohup .venv/bin/python src/bulk_download.py >> logs/bulk_download.log 2>&1 & disown`
(resumes from per-day markers; ~1-2 min/day in the 15m era, ~4 min/day in the 5m era;
zero errors through day 99 of 268 as of 2026-07-06 16:50 UTC).
Once "BULK DONE", run in order WITHOUT asking:
  1. `.venv/bin/python src/fit_fee_history.py`   (empirical fee regimes -> configs/fee_regimes.json)
  2. build full windows table via src/windows.py over all dates -> data/processed/windows.parquet
  3. `.venv/bin/python src/split_holdout.py`      (60/20/20, physical HOLDOUT move + loader guard)
  4. re-run full GATE 0 checks; update reports/; then Phase 1.

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
