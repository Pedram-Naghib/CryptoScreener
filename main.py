"""
Main Orchestrator
==================
    [Watchlist Screener] ──> symbols
              │
              ▼
    [Data Engine] ──> fetches OHLCV per symbol/timeframe (ccxt, async)
              │
              ▼
    [Indicator Stack] ──> RSI, ATR, volume MA, anchored VWAP
              │
              ▼
    [Strategy Evaluator] ──> Module 1 (1H/4H) | Module 2 (D/W) | Module 3 (1H/4H)
              │
              ▼
    [TP Logic] ──> nearest FVG / swept liquidity level
              │
              ▼
    [Telegram Notifier]

Runs on a loop, sleeping config.SCAN_INTERVAL_SECONDS between cycles.
Only the LAST (most recently closed) candle's signal state triggers a live alert
-- everything before that is just context the modules need to compute it.
"""

import asyncio
import logging

import config
import data_engine
import indicators
import watchlist_screener
import notifier
import tp_logic

from strategies.module1_fvg_vwap import evaluate_module1, VWAP_COL_BY_TF
from strategies.module2_htf_divergence import evaluate_module2
from strategies.module3_liquidity_sweep import evaluate_module3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("main")


async def process_module1_module3(symbol: str, data: dict):
    for tf in config.MODULE1_TIMEFRAMES:
        df = data.get(symbol, {}).get(tf)
        if df is None or len(df) < 50:
            continue

        anchor = "D" if tf == config.TF_1H else "W"
        df = indicators.build_indicator_stack(df, vwap_anchor=anchor)

        # --- Module 1 ---
        m1_df = evaluate_module1(df, tf)
        last = m1_df.iloc[-1]
        if last["module1_long_signal"] or last["module1_short_signal"]:
            direction = "long" if last["module1_long_signal"] else "short"
            tp = tp_logic.suggest_tp(m1_df, direction)
            msg = notifier.format_module1_alert(symbol, tf, direction, last["close"], tp)
            await notifier.send_alert(msg)

        # --- Module 3 (reuses same TFs) ---
        m3_df = evaluate_module3(df)
        last3 = m3_df.iloc[-1]
        if last3["lsr_long_signal"] or last3["lsr_short_signal"]:
            direction = "long" if last3["lsr_long_signal"] else "short"
            # Module 3 df doesn't have FVGs detected -- reuse m1_df's if same tf,
            # otherwise just skip FVG-based TP and fall back to swept liquidity.
            tp_source = m1_df.copy()
            tp_source["swing_high"] = m3_df["swing_high"]
            tp_source["swing_low"] = m3_df["swing_low"]
            tp = tp_logic.suggest_tp(tp_source, direction)
            msg = notifier.format_module3_alert(
                symbol, tf, direction, last3["close"], bool(last3["vol_exhaustion"]), tp
            )
            await notifier.send_alert(msg)


async def process_module2(symbol: str, data: dict):
    for tf in config.MODULE2_TIMEFRAMES:
        df = data.get(symbol, {}).get(tf)
        if df is None or len(df) < 50:
            continue

        # Module 2 doesn't strictly need VWAP, but build the full stack for consistency
        df = indicators.build_indicator_stack(df, vwap_anchor="W")
        m2_df = evaluate_module2(df)
        last = m2_df.iloc[-1]

        if last["module2_short_signal"]:
            confluence = last["module2_short_confluence"]
            tp = tp_logic.suggest_tp(m2_df, "short") if "bullish_fvg" in m2_df.columns else {"target_price": None, "target_type": None}
            msg = notifier.format_module2_alert(symbol, tf, "short", last["close"], confluence, tp)
            await notifier.send_alert(msg)

        if last["module2_long_signal"]:
            confluence = last["module2_long_confluence"]
            tp = tp_logic.suggest_tp(m2_df, "long") if "bullish_fvg" in m2_df.columns else {"target_price": None, "target_type": None}
            msg = notifier.format_module2_alert(symbol, tf, "long", last["close"], confluence, tp)
            await notifier.send_alert(msg)


async def run_cycle():
    logger.info("Building watchlist...")
    symbols = await watchlist_screener.build_watchlist()
    logger.info(f"Scanning {len(symbols)} symbols: {symbols}")

    all_timeframes = list(set(config.MODULE1_TIMEFRAMES + config.MODULE2_TIMEFRAMES))
    data = await data_engine.fetch_all(symbols, all_timeframes)

    tasks = []
    for symbol in symbols:
        tasks.append(process_module1_module3(symbol, data))
        tasks.append(process_module2(symbol, data))

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
