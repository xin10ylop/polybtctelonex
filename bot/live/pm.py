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


def find_btc_5m_market(target_open_us: int | None = None) -> dict | None:
    """Return {open_ts_us, up_token, down_token, min_size, tick, slug} for the
    BTC 5m up/down market whose boundary matches target_open_us (slug encodes
    the unix boundary: btc-updown-5m-<unix>). If target is None, the nearest
    future one. None if not found."""
    data = _get(f"{GAMMA}/markets?closed=false&limit=500&order=startDate&ascending=false")
    tgt = None if target_open_us is None else target_open_us // 1_000_000
    best = None
    for m in data:
        slug = (m.get("slug") or "").lower()
        if not slug.startswith("btc-updown-5m-"):
            continue
        try:
            boundary = int(slug.rsplit("-", 1)[1])
        except ValueError:
            continue
        toks = m.get("clobTokenIds")
        if isinstance(toks, str):
            toks = json.loads(toks)
        if not toks or len(toks) != 2:
            continue
        cand = {
            "slug": m.get("slug"),
            "open_ts_us": boundary * 1_000_000,
            "up_token": toks[0],
            "down_token": toks[1],
            "min_size": float(m.get("orderMinSize") or 5),
            "tick": float(m.get("orderPriceMinTickSize") or 0.01),
        }
        if tgt is None:
            if best is None or boundary < best[0]:
                best = (boundary, cand)
        elif boundary == tgt:
            return cand
    return best[1] if best else None


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
