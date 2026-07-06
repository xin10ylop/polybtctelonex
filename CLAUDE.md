# Polymarket BTC Up/Down Strategy Discovery Engine

On every new session: read PROGRESS.md and continue from the current step without asking.

## THE FIVE HARD RULES

1. **No look-ahead, ever.** Features at decision time T use only data timestamped strictly
   before T. All joins are as-of joins. The look-ahead unit test (shift inputs forward one
   step → results MUST change materially) must pass before any backtest is trusted.

2. **The holdout is sacred.** The chronologically last ~20% of data lives in `data/HOLDOUT/`.
   The data loader refuses to read it unless called with `--holdout-final-run`. It is read
   exactly once, in Phase 5, with frozen parameters. Never retune after seeing holdout results.

3. **Fees and slippage always on.** No leaderboard number is ever computed without the
   date-correct fee model and book-walk slippage. Pre-fee numbers are diagnostics only.

4. **Negative results are results.** If nothing survives, FINAL_REPORT.md says so with
   evidence. Never loosen a filter to manufacture survivors. Never relax thresholds.

5. **Reproducibility.** Every result traces to a config file + seed + data version, all logged.

## Practical notes

- Secrets live in `.env` (gitignored). NEVER print, echo, or log `TELONEX_API_KEY` or
  `PM_PRIVATE_KEY` anywhere — not in chat, logs, code, commits, or reports.
- Long jobs run via `nohup` in background, resumable, logging to `logs/`.
- Use `.venv/bin/python`. Tick data via polars/DuckDB, vectorized backtests.
- Verify API schemas against real files/SDK source, never from memory.
