"""
Main Orchestrator (Weighted Confluence Scoring Matrix + R-Multiple Journal)
=============================================================================
    [Watchlist Screener] -> symbols
              |
    [Data Engine] -> fetches OHLCV per symbol/timeframe (ccxt, async)
              |
    [Scoring Engine] -> runs every auto-discovered strategy, sums weighted
                         scores per direction (long/short), and -- if a
                         direction clears the alert threshold -- computes
                         entry/SL/TP/R:R for it
              |
    [Signal Tracker] -> dedups (skips re-alerting a symbol/direction that's
                         already open), opens new tracked signals, and every
                         cycle checks existing open signals against the
                         latest candle for a TP/SL hit
              |
    [Telegram Notifier] -> alerts on: new signal opened, signal closed
                            (+/-R), and periodic performance summaries

Adding a new strategy = drop a file in strategies/ + add its weight to
weights.json. This file never needs to change for that.
"""

import asyncio
import logging

import config
import data_engine
import watchlist_screener
import notifier
import scoring_engine
import signal_tracker
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
    """Scores a symbol and opens/alerts a new tracked signal per direction,
    skipping any direction that's already being tracked (dedup) or that
    cleared the score threshold without a usable TP/SL/R:R."""
    result = scoring_engine.score_symbol(raw_data, STRATEGIES)

    for direction in ("long", "short"):
        score = result[f"{direction}_score"]
        if score < ALERT_THRESHOLD:
            continue

        levels = result[f"{direction}_levels"]
        if levels is None:
            logger.info(f"{symbol} {direction} cleared threshold but no valid TP/SL/R:R -- skipping")
            continue

        if await signal_tracker.has_open_signal(symbol, direction):
            continue  # already tracking an open signal here -- don't re-alert every cycle

        breakdown = result[f"{direction}_breakdown"]
        msg = notifier.format_scored_alert(symbol, direction, score, ALERT_THRESHOLD, breakdown, levels)
        await notifier.send_alert(msg)
        await signal_tracker.open_signal(symbol, direction, levels, score)


async def check_open_signals(symbol: str, raw_data: dict):
    """Checks this symbol's open tracked signals (if any) against the latest
    1H candle and sends a closed-signal alert for anything that hit TP/SL."""
    df_1h = raw_data.get(config.TF_1H)
    closed = await signal_tracker.check_symbol_signals(symbol, df_1h)
    for record in closed:
        await notifier.send_alert(notifier.format_signal_closed(record))


async def maybe_send_performance_summary():
    if await signal_tracker.should_send_summary():
        stats = await signal_tracker.get_performance_summary(hours=config.PERFORMANCE_SUMMARY_INTERVAL_HOURS)
        period_label = f"last {config.PERFORMANCE_SUMMARY_INTERVAL_HOURS}h"
        await notifier.send_alert(notifier.format_performance_summary(stats, period_label))
        await signal_tracker.mark_summary_sent()


async def run_cycle():
    logger.info("Building watchlist...")
    watchlist_symbols = await watchlist_screener.build_watchlist()

    # Symbols with an open tracked signal must keep being fetched even if
    # they later fall off the live watchlist -- otherwise we'd lose the
    # ability to ever close them out.
    open_symbols = await signal_tracker.get_open_symbols()
    all_symbols = sorted(set(watchlist_symbols) | open_symbols)
    tracked_only = len(open_symbols - set(watchlist_symbols))
    logger.info(f"Scanning {len(all_symbols)} symbols ({len(watchlist_symbols)} watchlist + {tracked_only} tracked-only)")

    all_timeframes = set(scoring_engine.collect_required_timeframes(STRATEGIES))
    all_timeframes.add(config.TF_1H)  # always needed to check open signals for TP/SL hits
    data = await data_engine.fetch_all(all_symbols, list(all_timeframes))

    score_tasks = [process_symbol(symbol, data.get(symbol, {})) for symbol in watchlist_symbols]
    await asyncio.gather(*score_tasks)

    check_tasks = [check_open_signals(symbol, data.get(symbol, {})) for symbol in all_symbols]
    await asyncio.gather(*check_tasks)

    await maybe_send_performance_summary()
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