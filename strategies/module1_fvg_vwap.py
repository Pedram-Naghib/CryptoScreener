"""
Module 1: Liquidity & Mean Reversion (FVG + VWAP convergence)
================================================================
Timeframes: 1H (Daily VWAP) and 4H (Weekly VWAP).

Trigger: price pulls back into a fresh, volume-confirmed FVG WHILE that
zone is also aligning with the relevant anchored VWAP -- either:
  (a) price is within FVG_PROXIMITY_PCT of entering the gap, OR
  (b) price has wicked into the outer FVG_WICK_ENTRY_PCT of the gap,
  AND
  (c) the gap (or current price) sits within FVG_VWAP_TOLERANCE_PCT of VWAP.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

import config
from fvg import detect_fvgs, get_active_fvgs


VWAP_COL_BY_TF = {
    config.TF_1H: "vwap_daily",
    config.TF_4H: "vwap_weekly",
}


def _gap_midpoint(row) -> float:
    return (row["fvg_top"] + row["fvg_bottom"]) / 2


def evaluate_module1(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    df must already have the standard indicator stack (indicators.build_indicator_stack)
    with the correct VWAP anchor for this timeframe already applied.

    Returns df with 'module1_long_signal' / 'module1_short_signal' bool columns,
    plus 'module1_target_fvg_mid' for reference (used loosely by tp_logic too).
    """
    df = detect_fvgs(df)
    vwap_col = VWAP_COL_BY_TF.get(timeframe)
    if vwap_col is None or vwap_col not in df.columns:
        raise ValueError(f"Missing VWAP column '{vwap_col}' for timeframe {timeframe}")

    n = len(df)
    long_signal = np.zeros(n, dtype=bool)
    short_signal = np.zeros(n, dtype=bool)

    close = df["close"].values
    low = df["low"].values
    high = df["high"].values
    vwap = df[vwap_col].values

    for i in range(n):
        row = df.iloc[i]
        if not (row["bullish_fvg"] or row["bearish_fvg"]) or row["fvg_mitigated"]:
            continue

        top, bottom = row["fvg_top"], row["fvg_bottom"]
        if np.isnan(top) or np.isnan(bottom):
            continue
        gap_size = top - bottom
        mid = (top + bottom) / 2

        # Look forward from formation bar to see if/when price re-approaches the gap
        # (in a live system this would just be "the current bar"; here we scan
        # forward for backtest purposes)
        for j in range(i, min(i + config.TP_SEARCH_MAX_BARS_BACK, n)):
            price_close = close[j]
            price_low = low[j]
            price_high = high[j]
            vwap_j = vwap[j]
            if np.isnan(vwap_j):
                continue

            near_vwap = abs(price_close - vwap_j) / vwap_j <= config.FVG_VWAP_TOLERANCE_PCT

            if row["bullish_fvg"]:
                proximity_hit = abs(price_close - bottom) / bottom <= config.FVG_PROXIMITY_PCT
                wick_hit = price_low <= bottom + gap_size * config.FVG_WICK_ENTRY_PCT
                if (proximity_hit or wick_hit) and near_vwap:
                    long_signal[j] = True
                    break

            if row["bearish_fvg"]:
                proximity_hit = abs(price_close - top) / top <= config.FVG_PROXIMITY_PCT
                wick_hit = price_high >= top - gap_size * config.FVG_WICK_ENTRY_PCT
                if (proximity_hit or wick_hit) and near_vwap:
                    short_signal[j] = True
                    break

    df["module1_long_signal"] = long_signal
    df["module1_short_signal"] = short_signal
    return df
