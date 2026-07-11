# nix2 live bot — the cheap+signal edge, deployable

Trades the one edge that survived the whole study: **buy a BTC 5-minute
up/down token when the order book has it *cheap* (44–50¢) AND a 1-second spot
move says that side just ticked its way, then hold to resolution.** The profit
is price leverage (win ~53% at a ~47¢ entry ≈ +9%/trade), not direction
skill. Full rule frozen in `../cheapsig.json`.

## Why Python (not Rust/C++)

The decision window is **0.5 seconds** and the hold is **5 minutes**. The
binding latency is the network round-trip to Polymarket (~50–200 ms), not
compute — so a faster language buys nothing. Python has the official
Polymarket client (`py-clob-client`), trivial exchange WebSockets, and matches
the validated research stack. Rust/C++ would be effort spent where there is no
bottleneck.

## The data it needs (all obtainable, mostly free)

| Leg | Source | Cost | Notes |
|---|---|---|---|
| Signal (1s spot return `g`, vol `sigma`) | Binance / Binance.US / Coinbase WS | free, public | `feeds.py`. Binance.com is geo-blocked in some regions → use `--venue binanceus` (same BTCUSDT, research-matched) or `coinbase`. |
| Order book (cheap-side ask + depth) | Polymarket CLOB `/book` | free, public | `pm.top_of_book` |
| Market schedule + token ids | Polymarket Gamma | free, public | `pm.find_btc_5m_market` (boundary is in the slug) |
| Order placement | Polymarket CLOB via `py-clob-client` | your funded wallet | LIVE mode only; needs `PM_PRIVATE_KEY` |

The signal is **pure spot** — it does NOT need a live Chainlink feed. (The
oracle lag is *why* the edge exists; the signal that exploits it is just a fast
spot return.)

## Run it

```bash
pip install -r requirements.txt

# PAPER (real data + real book, simulated fills). Start here — this IS the
# pre-registered forward test. No key needed.
python nix2_live.py --venue binanceus --stake 10 --account paper1

# Check the accumulating verdict any time:
python settle.py --account paper1

# LIVE (real orders). Needs a funded Polymarket account.
#   export PM_PRIVATE_KEY=...        # your wallet key — never printed/logged
#   export PM_API_KEY=... PM_API_SECRET=... PM_API_PASSPHRASE=...   # optional L2 creds
python nix2_live.py --venue binanceus --stake 5 --live --account wallet1
```

Every decision (trade or skip) is appended to `logs/nix2_live_<account>.jsonl`,
so the forward record builds itself.

## Scaling: your $5 × N accounts idea — the honest version

You asked about deploying several bots on several accounts at $5 each. That is
**the right way to scale here**, with one caveat:

- **It works for the minimum-order and per-account limits** — Polymarket's min
  order is **$5**, so each account can trade. Run N instances with different
  `--account` tags and keys.
- **But it does NOT multiply the underlying capacity.** The cap is *order-book
  depth*: a median of ~$27 rests at the cheap touch, and 5 accounts buying $5
  each still draw from that same $27. Total fillable size per window is
  ~$10–25 regardless of how many accounts you split it across (the extra
  accounts just walk deeper into the book at slightly worse prices).
- **Net:** multiple accounts help you (a) place the $5 minimums, (b) parallelise
  across the book, (c) spread wallet risk — but the real ceiling is ~$10–25 per
  window on 5m BTC. To deploy *more* capital you need more *markets* (other
  coins / timeframes), not more accounts on the same one. The bigger edge was
  always small-capacity; size accordingly.

Recommended sizing: **min(4% of bankroll, $15) per trade**, fixed fraction, and
**no win-doubling ladder** (it 4×'d the drawdown in backtest for a fragile
edge). ~7–8 trades/day; expect −$200-ish drawdowns.

## Honest status

The edge is the strongest, most stable, fill-verified result in the study
(daily t≈3 in-sample, positive train/val/fresh) but it was found after heavy
searching, so **run PAPER first** and let `settle.py` accumulate the
pre-registered verdict (positive, daily t≥2 over ≥20 trade-days on days after
2026-07-08). If it passes → go live small. If it fails → it was an in-sample
mirage; do not retune. Either way you'll know from real days, not a promise.
```
