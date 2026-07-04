"""
Pure indicator math. No strategy logic here -- just rigid, reproducible
calculations that every module reads from.
"""

import pandas as pd
import numpy as np
import config


def add_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD, col: str = "close") -> pd.DataFrame:
    """Wilder's RSI, plus an SMA of the RSI line itself (used for the
    'RSI touching/crossing its SMA' trigger in Module 2)."""
    df = df.copy()
    delta = df[col].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)  # neutral when undefined (e.g. no losses yet)

    df[f"rsi{period}"] = rsi
    df[f"rsi{period}_sma"] = rsi.rolling(config.RSI_SMA_PERIOD).mean()
    return df


def add_atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    df[f"atr{period}"] = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return df


def add_volume_ma(df: pd.DataFrame, period: int = config.VOLUME_MA_PERIOD) -> pd.DataFrame:
    df = df.copy()
    df[f"vol_sma{period}"] = df["volume"].rolling(period).mean()
    return df


def add_anchored_vwap(df: pd.DataFrame, anchor: str = "D") -> pd.DataFrame:
    """
    Anchored VWAP, reset at each new period boundary.
    anchor: 'D' for daily anchor, 'W' for weekly anchor.
    df.index must be a DatetimeIndex (UTC recommended).
    """
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("add_anchored_vwap requires a DatetimeIndex")

    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical_price * df["volume"]

    # to_period() drops tz info with a warning if the index is tz-aware; since
    # we're already anchored in UTC, strip tz explicitly for the grouping key only.
    naive_index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    period_key = naive_index.to_period(anchor)
    cum_tp_vol = tp_vol.groupby(period_key).cumsum()
    cum_vol = df["volume"].groupby(period_key).cumsum()

    col_name = "vwap_daily" if anchor == "D" else "vwap_weekly"
    df[col_name] = cum_tp_vol / cum_vol.replace(0, np.nan)
    return df


def build_indicator_stack(df: pd.DataFrame, vwap_anchor: str = "D") -> pd.DataFrame:
    """Convenience: apply the full standard indicator stack in one call."""
    df = add_rsi(df)
    df = add_atr(df)
    df = add_volume_ma(df)
    df = add_anchored_vwap(df, anchor=vwap_anchor)
    return df
