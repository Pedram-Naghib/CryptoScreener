"""
Take-Profit Logic
==================
Per the "price is a magnet to inefficiency" idea from your Gemini chat:
target the nearest UNMITIGATED FVG in the trade's direction rather than a
geometric measured move (which we can't code anyway -- wedges are excluded).

Fallback: if no unmitigated FVG exists further out in that direction, target
the most recent swept liquidity level (the swing high/low Module 3 already
computes) instead of leaving TP undefined.
"""

import pandas as pd
import numpy as np

import config
from fvg import get_active_fvgs


def suggest_tp(df: pd.DataFrame, direction: str) -> dict:
    """
    direction: 'long' or 'short'
    Returns: {
        'target_price': float | None,
        'target_type': 'fvg' | 'swept_liquidity' | None,
        'target_index': timestamp | None,
    }
    Call this with the SAME df a signal fired on (already run through
    fvg.detect_fvgs and, ideally, module3's swing_high/swing_low columns).
    """
    if "bullish_fvg" not in df.columns or "bearish_fvg" not in df.columns:
        raise ValueError("df must have FVGs detected first (fvg.detect_fvgs)")

    current_price = df["close"].iloc[-1]
    active = get_active_fvgs(df)

    if direction == "long":
        # target a bullish FVG (price magnet above current price) further up
        candidates = active[active["bullish_fvg"] & (active["fvg_bottom"] > current_price)]
        if not candidates.empty:
            # nearest = smallest distance from current price
            candidates = candidates.copy()
            candidates["dist"] = candidates["fvg_bottom"] - current_price
            nearest = candidates.sort_values("dist").iloc[0]
            return {
                "target_price": float(nearest["fvg_bottom"]),
                "target_type": "fvg",
                "target_index": nearest.name,
            }
        # fallback: most recent swept liquidity level above price, if available
        if "swing_high" in df.columns:
            highs_above = df[df["swing_high"] & (df["high"] > current_price)]
            if not highs_above.empty:
                nearest = highs_above.iloc[-1]
                return {
                    "target_price": float(nearest["high"]),
                    "target_type": "swept_liquidity",
                    "target_index": nearest.name,
                }

    elif direction == "short":
        candidates = active[active["bearish_fvg"] & (active["fvg_top"] < current_price)]
        if not candidates.empty:
            candidates = candidates.copy()
            candidates["dist"] = current_price - candidates["fvg_top"]
            nearest = candidates.sort_values("dist").iloc[0]
            return {
                "target_price": float(nearest["fvg_top"]),
                "target_type": "fvg",
                "target_index": nearest.name,
            }
        if "swing_low" in df.columns:
            lows_below = df[df["swing_low"] & (df["low"] < current_price)]
            if not lows_below.empty:
                nearest = lows_below.iloc[-1]
                return {
                    "target_price": float(nearest["low"]),
                    "target_type": "swept_liquidity",
                    "target_index": nearest.name,
                }
    else:
        raise ValueError("direction must be 'long' or 'short'")

    return {"target_price": None, "target_type": None, "target_index": None}


def suggest_sl(df: pd.DataFrame, direction: str, atr_col: str) -> dict:
    """
    Structural stop-loss: the nearest swing low/high beyond entry (the level
    that, if it breaks, invalidates the setup), pushed out by a small ATR
    buffer so ordinary wick noise doesn't stop the trade out exactly at the
    structural level. Falls back to a pure ATR-multiple stop if no structural
    swing exists yet on this leg (e.g. right after a fresh breakout).

    Call this on the SAME df already used for suggest_tp (needs swing_high/
    swing_low and the ATR column already computed).

    Returns: {'sl_price': float | None, 'sl_type': 'structure' | 'atr_fallback' | None}
    """
    current_price = df["close"].iloc[-1]
    atr = df[atr_col].iloc[-1] if atr_col in df.columns else np.nan
    atr_valid = not np.isnan(atr)

    if direction == "long":
        if "swing_low" in df.columns:
            lows_below = df[df["swing_low"] & (df["low"] < current_price)]
            if not lows_below.empty:
                structural = float(lows_below["low"].iloc[-1])
                buffer = atr * config.SL_STRUCTURE_BUFFER_ATR_MULT if atr_valid else structural * 0.002
                return {"sl_price": structural - buffer, "sl_type": "structure"}
        if atr_valid:
            return {"sl_price": float(current_price - atr * config.SL_FALLBACK_ATR_MULT), "sl_type": "atr_fallback"}

    elif direction == "short":
        if "swing_high" in df.columns:
            highs_above = df[df["swing_high"] & (df["high"] > current_price)]
            if not highs_above.empty:
                structural = float(highs_above["high"].iloc[-1])
                buffer = atr * config.SL_STRUCTURE_BUFFER_ATR_MULT if atr_valid else structural * 0.002
                return {"sl_price": structural + buffer, "sl_type": "structure"}
        if atr_valid:
            return {"sl_price": float(current_price + atr * config.SL_FALLBACK_ATR_MULT), "sl_type": "atr_fallback"}

    else:
        raise ValueError("direction must be 'long' or 'short'")

    return {"sl_price": None, "sl_type": None}