"""
Module 3: Liquidity Sweep Reversal (LSR)
==========================================
The objective codification of the TCT-distribution chart that kicked this off:
sweep -> LTF RSI divergence within a short window -> optional volume-exhaustion
confirmation. Explicitly does NOT encode the TCT arc/schematic shape itself.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

import config
from pivots import find_swing_highs, find_swing_lows


def detect_liquidity_sweep_short(df: pd.DataFrame) -> pd.Series:
    atr_col = f"atr{config.ATR_PERIOD}"
    last_swing_high = (
        df.loc[df["swing_high"], "high"].reindex(df.index).ffill().shift(1)
    )
    buffer = df[atr_col] * config.LSR_BUFFER_ATR_MULT
    swept = (df["high"] > last_swing_high + buffer) & (df["close"] < last_swing_high)
    return swept.fillna(False)


def detect_liquidity_sweep_long(df: pd.DataFrame) -> pd.Series:
    atr_col = f"atr{config.ATR_PERIOD}"
    last_swing_low = (
        df.loc[df["swing_low"], "low"].reindex(df.index).ffill().shift(1)
    )
    buffer = df[atr_col] * config.LSR_BUFFER_ATR_MULT
    swept = (df["low"] < last_swing_low - buffer) & (df["close"] > last_swing_low)
    return swept.fillna(False)


def detect_volume_exhaustion(df: pd.DataFrame, decay_bars: int = 3) -> pd.Series:
    vol_ma_col = f"vol_sma{config.VOLUME_MA_PERIOD}"
    spike = df["volume"] > 1.5 * df[vol_ma_col]
    vol = df["volume"].values
    n = len(df)
    exhaustion = np.zeros(n, dtype=bool)
    for i in np.where(spike.values)[0]:
        if i + decay_bars < n:
            window = vol[i: i + decay_bars + 1]
            if all(window[j] > window[j + 1] for j in range(len(window) - 1)):
                exhaustion[i + decay_bars] = True
    return pd.Series(exhaustion, index=df.index)


def evaluate_module3(df: pd.DataFrame) -> pd.DataFrame:
    """
    df must already have rsi{period}, atr{period}, vol_sma{period} columns.
    Returns df with lsr_short_signal / lsr_long_signal bool columns.
    """
    df = df.copy()
    df["swing_high"] = find_swing_highs(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)
    df["swing_low"] = find_swing_lows(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)
    df["sweep_short"] = detect_liquidity_sweep_short(df)
    df["sweep_long"] = detect_liquidity_sweep_long(df)

    rsi_col = f"rsi{config.RSI_PERIOD}"
    ph = df["swing_high"]
    pl = df["swing_low"]
    bearish_div = pd.Series(False, index=df.index)
    bullish_div = pd.Series(False, index=df.index)

    ph_idx = df.index[ph]
    for i in range(1, len(ph_idx)):
        cur, prev = ph_idx[i], ph_idx[i - 1]
        if (df.index.get_loc(cur) - df.index.get_loc(prev)) > config.DIVERGENCE_LOOKBACK_BARS:
            continue
        if df.loc[cur, "high"] > df.loc[prev, "high"] and df.loc[cur, rsi_col] < df.loc[prev, rsi_col]:
            bearish_div.loc[cur] = True

    pl_idx = df.index[pl]
    for i in range(1, len(pl_idx)):
        cur, prev = pl_idx[i], pl_idx[i - 1]
        if (df.index.get_loc(cur) - df.index.get_loc(prev)) > config.DIVERGENCE_LOOKBACK_BARS:
            continue
        if df.loc[cur, "low"] < df.loc[prev, "low"] and df.loc[cur, rsi_col] > df.loc[prev, rsi_col]:
            bullish_div.loc[cur] = True

    df["bearish_div"] = bearish_div
    df["bullish_div"] = bullish_div
    df["vol_exhaustion"] = detect_volume_exhaustion(df)

    df["lsr_short_signal"] = False
    df["lsr_long_signal"] = False

    for i in np.where(df["sweep_short"].values)[0]:
        if config.LSR_REQUIRE_VOLUME_EXHAUSTION and not df["vol_exhaustion"].iloc[i]:
            continue
        window_end = min(i + config.LSR_CONFLUENCE_WINDOW, len(df))
        window = df["bearish_div"].iloc[i:window_end]
        if window.any():
            confirm_idx = window.index[window.values.argmax()]
            df.loc[confirm_idx, "lsr_short_signal"] = True

    for i in np.where(df["sweep_long"].values)[0]:
        if config.LSR_REQUIRE_VOLUME_EXHAUSTION and not df["vol_exhaustion"].iloc[i]:
            continue
        window_end = min(i + config.LSR_CONFLUENCE_WINDOW, len(df))
        window = df["bullish_div"].iloc[i:window_end]
        if window.any():
            confirm_idx = window.index[window.values.argmax()]
            df.loc[confirm_idx, "lsr_long_signal"] = True

    return df
