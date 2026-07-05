"""
Scoring Engine
================
Aggregates every registered strategy's score for a symbol, per direction
(long/short), and decides whether the combined score clears the alert
threshold from weights.json.

    [Watchlist Screener] -> symbols
              |
    [Data Engine] -> raw OHLCV per symbol/timeframe
              |
    [build_indicator_stacks] -> RSI, ATR, EMAs, volume MA, anchored VWAP
              |
    [score_symbol] -> runs every registered Strategy, sums weighted scores
              |
    [main.py] -> alerts when long_score/short_score >= alert_threshold
"""

import json
import os
import logging
from typing import Dict, List

import pandas as pd

import config
import indicators
import tp_logic
from fvg import detect_fvgs
from pivots import find_swing_highs, find_swing_lows
from strategies.base import Strategy, StrategyResult

logger = logging.getLogger("scoring_engine")

_WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights.json")


def get_alert_threshold() -> int:
    with open(_WEIGHTS_PATH) as f:
        return json.load(f).get("alert_threshold", 4)


def collect_required_timeframes(strategies: List[Strategy]) -> List[str]:
    tfs = set()
    for s in strategies:
        tfs.update(s.required_timeframes)
    return list(tfs)


def build_indicator_stacks(raw_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    raw_data: { timeframe: raw OHLCV df }. Applies the correct VWAP anchor
    per timeframe (Daily for 1H, Weekly for everything 4H and above) and
    returns a new dict with the full indicator stack added.
    """
    out = {}
    for tf, df in raw_data.items():
        if df is None or len(df) < 50:
            continue
        anchor = "D" if tf == config.TF_1H else "W"
        out[tf] = indicators.build_indicator_stack(df, vwap_anchor=anchor)
    return out


def suggest_trade_levels_for_direction(data: Dict[str, pd.DataFrame], direction: str) -> dict | None:
    """
    Prefers 1H, falls back to 4H -- first timeframe with a usable TP AND SL
    (and an R:R that clears MIN_RR_RATIO) wins. Returns None if no timeframe
    produces a usable set of levels, so callers never have to alert with a
    missing TP or SL.
    """
    atr_col = f"atr{config.ATR_PERIOD}"

    for tf in (config.TF_1H, config.TF_4H):
        df = data.get(tf)
        if df is None:
            continue
        df = detect_fvgs(df.copy())
        df["swing_high"] = find_swing_highs(df, config.LTF_PIVOT_WINDOW, config.LTF_PIVOT_WINDOW)
        df["swing_low"] = find_swing_lows(df, config.LTF_PIVOT_WINDOW, config.LTF_PIVOT_WINDOW)

        tp = tp_logic.suggest_tp(df, direction)
        if not tp.get("target_price"):
            continue
        sl = tp_logic.suggest_sl(df, direction, atr_col)
        if not sl.get("sl_price"):
            continue

        entry_price = float(df["close"].iloc[-1])
        risk = abs(entry_price - sl["sl_price"])
        reward = abs(tp["target_price"] - entry_price)
        if risk <= 0:
            continue
        rr = reward / risk
        if rr < config.MIN_RR_RATIO:
            continue

        return {
            "entry_price": entry_price,
            "tp_price": tp["target_price"],
            "tp_type": tp["target_type"],
            "sl_price": sl["sl_price"],
            "sl_type": sl["sl_type"],
            "rr": round(rr, 2),
            "timeframe": tf,
        }

    return None


def score_symbol(raw_data: Dict[str, pd.DataFrame], strategies: List[Strategy]) -> dict:
    """
    Returns: {
      'long_score': int, 'short_score': int,
      'long_breakdown': [ (strategy_name, score, details), ... ],
      'short_breakdown': [ ... ],
      'long_levels': {entry_price, sl_price, sl_type, tp_price, tp_type, rr, timeframe} | None,
      'short_levels': {...} | None,
    }
    """
    data = build_indicator_stacks(raw_data)

    long_score = 0
    short_score = 0
    long_breakdown = []
    short_breakdown = []

    for strat in strategies:
        strat_data = {tf: data[tf] for tf in strat.required_timeframes if tf in data}
        if not strat_data:
            continue
        try:
            result: StrategyResult = strat.evaluate(strat_data)
        except Exception as e:
            logger.warning(f"{strat.name} failed: {e}")
            continue

        if result.long.score:
            long_score += result.long.score
            long_breakdown.append((strat.name, result.long.score, result.long.details))
        if result.short.score:
            short_score += result.short.score
            short_breakdown.append((strat.name, result.short.score, result.short.details))

    threshold = get_alert_threshold()
    long_levels = suggest_trade_levels_for_direction(data, "long") if long_score >= threshold else None
    short_levels = suggest_trade_levels_for_direction(data, "short") if short_score >= threshold else None

    return {
        "long_score": long_score,
        "short_score": short_score,
        "long_breakdown": long_breakdown,
        "short_breakdown": short_breakdown,
        "long_levels": long_levels,
        "short_levels": short_levels,
    }