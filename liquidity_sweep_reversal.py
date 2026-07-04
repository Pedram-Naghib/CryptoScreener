"""
Strategy: Liquidity Sweep Reversal
=====================================
Folded into the scoring matrix from the original Module 3 (your TCT/
liquidity-grab chart): sweep of a swing high/low, close back inside range,
confirmed by RSI divergence within a short window. Checked here against the
LAST few bars' live sweep + divergence state.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from pivots import find_swing_highs, find_swing_lows
from strategies.base import Strategy, StrategyResult, DirectionResult


class LiquiditySweepReversal(Strategy):
    name = "liquidity_sweep_reversal"
    required_timeframes = [config.TF_1H, config.TF_4H]

    def evaluate(self, data):
        result = StrategyResult()
        rsi_col = f"rsi{config.RSI_PERIOD}"
        atr_col = f"atr{config.ATR_PERIOD}"

        for tf, df in data.items():
            if len(df) < 30:
                continue
            df = df.copy()
            df["swing_high"] = find_swing_highs(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)
            df["swing_low"] = find_swing_lows(df, config.PIVOT_LEFT, config.PIVOT_RIGHT)

            last_swing_high = df.loc[df["swing_high"], "high"].reindex(df.index).ffill().shift(1)
            last_swing_low = df.loc[df["swing_low"], "low"].reindex(df.index).ffill().shift(1)
            buffer = df[atr_col] * config.LSR_BUFFER_ATR_MULT

            sweep_short = (df["high"] > last_swing_high + buffer) & (df["close"] < last_swing_high)
            sweep_long = (df["low"] < last_swing_low - buffer) & (df["close"] > last_swing_low)

            recent_sweep_short = sweep_short.iloc[-config.LSR_CONFLUENCE_WINDOW:].fillna(False).any()
            recent_sweep_long = sweep_long.iloc[-config.LSR_CONFLUENCE_WINDOW:].fillna(False).any()

            if recent_sweep_short:
                ph = df.index[df["swing_high"]]
                if len(ph) >= 2:
                    cur, prev = ph[-1], ph[-2]
                    if df.loc[cur, "high"] > df.loc[prev, "high"] and df.loc[cur, rsi_col] < df.loc[prev, rsi_col]:
                        result.short = DirectionResult(score=self.weight, details={"tf": tf})

            if recent_sweep_long:
                pl = df.index[df["swing_low"]]
                if len(pl) >= 2:
                    cur, prev = pl[-1], pl[-2]
                    if df.loc[cur, "low"] < df.loc[prev, "low"] and df.loc[cur, rsi_col] > df.loc[prev, rsi_col]:
                        result.long = DirectionResult(score=self.weight, details={"tf": tf})

        return result