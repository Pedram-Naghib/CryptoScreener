"""
Strategy: Dynamic EMA Confluence
==================================
EMA50 checked on 1H and 4H; EMA200 checked on 4H and 1D. No EMA9/EMA21
checks below 4H, per directive.

Confluence-only: this strategy's weight (1, in weights.json) is deliberately
below the alert threshold (4), so it can never trigger an alert by itself --
enforced structurally by the scoring engine summing weights, not by any
special-cased "don't fire alone" logic here.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config
from strategies.base import Strategy, StrategyResult, DirectionResult

# (timeframe, ema_column) pairs to check
_EMA_CHECKS = [
    (config.TF_1H, "ema_50"),
    (config.TF_4H, "ema_50"),
    (config.TF_4H, "ema_200"),
    (config.TF_1D, "ema_200"),
]


class EMAConfluence(Strategy):
    name = "ema_confluence"
    required_timeframes = [config.TF_1H, config.TF_4H, config.TF_1D]

    def evaluate(self, data):
        long_matches = []
        short_matches = []

        for tf, ema_col in _EMA_CHECKS:
            df = data.get(tf)
            if df is None or ema_col not in df.columns or len(df) < 6:
                continue

            last = df.iloc[-1]
            prev = df.iloc[-5]
            ema_val = last[ema_col]
            if pd.isna(ema_val) or ema_val == 0:
                continue

            in_zone = abs(last["close"] - ema_val) / ema_val <= config.EMA_PROXIMITY_PCT
            if not in_zone:
                continue

            approaching_from_below = prev["close"] < ema_val
            # label combines TF + which EMA, since a strategy can match on the
            # same TF for different EMAs (e.g. 4H ema_50 AND 4H ema_200)
            label = f"{tf}:{ema_col}"

            if approaching_from_below:
                long_matches.append((label, {}))
            else:
                short_matches.append((label, {}))

        return StrategyResult(
            long=self.merge_matches(long_matches),
            short=self.merge_matches(short_matches),
        )