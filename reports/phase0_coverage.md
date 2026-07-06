# Phase 0.2 — Telonex coverage audit

Generated: 2026-07-06 14:58 UTC. Source: free markets dataset (1,956,019 markets) + public availability endpoint.

## Chainlink resolution feed (`crypto_prices`, asset_id=`btcusd`)

- Available **2026-04-02 → 2026-07-06** (~3 months).
- This is the feed Polymarket uses to resolve these markets. Windows-table
  open/close reconstruction (0.5) is only possible inside this range; outside it,
  outcomes come from market metadata `result_id` and Binance-proxy prices are
  diagnostics only.

## btc-updown-5m

- Markets: **53,237** (2025-12-18 04:25 → 2026-07-07 04:10 UTC)
- Slug timestamp modulo violations: 0 | duplicate timestamps: 0
- Status: {'active': '294', 'resolved': '52,943'}
- Resolved with result_id in {0,1}: 52,943 / 52,943
- Missing whole days inside range: 16 → ['2026-01-27', '2026-01-28', '2026-01-29', '2026-01-30', '2026-01-31', '2026-02-01', '2026-02-02', '2026-02-03', '2026-02-04', '2026-02-05', '2026-02-06', '2026-02-07', '2026-02-08', '2026-02-09', '2026-02-10']
- Partial days (fewer windows than expected, excl. endpoints): 8 → first 10: [('2026-01-21', 282), ('2026-01-26', 281), ('2026-02-12', 281), ('2026-04-15', 286), ('2026-04-16', 286), ('2026-05-26', 287), ('2026-06-17', 283), ('2026-06-20', 287)]

| channel | markets with data | % | first | last |
|---|---|---|---|---|
| trades | 40,708 | 76.5% | 2026-02-12 | 2026-07-06 |
| quotes | 41,734 | 78.4% | 2026-02-12 | 2026-07-06 |
| book_snapshot_25 | 41,734 | 78.4% | 2026-02-12 | 2026-07-06 |
| book_snapshot_full | 41,734 | 78.4% | 2026-02-12 | 2026-07-06 |
| onchain_fills | 41,490 | 77.9% | 2026-02-12 | 2026-07-06 |

## btc-updown-15m

- Markets: **25,913** (2025-10-09 16:45 → 2026-07-07 04:00 UTC)
- Slug timestamp modulo violations: 0 | duplicate timestamps: 0
- Status: {'active': '96', 'resolved': '25,817'}
- Resolved with result_id in {0,1}: 25,817 / 25,817
- Missing whole days inside range: 0
- Partial days (fewer windows than expected, excl. endpoints): 17 → first 10: [('2025-10-17', 78), ('2025-11-18', 94), ('2025-12-04', 94), ('2025-12-05', 95), ('2025-12-12', 95), ('2025-12-13', 93), ('2025-12-17', 94), ('2025-12-18', 94), ('2025-12-28', 95), ('2026-01-06', 94)]

| channel | markets with data | % | first | last |
|---|---|---|---|---|
| trades | 23,569 | 91.0% | 2025-10-11 | 2026-07-06 |
| quotes | 24,307 | 93.8% | 2025-10-11 | 2026-07-06 |
| book_snapshot_25 | 24,307 | 93.8% | 2025-10-11 | 2026-07-06 |
| book_snapshot_full | 24,307 | 93.8% | 2025-10-11 | 2026-07-06 |
| onchain_fills | 25,814 | 99.6% | 2025-10-09 | 2026-07-06 |

## btc-updown-4h

- Markets: **1,554** (2025-10-15 08:00 → 2026-07-07 04:00 UTC)
- Slug timestamp modulo violations: 720 | duplicate timestamps: 0
- Status: {'active': '7', 'resolved': '1,547'}
- Resolved with result_id in {0,1}: 1,547 / 1,547
- Missing whole days inside range: 5 → ['2025-11-03', '2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06']
- Partial days (fewer windows than expected, excl. endpoints): 7 → first 10: [('2025-11-02', 2), ('2025-11-04', 4), ('2025-12-04', 5), ('2025-12-17', 5), ('2026-01-02', 4), ('2026-01-09', 5), ('2026-01-19', 5)]

| channel | markets with data | % | first | last |
|---|---|---|---|---|
| trades | 1,518 | 97.7% | 2025-10-15 | 2026-07-06 |
| quotes | 1,542 | 99.2% | 2025-10-15 | 2026-07-06 |
| book_snapshot_25 | 1,542 | 99.2% | 2025-10-15 | 2026-07-06 |
| book_snapshot_full | 1,542 | 99.2% | 2025-10-15 | 2026-07-06 |
| onchain_fills | 1,548 | 99.6% | 2025-10-15 | 2026-07-06 |

## btc-up-or-down-15m (legacy)

- Markets: **2,547** (2025-09-13 00:45 → 2025-10-09 16:30 UTC)
- Slug timestamp modulo violations: 0 | duplicate timestamps: 0
- Status: {'resolved': '2,547'}
- Resolved with result_id in {0,1}: 2,547 / 2,547
- Missing whole days inside range: 0
- Partial days (fewer windows than expected, excl. endpoints): 1 → first 10: [('2025-10-03', 83)]

| channel | markets with data | % | first | last |
|---|---|---|---|---|
| trades | 0 | 0.0% | None | None |
| quotes | 0 | 0.0% | None | None |
| book_snapshot_25 | 0 | 0.0% | None | None |
| book_snapshot_full | 0 | 0.0% | None | None |
| onchain_fills | 2,525 | 99.1% | 2025-09-13 | 2025-10-10 |

## Hourly BTC up/down (`bitcoin-up-or-down-*-et`)

- Markets: **6,867** (window ends 2025-06-02 → 2026-04-06 UTC)
- Status: {'resolved': '6,867'}
- Channel presence: trades: 54%, quotes: 54%, book_snapshot_25: 54%

## Cross-timeframe note

- The hourly series (`bitcoin-up-or-down-*-et`, 6,867 markets) ENDED ~2026-04-06; there is
  no deterministic `btc-updown-1h` successor as of 2026-07-06 (verified against full
  markets dataset). Cross-timeframe features therefore use 15m + 4h for the full range,
  and hourly only where it exists (pre-April 2026).
- Effective tick-data ranges: 15m → 2025-10-11 onward (~9 months); 5m → 2026-02-12 onward
  (~5 months; listings gap 2026-01-27→02-11 predates tick coverage anyway); 4h → 2025-10-15.
- `crypto_prices` (Chainlink btcusd) only from 2026-04-02 → windows before that date get
  outcomes from `result_id` metadata; opens/closes reconstructable only after 2026-04-02.
