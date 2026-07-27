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
    s = book_summary(token_id)
    return (s["ask"], s["ask_usd"]) if s else None


def book_summary(token_id: str) -> dict | None:
    """Both sides of a token's ToB: {ask, ask_usd, bid, bid_usd, q_imb}.
    q_imb = (bid$ - ask$)/(bid$ + ask$) at the touch — negative means the book
    leans AWAY from this token (more sellers resting), the research's
    mispricing fingerprint (v2 gate: q_imb < -0.05)."""
    try:
        b = _get(f"{CLOB}/book?token_id={token_id}")
    except Exception:
        return None
    asks = b.get("asks") or []
    bids = b.get("bids") or []
    if not asks:
        return None
    ba = min(asks, key=lambda a: float(a["price"]))
    ask = float(ba["price"]); ask_usd = ask * float(ba["size"])
    if bids:
        bb = max(bids, key=lambda a: float(a["price"]))
        bid = float(bb["price"]); bid_usd = bid * float(bb["size"])
    else:
        bid, bid_usd = None, 0.0
    tot = bid_usd + ask_usd
    q = (bid_usd - ask_usd) / tot if tot > 0 else None
    return {"ask": ask, "ask_usd": ask_usd, "bid": bid, "bid_usd": bid_usd,
            "q_imb": round(q, 4) if q is not None else None,
            "_asks": [(float(a["price"]), float(a["size"])) for a in asks]}


def walk_price(asks: list[tuple[float, float]], usd: float,
               limit_px: float | None = None) -> tuple[float, float]:
    """Average price to buy `usd` of notional by walking the ask ladder.

    With `limit_px` this simulates a marketable LIMIT order: levels priced
    above the limit are not taken, so the result can be a PARTIAL fill (or
    none) — exactly what a fill-or-kill/IOC order does when the book moves
    away between the decision and the order's arrival.

    Returns (avg_price, usd_filled); avg_price is NaN when nothing fills.
    The fill audit measured walking costs ~0.4c median vs the touch, and
    keeps ~100% of signal windows tradeable vs the 74% that skip-if-thin
    allows — which is what lets stakes above ~$10 scale.
    """
    spent = shares = 0.0
    for px, sz in sorted(asks, key=lambda a: a[0]):
        if limit_px is not None and px > limit_px + 1e-9:
            break
        if spent >= usd - 1e-9:
            break
        take = min(px * sz, usd - spent)
        shares += take / px
        spent += take
    if shares <= 0:
        return float("nan"), 0.0
    return spent / shares, spent


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
