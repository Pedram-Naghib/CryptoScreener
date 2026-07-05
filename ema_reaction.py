"""
EMA Reaction (TP / Exit Watch Signal)
========================================
From your chart: EMA50 rejected price multiple times historically, price
returns to EMA50 again, RSI climbs to the mid-lane (~45-60) and turns back
down at the same time. This is a dynamic exit/TP cue, not a fixed price
level like an FVG -- so it's surfaced as a "watch this zone" alert rather
than a fixed target price.

Two objective ingredients, both rigid:
  1. Historical validation: has this EMA actually acted as support/resistance
     multiple times recently? (counted, not eyeballed)
  2. Current reaction: is price at the EMA right now, AND is RSI sitting in
     the mid-lane and turning away from it?
"""

import pandas as pd
import numpy as np
import config


def count_prior_rejections(df: pd.DataFrame, ema_col: str = config.EMA_REACTION_EMA) -> int:
    """
    Counts how many times, in the last EMA_REJECTION_LOOKBACK_BARS bars, price
    touched the EMA (within EMA_PROXIMITY_PCT) and then moved away by at least
    EMA_REJECTION_MOVE_PCT within EMA_REJECTION_CONFIRM_BARS -- i.e. an actual
    rejection, not just a crossover.
    """
    recent = df.iloc[-config.EMA_REJECTION_LOOKBACK_BARS:]
    close = recent["close"].values
    ema = recent[ema_col].values
    n = len(recent)
    rejections = 0

    for i in range(n - config.EMA_REJECTION_CONFIRM_BARS):
        if np.isnan(ema[i]):
            continue
        touched = abs(close[i] - ema[i]) / ema[i] <= config.EMA_PROXIMITY_PCT
        if not touched:
            continue
        future = close[i: i + config.EMA_REJECTION_CONFIRM_BARS + 1]
        move_pct = (future.max() - future.min()) / ema[i]
        # confirm it actually moved away (either direction) rather than chopping at the line
        if move_pct >= config.EMA_REJECTION_MOVE_PCT:
            rejections += 1

    return rejections


def evaluate_ema_reaction(df: pd.DataFrame) -> dict:
    """
    Checks the LAST bar for a live EMA reaction setup. Returns a dict describing
    whether it's currently valid -- meant to be called on the same df you're
    already scanning for other modules (needs EMAs + RSI already computed).
    """
    ema_col = config.EMA_REACTION_EMA
    rsi_col = f"rsi{config.RSI_PERIOD}"

    if ema_col not in df.columns or rsi_col not in df.columns:
        raise ValueError(f"df missing required columns: {ema_col}, {rsi_col}")

    if len(df) < config.EMA_REJECTION_LOOKBACK_BARS:
        return {"active": False, "reason": "not enough history"}

    prior_rejections = count_prior_rejections(df, ema_col)
    if prior_rejections < config.EMA_MIN_PRIOR_REJECTIONS:
        return {"active": False, "reason": f"only {prior_rejections} prior rejections at {ema_col}"}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price_at_ema = abs(last["close"] - last[ema_col]) / last[ema_col] <= config.EMA_PROXIMITY_PCT
    rsi_in_midlane = config.RSI_MIDLANE_LOW <= last[rsi_col] <= config.RSI_MIDLANE_HIGH
    rsi_turning_down = last[rsi_col] < prev[rsi_col]
    rsi_turning_up = last[rsi_col] > prev[rsi_col]

    if not price_at_ema or not rsi_in_midlane:
        return {"active": False, "reason": "price not at EMA or RSI not in mid-lane"}

    if rsi_turning_down:
        return {
            "active": True,
            "direction": "bearish_rejection",
            "ema": ema_col,
            "price": float(last["close"]),
            "rsi": float(last[rsi_col]),
            "prior_rejections": prior_rejections,
        }
    if rsi_turning_up:
        return {
            "active": True,
            "direction": "bullish_rejection",
            "ema": ema_col,
            "price": float(last["close"]),
            "rsi": float(last[rsi_col]),
            "prior_rejections": prior_rejections,
        }

    return {"active": False, "reason": "RSI flat, no clear turn yet"}