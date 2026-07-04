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