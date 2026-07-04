"""
Shared pivot/swing detection primitive. Used by Module 2 (divergence, double
bottom/top) and Module 3 (liquidity sweep). Kept separate so it's defined once.
"""

import pandas as pd
import numpy as np


def find_swing_highs(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.Series:
    """Confirmed pivot highs: strict max within [i-left, i+right]. Confirms
    `right` bars later -> no repaint once flagged True."""
    highs = df["high"].values
    n = len(df)
    flags = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        window = highs[i - left: i + right + 1]
        if highs[i] == window.max() and (window == highs[i]).sum() == 1:
            flags[i] = True
    return pd.Series(flags, index=df.index)


def find_swing_lows(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.Series:
    lows = df["low"].values
    n = len(df)
    flags = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        window = lows[i - left: i + right + 1]
        if lows[i] == window.min() and (window == lows[i]).sum() == 1:
            flags[i] = True
    return pd.Series(flags, index=df.index)
