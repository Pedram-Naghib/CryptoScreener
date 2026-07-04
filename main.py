"""
Main Orchestrator (Weighted Confluence Scoring Matrix)
=========================================================
    [Watchlist Screener] -> symbols
              |
    [Data Engine] -> fetches OHLCV per symbol/timeframe (ccxt, async)
              |
    [Scoring Engine] -> runs every auto-discovered strategy, sums weighted
                         scores per direction (long/short)
              |
    [Telegram Notifier] -> ONE alert per symbol/direction when score >=
                            alert_threshold (weights.json), with a full
                            breakdown of which strategies contributed

Adding a new strategy = drop a file in strategies/ + add its weight to
weights.json. This file never needs to change.
"""

import asyncio
import logging

import config
import data_engine
import watchlist_screener
import notifier
import scoring_engine
from strategies.registry import discover_strategies

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("main")

STRATEGIES = discover_strategies()
ALERT_THRESHOLD = scoring_engine.get_alert_threshold()

logger.info(
    f"Loaded {len(STRATEGIES)} strategies: {[s.name for s in STRATEGIES]} "
    f"(alert threshold = {ALERT_THRESHOLD})"
)


async def process_symbol(symbol: str, raw_data: dict):
    result = scoring_engine.score_symbol(raw_data, STRATEGIES)

    if result["long_score"] >= ALERT_THRESHOLD:
        msg = notifier.format_scored_alert(
            symbol, "long", result["long_score"], ALERT_THRESHOLD,
            result["long_breakdown"], result["long_tp"],
        )
        await notifier.send_alert(msg)

    if result["short_score"] >= ALERT_THRESHOLD:
        msg = notifier.format_scored_alert(
            symbol, "short", result["short_score"], ALERT_THRESHOLD,
            result["short_breakdown"], result["short_tp"],
        )
        await notifier.send_alert(msg)


async def run_cycle():
    logger.info("Building watchlist...")
    symbols = await watchlist_screener.build_watchlist()
    logger.info(f"Scanning {len(symbols)} symbols: {symbols}")

    all_timeframes = scoring_engine.collect_required_timeframes(STRATEGIES)
    data = await data_engine.fetch_all(symbols, all_timeframes)

    tasks = [process_symbol(symbol, data.get(symbol, {})) for symbol in symbols]
    await asyncio.gather(*tasks)
    logger.info("Cycle complete.")


async def main_loop():
    while True:
        try:
            await run_cycle()
        except Exception as e:
            logger.exception(f"Cycle failed: {e}")
        await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main_loop())