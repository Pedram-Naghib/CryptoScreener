"""
Fair Value Gap detection -- shared primitive used by Module 1 (entry trigger)
and tp_logic.py (target selection).

Definition (3-candle pattern):
  Bullish FVG: low of candle[i] > high of candle[i-2]  (gap left below candle i-1)
  Bearish FVG: high of candle[i] < low of candle[i-2]

Only gaps where the MIDDLE candle (i-1, the expansion/displacement candle)
has volume >= FVG_VOLUME_MULT * its volume MA are considered valid --
this is the "prove true displacement" filter from your Gemini chat.
"""

import pandas as pd
import numpy as np
import config


def detect_fvgs(df: pd.DataFrame, vol_ma_col: str = f"vol_sma{config.VOLUME_MA_PERIOD}") -> pd.DataFrame:
    """
    Appends columns to df (indexed at the THIRD candle of each 3-candle pattern,
    i.e. the candle that confirms the gap):
      bullish_fvg, bearish_fvg : bool
      fvg_top, fvg_bottom      : float (gap boundaries)
      fvg_mitigated            : bool, True once price has fully closed the gap
    """
    df = df.copy()
    n = len(df)

    bullish = np.zeros(n, dtype=bool)
    bearish = np.zeros(n, dtype=bool)
    fvg_top = np.full(n, np.nan)
    fvg_bottom = np.full(n, np.nan)

    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values
    vol_ma = df[vol_ma_col].values

    for i in range(2, n):
        mid_vol_ok = (
            not np.isnan(vol_ma[i - 1])
            and vol[i - 1] >= config.FVG_VOLUME_MULT * vol_ma[i - 1]
        )
        if not mid_vol_ok:
            continue

        # Bullish: gap between candle i-2's high and candle i's low
        if low[i] > high[i - 2]:
            bullish[i] = True
            fvg_bottom[i] = high[i - 2]
            fvg_top[i] = low[i]

        # Bearish: gap between candle i-2's low and candle i's high
        if high[i] < low[i - 2]:
            bearish[i] = True
            fvg_top[i] = low[i - 2]
            fvg_bottom[i] = high[i]

    df["bullish_fvg"] = bullish
    df["bearish_fvg"] = bearish
    df["fvg_top"] = fvg_top
    df["fvg_bottom"] = fvg_bottom

    df["fvg_mitigated"] = _compute_mitigation(df)
    return df


def _compute_mitigation(df: pd.DataFrame) -> pd.Series:
    """
    A gap is 'mitigated' once, at any point AFTER it formed, price has
    fully traded back through the gap (close or wick beyond the far edge).
    We check the near-term future relative to each gap's formation bar.
    """
    n = len(df)
    mitigated = np.zeros(n, dtype=bool)
    low = df["low"].values
    high = df["high"].values
    is_bull = df["bullish_fvg"].values
    is_bear = df["bearish_fvg"].values
    fvg_bottom = df["fvg_bottom"].values

    for i in range(n):
        if is_bull[i]:
            # mitigated when future price trades back down through fvg_bottom
            future_low = low[i + 1:]
            if len(future_low) and (future_low <= fvg_bottom[i]).any():
                mitigated[i] = True
        elif is_bear[i]:
            future_high = high[i + 1:]
            fvg_top_i = df["fvg_top"].values[i]
            if len(future_high) and (future_high >= fvg_top_i).any():
                mitigated[i] = True

    return pd.Series(mitigated, index=df.index)


def get_active_fvgs(df: pd.DataFrame) -> pd.DataFrame:
    """Returns only unmitigated FVGs (as of the last available bar) -- these
    are the ones still 'live' as potential entry zones or TP targets."""
    fvgs = df[(df["bullish_fvg"] | df["bearish_fvg"]) & (~df["fvg_mitigated"])]
    return fvgs
