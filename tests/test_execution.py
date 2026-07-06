"""GATE 0 unit tests: book-walk slippage and maker trade-through fills,
verified against hand-computed expected values on synthetic books/tapes."""
import sys

import numpy as np

sys.path.insert(0, "src")
from consolidate import _walk_curves
from execution import maker_fill_trade_through, walk_book

BOOK = [(0.50, 100.0), (0.52, 200.0), (0.55, 400.0)]
# hand math (levels cost $50, $104, $220; whole book = 700 sh for $374):
#   $50  -> exactly level 1: 100 sh @ avg 0.50
#   $200 -> 100 sh ($50) + 200 sh ($104) + $46/0.55 = 83.636364 sh
#           = 383.636364 sh, avg = 200/383.636364 = 0.52132701
#   $1000-> exceeds $374 book -> exhausted: 700 sh, avg 374/700 = 0.53428571
#   $5000-> same exhaustion: 700 sh, avg 0.53428571


def test_walk_book_hand_values():
    px, sh, ex = walk_book(BOOK, 50)
    assert abs(px - 0.50) < 1e-12 and abs(sh - 100) < 1e-9 and not ex
    px, sh, ex = walk_book(BOOK, 200)
    assert abs(sh - 383.63636364) < 1e-6 and abs(px - 0.52132701) < 1e-6 and not ex
    px, sh, ex = walk_book(BOOK, 1000)
    assert ex and abs(sh - 700) < 1e-9 and abs(px - 0.53428571) < 1e-6
    px, sh, ex = walk_book(BOOK, 5000)
    assert ex and abs(sh - 700) < 1e-9 and abs(px - 0.53428571) < 1e-6


def test_vectorized_walk_matches_reference():
    prices = np.array([[0.50, 0.52, 0.55], [0.30, np.nan, np.nan]])
    sizes = np.array([[100.0, 200.0, 400.0], [10.0, np.nan, np.nan]])
    out = _walk_curves(prices, sizes, notionals=(50.0, 200.0, 1000.0, 5000.0))
    for N in (50.0, 200.0, 1000.0, 5000.0):
        avg, sh, ex = out[N]
        ref_px, ref_sh, ref_ex = walk_book(BOOK, N)
        assert abs(avg[0] - ref_px) < 1e-4, (N, avg[0], ref_px)
        assert abs(sh[0] - ref_sh) < 0.05, (N, sh[0], ref_sh)
        assert bool(ex[0]) == ref_ex, (N, ex[0], ref_ex)
    # row 2: $3 book (10 sh @ 0.30); every notional >= $50 exhausts it
    for N in (50.0, 200.0):
        avg, sh, ex = out[N]
        assert bool(ex[1]) and abs(sh[1] - 10.0) < 1e-6 and abs(avg[1] - 0.30) < 1e-6


TAPE_TS = np.array([100, 200, 300, 400, 500], dtype=np.int64)
TAPE_PX = np.array([0.50, 0.49, 0.48, 0.50, 0.47])
TAPE_SZ = np.array([10.0, 20.0, 30.0, 50.0, 40.0])


def test_maker_buy_strictly_through_only():
    # BUY limit 0.49 placed at t=150, expiry 1000:
    #   eligible trades: t=200 @0.49 (AT limit -> NOT counted), t=300 @0.48 (30),
    #   t=400 @0.50 (no), t=500 @0.47 (40). Through-volume = 70.
    filled, ts = maker_fill_trade_through(0.49, "buy", 60, 150, TAPE_TS, TAPE_PX, TAPE_SZ, 1000)
    assert filled == 60 and ts == 500  # 30 at t=300 + 30 more of the 40 at t=500
    filled, ts = maker_fill_trade_through(0.49, "buy", 100, 150, TAPE_TS, TAPE_PX, TAPE_SZ, 1000)
    assert filled == 70 and ts is None  # partial, never completed


def test_maker_placement_and_expiry_bounds():
    # placed AT a trade's timestamp: that trade is excluded (searchsorted right)
    filled, _ = maker_fill_trade_through(0.49, "buy", 5, 300, TAPE_TS, TAPE_PX, TAPE_SZ, 1000)
    assert filled == 5  # only t=500 @0.47 counts, 40 >= 5
    # expiry before any through print
    filled, ts = maker_fill_trade_through(0.49, "buy", 5, 150, TAPE_TS, TAPE_PX, TAPE_SZ, 250)
    assert filled == 0 and ts is None


def test_maker_sell_side():
    # SELL limit 0.49 placed t=50: through prints are px>0.49: t=100 @0.50 (10),
    # t=400 @0.50 (50). 60 total.
    filled, ts = maker_fill_trade_through(0.49, "sell", 55, 50, TAPE_TS, TAPE_PX, TAPE_SZ, 1000)
    assert filled == 55 and ts == 400
    filled, ts = maker_fill_trade_through(0.49, "sell", 100, 50, TAPE_TS, TAPE_PX, TAPE_SZ, 1000)
    assert filled == 60 and ts is None
