"""
Strategy: EMA Historical Rejection
=====================================
Folded into the scoring matrix from the standalone EMA Reaction tool: has
this EMA rejected price multiple times recently, AND is price at it again
right now with RSI in the mid-lane and turning away? Weight 1, like EMA
Confluence -- structurally incapable of triggering an alert alone.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from ema_reaction import evaluate_ema_reaction
from strategies.base import Strategy, StrategyResult, DirectionResult


class EMAHistoricalRejection(Strategy):
    name = "ema_historical_rejection"
    required_timeframes = [config.TF_1H, config.TF_4H, config.TF_1D]

    def evaluate(self, data):
        result = StrategyResult()

        for tf, df in data.items():
            if len(df) < config.EMA_REJECTION_LOOKBACK_BARS:
                continue
            reaction = evaluate_ema_reaction(df)
            if not reaction.get("active"):
                continue

            details = {
                "tf": tf,
                "ema": reaction["ema"],
                "prior_rejections": reaction["prior_rejections"],
            }
            if reaction["direction"] == "bullish_rejection":
                result.long = DirectionResult(score=self.weight, details=details)
            else:
                result.short = DirectionResult(score=self.weight, details=details)

        return result