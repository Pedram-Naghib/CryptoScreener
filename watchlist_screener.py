"""
Phase 0: Watchlist Screener
============================
Two sources, always merged:
  1. FALLBACK_WATCHLIST (config.py) -- always scanned, guarantees the bot
     never goes dark even if the live screener or an API call fails.
  2. Live screener -- filters all KuCoin perpetual pairs by 24h volume
     and relative volume (RVOL), per your Gemini-chat baseline.

Toggle live screening on/off via config.USE_LIVE_SCREENER.
"""

import asyncio
import logging
from typing import List

import config
import data_engine

logger = logging.getLogger("watchlist_screener")


async def _compute_rvol(symbols: List[str]) -> dict:
    """
    RVOL = current bar's volume / average volume over RVOL_LOOKBACK_BARS,
    measured on the 1H timeframe (matches the primary execution TF).
    """
    data = await data_engine.fetch_all(symbols, [config.TF_1H])
    rvol_map = {}
    for symbol, tfs in data.items():
        df = tfs.get(config.TF_1H)
        if df is None or len(df) < config.RVOL_LOOKBACK_BARS + 1:
            continue
        avg_vol = df["volume"].iloc[-(config.RVOL_LOOKBACK_BARS + 1):-1].mean()
        current_vol = df["volume"].iloc[-1]
        if avg_vol and avg_vol > 0:
            rvol_map[symbol] = current_vol / avg_vol
    return rvol_map


async def build_watchlist() -> List[str]:
    fallback = list(dict.fromkeys(config.FALLBACK_WATCHLIST))  # de-dup, preserve order

    if not config.USE_LIVE_SCREENER:
        return fallback[: config.MAX_WATCHLIST_SIZE]

    try:
        tickers = await data_engine.fetch_tickers_24h()
    except Exception as e:
        logger.warning(f"Live screener failed fetching tickers, falling back: {e}")
        return fallback[: config.MAX_WATCHLIST_SIZE]

    # Filter 1: perpetual USDT pairs above min 24h volume (quoteVolume in USD terms)
    volume_candidates = []
    for symbol, t in tickers.items():
        if not symbol.endswith(":USDT"):
            continue
        quote_vol = t.get("quoteVolume") or 0
        if quote_vol >= config.MIN_24H_VOLUME_USD:
            volume_candidates.append(symbol)

    if not volume_candidates:
        logger.warning("Screener found no pairs above MIN_24H_VOLUME_USD; using fallback only")
        return fallback[: config.MAX_WATCHLIST_SIZE]

    # Filter 2: RVOL, requires an extra round-trip of 1H OHLCV per candidate
    rvol_map = await _compute_rvol(volume_candidates)
    screened = [s for s, rvol in rvol_map.items() if rvol >= config.MIN_RVOL]

    # Rank by RVOL descending so the most "active right now" pairs are first
    screened.sort(key=lambda s: rvol_map[s], reverse=True)

    merged = list(dict.fromkeys(fallback + screened))
    return merged[: config.MAX_WATCHLIST_SIZE]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    watchlist = asyncio.run(build_watchlist())
    print(f"Watchlist ({len(watchlist)}): {watchlist}")
