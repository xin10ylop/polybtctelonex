"""Fast spot-price feed for the nix2 bot — the SIGNAL leg.

The edge's signal g is a 1-second spot return (validated on Binance BTCUSDT).
Binance.com is geo-blocked in some regions, so the feed is pluggable:
  - "binance"    wss://stream.binance.com:9443/ws/btcusdt@aggTrade   (research match)
  - "binanceus"  wss://stream.binance.us:9443/ws/btcusdt@aggTrade    (US, same symbol)
  - "coinbase"   wss://ws-feed.exchange.coinbase.com  BTC-USD matches (fallback)

The feed keeps a rolling window of (ts_us, price) and answers two questions the
strategy needs at decision time T0:
  price_at(t)      last trade price at/just before t (for the 1s return g)
  sigma_1s(T0)     std of 1s-grid log returns over the prior 300s (vol scaler)
"""
from __future__ import annotations

import asyncio
import bisect
import json
import math
import time

import websockets

FEEDS = {
    "binance": ("wss://stream.binance.com:9443/ws/btcusdt@aggTrade", "binance"),
    "binanceus": ("wss://stream.binance.us:9443/ws/btcusdt@aggTrade", "binance"),
    "coinbase": ("wss://ws-feed.exchange.coinbase.com", "coinbase"),
}


class SpotFeed:
    def __init__(self, venue: str = "binanceus", keep_s: int = 400):
        if venue not in FEEDS:
            raise ValueError(f"venue {venue} not in {list(FEEDS)}")
        self.url, self.kind = FEEDS[venue]
        self.venue = venue
        self.keep_us = keep_s * 1_000_000
        self.ts: list[int] = []      # sorted trade timestamps (us)
        self.px: list[float] = []
        self._last = 0.0

    async def run(self) -> None:
        """Maintain the rolling trade buffer forever (reconnects on drop)."""
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=15) as ws:
                    if self.kind == "coinbase":
                        await ws.send(json.dumps({"type": "subscribe",
                            "product_ids": ["BTC-USD"], "channels": ["ticker"]}))
                    async for raw in ws:
                        m = json.loads(raw)
                        p = self._parse(m)
                        if p is None:
                            continue
                        now = int(time.time() * 1_000_000)
                        self.ts.append(now); self.px.append(p); self._last = p
                        cut = now - self.keep_us
                        while self.ts and self.ts[0] < cut:
                            self.ts.pop(0); self.px.pop(0)
            except Exception as e:  # reconnect on any drop
                print(f"[feed] reconnect after: {e}")
                await asyncio.sleep(1.0)

    def _parse(self, m: dict) -> float | None:
        if self.kind == "binance":
            return float(m["p"]) if "p" in m else None
        if m.get("type") == "ticker" and "price" in m:
            return float(m["price"])
        return None

    def ready(self) -> bool:
        return len(self.ts) > 50 and (self.ts[-1] - self.ts[0]) > 305_000_000

    def price_at(self, t_us: int) -> float | None:
        i = bisect.bisect_right(self.ts, t_us) - 1
        return self.px[i] if i >= 0 else None

    def sigma_1s_scaled(self, T0_us: int, dur_s: int = 300) -> float | None:
        """std of 1s-grid log returns over prior 300s, * sqrt(dur) * 1e4 — the
        exact volatility scaler used in research (nix_scalp6)."""
        base = T0_us - 5_000_000  # measured at T0-5s, like research
        grid = [base - k * 1_000_000 for k in range(300, -1, -1)]
        logs = []
        for g in grid:
            p = self.price_at(g)
            logs.append(math.log(p) if p and p > 0 else None)
        rets = [logs[i] - logs[i - 1] for i in range(1, len(logs))
                if logs[i] is not None and logs[i - 1] is not None]
        if len(rets) < 30:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var) * math.sqrt(dur_s) * 1e4

    def signal(self, T0_us: int, blat_us: int = 150_000) -> tuple[float, float] | None:
        """Returns (g_bp, z) at decision time T0, or None if not enough data.
        g = 1e4 * ln( price(T0-150ms) / price(T0-1.15s) ); z = g / sigma."""
        p_now = self.price_at(T0_us - blat_us)
        p_1s = self.price_at(T0_us - blat_us - 1_000_000)
        sig = self.sigma_1s_scaled(T0_us)
        if not (p_now and p_1s and sig and sig > 0):
            return None
        g = math.log(p_now / p_1s) * 1e4
        return g, g / sig
