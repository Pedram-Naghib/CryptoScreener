"""
Strategy: HTF RSI Divergence (Regular + Hidden)
==================================================
Timeframes: Daily, Weekly.

Evaluates BOTH regular and hidden divergence, but they are mathematically
mutually exclusive on any single swing leg:
  Regular (reversal):    price makes a Lower Low or Equal Low, RSI makes a
                          Higher Low  -> bullish reversal (long)
                          [mirror on highs for bearish reversal / short]
  Hidden (continuation): price makes a Higher Low, RSI makes a Lower Low
                          -> bullish continuation (long)
                          [mirror on highs for bearish continuation / short]

"Lower/equal" vs "Higher" for price are opposite conditions on the same
pivot pair, so regular and hidden can never both fire for the same pair --
the module structurally can't award more than its configured weight per
direction. Pivot detection uses scipy's vectorized argrelextrema rather
than a per-bar Python loop; the only iteration is over the small list of
detected pivots (typically a few dozen), not over every candle.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from scipy.signal import argrelextrema

import config
from strategies.base import Strategy, StrategyResult, DirectionResult


def _pivot_indices(series: np.ndarray, order: int, mode: str) -> np.ndarray:
    comparator = np.less_equal if mode == "min" else np.greater_equal
    return argrelextrema(series, comparator, order=order)[0]


def _classify_low_pair(price_prev, price_cur, rsi_prev, rsi_cur):
    price_diff_pct = (price_cur - price_prev) / price_prev
    if price_diff_pct <= config.DOUBLE_PATTERN_TOLERANCE_PCT and rsi_cur > rsi_prev:
        return "regular_bullish"   # price LL/equal-low, RSI HL -> reversal long
    if price_diff_pct > config.DOUBLE_PATTERN_TOLERANCE_PCT and rsi_cur < rsi_prev:
        return "hidden_bullish"    # price HL, RSI LL -> continuation long
    return None


def _classify_high_pair(price_prev, price_cur, rsi_prev, rsi_cur):
    price_diff_pct = (price_cur - price_prev) / price_prev
    if price_diff_pct >= -config.DOUBLE_PATTERN_TOLERANCE_PCT and rsi_cur < rsi_prev:
        return "regular_bearish"   # price HH/equal-high, RSI LH -> reversal short
    if price_diff_pct < -config.DOUBLE_PATTERN_TOLERANCE_PCT and rsi_cur > rsi_prev:
        return "hidden_bearish"    # price LH, RSI HH -> continuation short
    return None


def _rsi_sma_confirms(rsi: np.ndarray, rsi_sma: np.ndarray, pivot_idx: int, tolerance: float) -> bool:
    """
    Module 2's 'RSI actively touching or crossing its SMA' trigger. Checked
    over the whole window from the confirming pivot bar through the current
    bar (not just the current bar alone) so we still catch it if the touch/
    cross happens a bar or two after the divergence pivot rather than on the
    exact same bar.
    """
    end = len(rsi) - 1
    if pivot_idx > end:
        return False

    window_rsi = rsi[pivot_idx: end + 1]
    window_sma = rsi_sma[pivot_idx: end + 1]
    diff = window_rsi - window_sma
    diff = diff[~np.isnan(diff)]
    if diff.size == 0:
        return False

    touching_now = abs(diff[-1]) <= tolerance
    if touching_now:
        return True

    signs = np.sign(diff)
    signs = signs[signs != 0]
    return bool(signs.size >= 2 and np.any(signs[:-1] != signs[1:]))


class HTFRSIDivergence(Strategy):
    name = "htf_rsi_divergence"
    required_timeframes = [config.TF_1D, config.TF_1W]

    def evaluate(self, data):
        long_matches = []
        short_matches = []
        rsi_col = f"rsi{config.RSI_PERIOD}"

        rsi_sma_col = f"{rsi_col}_sma"

        for tf, df in data.items():
            if len(df) < config.DIVERGENCE_LOOKBACK_BARS + 10:
                continue

            low = df["low"].values
            high = df["high"].values
            rsi = df[rsi_col].values
            rsi_sma = df[rsi_sma_col].values if rsi_sma_col in df.columns else np.full(len(df), np.nan)
            order = config.HTF_PIVOT_WINDOW

            low_pivots = _pivot_indices(low, order, "min")
            high_pivots = _pivot_indices(high, order, "max")

            bullish_tag = None
            for i in range(1, len(low_pivots)):
                cur, prev = low_pivots[i], low_pivots[i - 1]
                if cur - prev > config.DIVERGENCE_LOOKBACK_BARS:
                    continue
                if np.isnan(rsi[cur]) or np.isnan(rsi[prev]):
                    continue
                tag = _classify_low_pair(low[prev], low[cur], rsi[prev], rsi[cur])
                if tag:
                    bullish_tag = tag  # keep most recent match

            bearish_tag = None
            for i in range(1, len(high_pivots)):
                cur, prev = high_pivots[i], high_pivots[i - 1]
                if cur - prev > config.DIVERGENCE_LOOKBACK_BARS:
                    continue
                if np.isnan(rsi[cur]) or np.isnan(rsi[prev]):
                    continue
                tag = _classify_high_pair(high[prev], high[cur], rsi[prev], rsi[cur])
                if tag:
                    bearish_tag = tag

            # only score if the confirming pivot is still "current" AND RSI is
            # actively touching/crossing its own SMA (Module 2's timing filter)
            # -- otherwise we'd be alerting on stale structure from earlier in
            # the window, or on a divergence with no live momentum trigger yet.
            if (
                bullish_tag
                and len(low_pivots)
                and (len(df) - 1 - low_pivots[-1]) <= config.DIVERGENCE_LOOKBACK_BARS
                and _rsi_sma_confirms(rsi, rsi_sma, low_pivots[-1], config.RSI_SMA_TOUCH_TOLERANCE)
            ):
                long_matches.append((tf, {"type": bullish_tag}))
            if (
                bearish_tag
                and len(high_pivots)
                and (len(df) - 1 - high_pivots[-1]) <= config.DIVERGENCE_LOOKBACK_BARS
                and _rsi_sma_confirms(rsi, rsi_sma, high_pivots[-1], config.RSI_SMA_TOUCH_TOLERANCE)
            ):
                short_matches.append((tf, {"type": bearish_tag}))

        return StrategyResult(
            long=self.merge_matches(long_matches),
            short=self.merge_matches(short_matches),
        )