"""
Module 2: HTF Momentum (RSI Divergence, + Double Bottom/Top confluence)
=========================================================================
Timeframes: Daily and Weekly only.

Base trigger (fires standalone): two consecutive price pivots where price
makes a new high/low that RSI doesn't confirm, AND the RSI line is actively
touching or crossing its own SMA at the confirming pivot.

Confluence tag (does NOT gate the base trigger -- it's an upgrade on top of
it): if the two price pivots are also roughly equal in price (a structural
double bottom/top, not just "any two lows"), the alert is tagged
'high_confluence' instead of 'standard'. You always get the base signal;
you additionally see when it's the stronger double-bottom/top version.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

import config
from pivots import find_swing_highs, find_swing_lows


def evaluate_module2(df: pd.DataFrame) -> pd.DataFrame:
    """
    df must already have rsi{period} and rsi{period}_sma columns
    (indicators.add_rsi). Returns df with:
      bearish_div / bullish_div          : bool, base divergence trigger
      module2_short_signal / _long_signal: bool, base trigger AND rsi/sma touch
      module2_short_confluence / _long_confluence : 'standard' | 'high_confluence'
    """
    df = df.copy()
    rsi_col = f"rsi{config.RSI_PERIOD}"
    rsi_sma_col = f"rsi{config.RSI_PERIOD}_sma"

    ph = find_swing_highs(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)
    pl = find_swing_lows(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)

    bearish_div = pd.Series(False, index=df.index)
    bullish_div = pd.Series(False, index=df.index)
    bearish_confluence = pd.Series("none", index=df.index)
    bullish_confluence = pd.Series("none", index=df.index)

    ph_idx = df.index[ph]
    for i in range(1, len(ph_idx)):
        cur, prev = ph_idx[i], ph_idx[i - 1]
        if (df.index.get_loc(cur) - df.index.get_loc(prev)) > config.DIVERGENCE_LOOKBACK_BARS:
            continue
        price_hh = df.loc[cur, "high"] > df.loc[prev, "high"]
        rsi_lh = df.loc[cur, rsi_col] < df.loc[prev, rsi_col]
        if price_hh and rsi_lh:
            bearish_div.loc[cur] = True
            # Double-top confluence: the two highs are roughly EQUAL rather than
            # just "any two highs" -- structurally distinct from plain divergence
            price_diff_pct = abs(df.loc[cur, "high"] - df.loc[prev, "high"]) / df.loc[prev, "high"]
            bearish_confluence.loc[cur] = (
                "high_confluence" if price_diff_pct <= config.DOUBLE_PATTERN_TOLERANCE_PCT
                else "standard"
            )

    pl_idx = df.index[pl]
    for i in range(1, len(pl_idx)):
        cur, prev = pl_idx[i], pl_idx[i - 1]
        if (df.index.get_loc(cur) - df.index.get_loc(prev)) > config.DIVERGENCE_LOOKBACK_BARS:
            continue
        price_ll = df.loc[cur, "low"] < df.loc[prev, "low"]
        rsi_hl = df.loc[cur, rsi_col] > df.loc[prev, rsi_col]
        if price_ll and rsi_hl:
            bullish_div.loc[cur] = True
            price_diff_pct = abs(df.loc[cur, "low"] - df.loc[prev, "low"]) / df.loc[prev, "low"]
            bullish_confluence.loc[cur] = (
                "high_confluence" if price_diff_pct <= config.DOUBLE_PATTERN_TOLERANCE_PCT
                else "standard"
            )

    df["bearish_div"] = bearish_div
    df["bullish_div"] = bullish_div
    df["module2_short_confluence"] = bearish_confluence
    df["module2_long_confluence"] = bullish_confluence

    # RSI/SMA touch filter -- this is what turns raw divergence into an actual signal
    rsi_touching_sma = (df[rsi_col] - df[rsi_sma_col]).abs() <= config.RSI_SMA_TOUCH_TOLERANCE
    rsi_crossing_sma = (
        (df[rsi_col] - df[rsi_sma_col]) * (df[rsi_col] - df[rsi_sma_col]).shift(1)
    ) < 0
    rsi_trigger = rsi_touching_sma | rsi_crossing_sma

    df["module2_short_signal"] = df["bearish_div"] & rsi_trigger
    df["module2_long_signal"] = df["bullish_div"] & rsi_trigger

    return df
