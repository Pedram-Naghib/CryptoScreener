"""
Strategy base class + result container. Every scoring strategy inherits from
Strategy and implements evaluate(). The scoring engine never touches strategy
internals -- it only reads the StrategyResult it gets back.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict
import pandas as pd


@dataclass
class DirectionResult:
    score: int = 0
    details: Dict = field(default_factory=dict)


@dataclass
class StrategyResult:
    long: DirectionResult = field(default_factory=DirectionResult)
    short: DirectionResult = field(default_factory=DirectionResult)


class Strategy(ABC):
    """
    Subclass this for every scoring module. Required class attributes:
      name                 : str, unique id, matched against weights.json
      required_timeframes  : list[str], timeframes this strategy needs

    weight is injected by the scoring engine from weights.json at
    construction time -- never hardcode it in a subclass.
    """
    name: str = "unnamed_strategy"
    required_timeframes: list = []

    def __init__(self, weight: int):
        self.weight = weight

    @abstractmethod
    def evaluate(self, data: Dict[str, pd.DataFrame]) -> StrategyResult:
        """
        data: { timeframe: DataFrame }. Only timeframes this strategy declared
        in required_timeframes are guaranteed present, and only if the fetch
        succeeded -- always check with .get()/`in` before indexing.

        Must return a StrategyResult with .long.score / .short.score set to
        either 0 or exactly self.weight (never a partial value) -- the
        scoring engine sums these directly, it does not scale them.
        """
        raise NotImplementedError

    def merge_matches(self, matches: list) -> DirectionResult:
        """
        Call this instead of building DirectionResult by hand whenever a
        strategy can match on more than one timeframe. Caps the score at
        self.weight (never adds it per-timeframe) while preserving full
        visibility into WHICH timeframes agreed -- e.g. the alert shows
        "EMA Confluence [4H, 1D]" instead of losing everything but the last
        match. This is why every strategy should route through here rather
        than overwriting a DirectionResult in a loop.

        matches: list of (timeframe: str, extra_details: dict) tuples,
                 one entry per timeframe that independently triggered.
        Returns a DirectionResult with score=0 if matches is empty.
        """
        if not matches:
            return DirectionResult()

        timeframes = [tf for tf, _ in matches]
        merged: Dict = {"tf": timeframes}

        extra_keys = set()
        for _, extra in matches:
            extra_keys.update(extra.keys())

        for key in extra_keys:
            values = [extra.get(key) for _, extra in matches]
            # if every timeframe agrees on this value, show it once; otherwise
            # show the per-timeframe list so nothing gets silently dropped
            if len(set(map(str, values))) == 1:
                merged[key] = values[0]
            else:
                merged[key] = values

        return DirectionResult(score=self.weight, details=merged)