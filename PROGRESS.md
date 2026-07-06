# PROGRESS — Polymarket BTC Up/Down Strategy Discovery

**Current phase:** 0 (Data acquisition & integrity)
**Current step:** 0.2 coverage audit (in progress)
**Last updated:** 2026-07-06 (session 1)

## Environment facts (verified this session)

- Remote ephemeral container (Claude Code on the web). Repo: xin10ylop/polybtctelonex,
  branch `claude/polymarket-btc-strategy-ys9coc`. **Data does NOT survive container
  reclamation** — only what is committed+pushed. Downloads must be re-runnable/resumable.
- Disk: **only ~31 GB available** (< the 120 GB the brief wants). Bulk download (0.4) needs
  either user confirmation to proceed with a reduced/rolling footprint, or a bigger machine.
- 4 CPU cores, 15 GB RAM, Python 3.11.15, venv at `.venv/`.
- Telonex API verified real & reachable. Schema ground truth = SDK source
  (`.venv/lib/python3.11/site-packages/telonex/`), v0.4.0:
  - Download: `GET https://api.telonex.io/v1/downloads/{exchange}/{channel}/{date}`
    with `Authorization: Bearer $TELONEX_API_KEY`; identifiers: `asset_id` OR
    `slug`+`outcome` OR `market_id`+`outcome`; returns Parquet (redirect to presigned S3).
    404 = no data that day. 403 = entitlement. 429 = rate limit w/ Retry-After.
  - Availability (public): `GET /v1/availability/{exchange}?slug=...&outcome=...`
  - Free datasets (no auth): `GET /v1/datasets/polymarket/markets` and `/tags`.
  - Channels: trades, quotes, book_snapshot_5/25/full, onchain_fills, crypto_prices,
    all_onchain_fills (whole-exchange, Pro tier, no identifiers).
  - **crypto_prices (Chainlink resolution feed) only exists from 2026-04-02** (per
    telonex.io/llms.txt). This bounds windows-table open/close reconstruction.
- Polymarket gamma API + CLOB API + data.binance.vision all reachable.

## Done

- [x] `.env` written with TELONEX_API_KEY (gitignored, chmod 600). Never print it.
- [x] `.gitignore` (data/, logs/, .venv/, .env, results/raw_grids/)
- [x] Directory layout created (data/raw, data/processed, data/HOLDOUT, configs, results,
      reports, logs, src, tests)
- [x] venv + telonex SDK 0.4.0 installed; bulk pip install (polars, duckdb, xgboost, ...)
      running in background → `logs/pip_install.log`
- [x] CLAUDE.md with the five hard rules
- [x] Telonex API schema verified from SDK source (see above)

## Next (in order)

- [ ] 0.2: Download free markets dataset; enumerate btc-updown-{5m,15m,1h} markets;
      query availability for sample markets + crypto_prices; write reports/phase0_coverage.md
- [ ] 0.3: One-day pipeline validation (download 1 day of key channels for 5m markets,
      parse → store → windows, validate)
- [ ] GATE-0 disk decision: surface 31 GB constraint to user before 0.4 bulk download
- [ ] 0.4 bulk download → 0.5 windows table → 0.6 fee regimes → 0.7 holdout split → GATE 0

## Output paths so far

- logs/pip_install.log — background package install
