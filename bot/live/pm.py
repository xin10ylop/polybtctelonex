"""Polymarket leg of the nix2 bot — discovery, order book, execution.

Discovery (free, public):   gamma-api.polymarket.com -> the current BTC 5m
  up/down market, its open (boundary) time, and the Up/Down clob token ids.
Order book (free, public):  clob.polymarket.com/book?token_id=...
Execution (needs the user's own key): py-clob-client posts a marketable limit
  ("taker") order. In PAPER mode we never place — we record the book ask as the
  fill and settle against the on-chain resolution.

Only the user's PM_PRIVATE_KEY (read from env, NEVER logged) can place live
orders. Paper mode needs no key.
"""
from __future__ import annotations

import json
import ssl
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
_CTX = ssl.create_default_context()


def _get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "nix2-bot/1.0"})
    with urllib.request.urlopen(req, timeout=10, context=_CTX) as r:
        return json.load(r)


def _parse_market(m: dict) -> dict | None:
    slug = m.get("slug") or ""
    try:
        boundary = int(slug.rsplit("-", 1)[1])
    except (ValueError, IndexError):
        return None
    toks = m.get("clobTokenIds")
    if isinstance(toks, str):
        toks = json.loads(toks)
    if not toks or len(toks) != 2:
        return None
    return {
        "slug": slug,
        "open_ts_us": boundary * 1_000_000,
        "up_token": toks[0],
        "down_token": toks[1],
        "min_size": float(m.get("orderMinSize") or 5),
        "tick": float(m.get("orderPriceMinTickSize") or 0.01),
        "accepting": bool(m.get("acceptingOrders", True)),
    }


def find_btc_5m_market(target_open_us: int | None = None) -> dict | None:
    """Return the BTC 5m up/down market for `target_open_us`, fetched by EXACT
    slug (btc-updown-5m-<unix_open>). Polymarket pre-creates ~a day of these, so
    a list+filter query silently drops the near-term window past its 500 limit;
    a direct slug lookup is deterministic. If target is None, fall back to the
    nearest future one via the list query."""
    if target_open_us is not None:
        b = target_open_us // 1_000_000
        for cand_b in (b, b + 300, b - 300):   # small fallback for boundary drift
            try:
                r = _get(f"{GAMMA}/markets?slug=btc-updown-5m-{cand_b}")
            except Exception:
                continue
            if r:
                pm = _parse_market(r[0])
                if pm:
                    return pm
        return None
    # target None: nearest upcoming from the ascending list
    data = _get(f"{GAMMA}/markets?closed=false&limit=500&order=endDate&ascending=true")
    for m in data:
        if (m.get("slug") or "").startswith("btc-updown-5m-"):
            pm = _parse_market(m)
            if pm:
                return pm
    return None


def top_of_book(token_id: str) -> tuple[float, float] | None:
    """(best_ask_price, ask_size_usd) for a token, from the public CLOB book."""
    try:
        b = _get(f"{CLOB}/book?token_id={token_id}")
    except Exception:
        return None
    asks = b.get("asks") or []
    if not asks:
        return None
    # CLOB returns asks ascending? normalize: best ask = min price
    best = min(asks, key=lambda a: float(a["price"]))
    px = float(best["price"]); sz = float(best["size"])
    return px, px * sz  # (price, $ resting at touch)


class Executor:
    """Live order placement via py-clob-client; no-op stub in paper mode."""

    def __init__(self, paper: bool = True, private_key: str | None = None,
                 api_creds: dict | None = None):
        self.paper = paper
        self._client = None
        if not paper:
            from py_clob_client.client import ClobClient  # live-only import
            from py_clob_client.clob_types import ApiCreds
            self._client = ClobClient(
                CLOB, key=private_key, chain_id=137,
                creds=ApiCreds(**api_creds) if api_creds else None)

    def buy(self, token_id: str, price: float, usd: float, tick: float) -> dict:
        """Marketable limit buy of ~$usd notional at `price` (taker). Returns a
        fill record. Paper mode returns the intended fill without touching the
        chain."""
        px = round(price / tick) * tick
        shares = round(usd / px, 2)
        if self.paper or self._client is None:
            return {"paper": True, "token": token_id, "price": px, "shares": shares}
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
        order = self._client.create_order(OrderArgs(
            token_id=token_id, price=px, size=shares, side=BUY))
        resp = self._client.post_order(order, OrderType.FOK)  # fill-or-kill taker
        return {"paper": False, "resp": resp, "price": px, "shares": shares}
