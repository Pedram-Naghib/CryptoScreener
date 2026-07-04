"""
Data Engine
===========
Owns all exchange I/O. Nothing else in the project should import ccxt directly --
strategies and the orchestrator only ever see pandas DataFrames coming out of here.
"""

import asyncio
import logging
from typing import Dict, List

import ccxt.async_support as ccxt
import pandas as pd

import config

logger = logging.getLogger("data_engine")


def make_exchange() -> ccxt.Exchange:
    exchange_cls = getattr(ccxt, config.EXCHANGE_ID)
    exchange = exchange_cls(
        {
            "apiKey": config.API_KEY,
            "secret": config.API_SECRET,
            "password": config.API_PASSPHRASE,  # KuCoin needs a passphrase too
            "enableRateLimit": True,
            "options": {"defaultType": config.MARKET_TYPE},
        }
    )
    return exchange


def _ohlcv_to_df(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts")
    return df


async def fetch_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    limit: int,
    semaphore: asyncio.Semaphore,
) -> pd.DataFrame | None:
    async with semaphore:
        try:
            raw = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not raw:
                return None
            return _ohlcv_to_df(raw)
        except Exception as e:
            logger.warning(f"fetch_ohlcv failed for {symbol} {timeframe}: {e}")
            return None


async def fetch_all(
    symbols: List[str], timeframes: List[str]
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Returns nested dict: { symbol: { timeframe: DataFrame } }
    Missing/failed fetches are simply absent from the result (callers must
    handle a symbol/timeframe not being present).
    """
    exchange = make_exchange()
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_FETCHES)
    result: Dict[str, Dict[str, pd.DataFrame]] = {s: {} for s in symbols}

    tasks = []
    task_meta = []
    for symbol in symbols:
        for tf in timeframes:
            limit = config.OHLCV_LIMIT.get(tf, 300)
            tasks.append(fetch_ohlcv(exchange, symbol, tf, limit, semaphore))
            task_meta.append((symbol, tf))

    try:
        results = await asyncio.gather(*tasks)
    finally:
        await exchange.close()

    for (symbol, tf), df in zip(task_meta, results):
        if df is not None:
            result[symbol][tf] = df

    return result


async def fetch_tickers_24h() -> Dict[str, dict]:
    """Used by the watchlist screener for 24h volume / price change data."""
    exchange = make_exchange()
    try:
        tickers = await exchange.fetch_tickers()
    finally:
        await exchange.close()
    return tickers
