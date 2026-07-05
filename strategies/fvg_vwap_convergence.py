"""
Strategy: FVG + VWAP Convergence
===================================
Folded into the scoring matrix from the original Module 1 spec: fresh,
volume-confirmed FVG that price is currently pulling back into, while also
aligning with the relevant anchored VWAP (Daily VWAP for 1H, Weekly VWAP
for 4H). Only the LAST bar's live state is checked (this runs on a live
scanning loop, not a backtest).
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config
from fvg import detect_fvgs, get_active_fvgs
from strategies.base import Strategy, StrategyResult, DirectionResult

_VWAP_COL_BY_TF = {config.TF_1H: "vwap_daily", config.TF_4H: "vwap_weekly"}


class FVGVWAPConvergence(Strategy):
    name = "fvg_vwap_convergence"
    required_timeframes = [config.TF_1H, config.TF_4H]

    def evaluate(self, data):
        long_matches = []
        short_matches = []

        for tf, df in data.items():
            vwap_col = _VWAP_COL_BY_TF.get(tf)
            if vwap_col is None or vwap_col not in df.columns or len(df) < 10:
                continue

            df = detect_fvgs(df.copy())
            active = get_active_fvgs(df)
            if active.empty:
                continue

            current_price = df["close"].iloc[-1]
            current_low = df["low"].iloc[-1]
            current_high = df["high"].iloc[-1]
            current_vwap = df[vwap_col].iloc[-1]
            if np.isnan(current_vwap):
                continue

            near_vwap = abs(current_price - current_vwap) / current_vwap <= config.FVG_VWAP_TOLERANCE_PCT
            if not near_vwap:
                continue

            tf_long_hit = False
            tf_short_hit = False
            for _, gap in active.iterrows():
                top, bottom = gap["fvg_top"], gap["fvg_bottom"]
                gap_size = top - bottom
                if gap_size <= 0:
                    continue

                if gap["bullish_fvg"]:
                    proximity_hit = abs(current_price - bottom) / bottom <= config.FVG_PROXIMITY_PCT
                    wick_hit = current_low <= bottom + gap_size * config.FVG_WICK_ENTRY_PCT
                    if proximity_hit or wick_hit:
                        tf_long_hit = True

                elif gap["bearish_fvg"]:
                    proximity_hit = abs(current_price - top) / top <= config.FVG_PROXIMITY_PCT
                    wick_hit = current_high >= top - gap_size * config.FVG_WICK_ENTRY_PCT
                    if proximity_hit or wick_hit:
                        tf_short_hit = True

            if tf_long_hit:
                long_matches.append((tf, {}))
            if tf_short_hit:
                short_matches.append((tf, {}))

        return StrategyResult(
            long=self.merge_matches(long_matches),
            short=self.merge_matches(short_matches),
        )