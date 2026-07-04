"""
Strategy: Deep Discount FVG
=============================
Timeframes: 1H, 4H.

Fresh (unmitigated) FVG, expansion candle volume >= 1.5x the 20-period volume
MA, whose GEOMETRIC CENTER falls inside the 0.706-0.790 Fibonacci retracement
zone (Optimal Trade Entry) of the current major swing leg. Legs are filtered
by an ATR multiplier so choppy/ranging noise doesn't get treated as a valid
swing (a real leg should be a multiple of the current ATR, not just noise).
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config
from pivots import find_swing_highs, find_swing_lows
from fvg import detect_fvgs, get_active_fvgs
from strategies.base import Strategy, StrategyResult, DirectionResult


def _get_last_valid_leg(df: pd.DataFrame):
    """Most recent swing leg, filtered to require leg size >= MIN_LEG_ATR_MULT * ATR."""
    recent = df.iloc[-config.FIB_SWING_LOOKBACK_BARS:]
    ph = find_swing_highs(recent, config.PIVOT_LEFT, config.PIVOT_RIGHT)
    pl = find_swing_lows(recent, config.PIVOT_LEFT, config.PIVOT_RIGHT)

    high_idx_list = recent.index[ph]
    low_idx_list = recent.index[pl]
    if len(high_idx_list) == 0 or len(low_idx_list) == 0:
        return None

    last_high_idx = high_idx_list[-1]
    last_low_idx = low_idx_list[-1]
    high_price = recent.loc[last_high_idx, "high"]
    low_price = recent.loc[last_low_idx, "low"]

    leg_size = high_price - low_price
    atr_col = f"atr{config.ATR_PERIOD}"
    current_atr = recent[atr_col].iloc[-1]
    if pd.isna(current_atr) or current_atr == 0 or leg_size < config.MIN_LEG_ATR_MULT * current_atr:
        return None  # too choppy to trust this leg

    direction = "uptrend" if last_high_idx > last_low_idx else "downtrend"
    return direction, high_price, low_price


def _compute_ote_zone(direction: str, high_price: float, low_price: float):
    leg = high_price - low_price
    lo, hi = config.OTE_ZONE_LEVELS  # (0.706, 0.790)
    if direction == "uptrend":
        zone_top = high_price - leg * lo
        zone_bottom = high_price - leg * hi
    else:
        zone_bottom = low_price + leg * lo
        zone_top = low_price + leg * hi
    return zone_bottom, zone_top


class DeepDiscountFVG(Strategy):
    name = "deep_discount_fvg"
    required_timeframes = [config.TF_1H, config.TF_4H]

    def evaluate(self, data):
        result = StrategyResult()

        for tf, df in data.items():
            if len(df) < config.FIB_SWING_LOOKBACK_BARS:
                continue

            df = detect_fvgs(df.copy())
            leg = _get_last_valid_leg(df)
            if leg is None:
                continue
            direction, high_price, low_price = leg
            zone_bottom, zone_top = _compute_ote_zone(direction, high_price, low_price)

            active = get_active_fvgs(df)
            if active.empty:
                continue

            wanted_col = "bullish_fvg" if direction == "uptrend" else "bearish_fvg"
            centers = (active["fvg_top"] + active["fvg_bottom"]) / 2
            mask = active[wanted_col] & (centers >= zone_bottom) & (centers <= zone_top)
            matches = active[mask]

            if matches.empty:
                continue

            details = {
                "tf": tf,
                "ote_zone": f"{zone_bottom:.6f}-{zone_top:.6f}",
                "fvg_count": int(len(matches)),
            }
            if direction == "uptrend":
                result.long = DirectionResult(score=self.weight, details=details)
            else:
                result.short = DirectionResult(score=self.weight, details=details)

        return result