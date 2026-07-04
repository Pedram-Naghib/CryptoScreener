"""
Telegram Notification Layer
=============================
Only formatting + sending lives here. Strategy modules never talk to
Telegram directly -- they return signal dicts that main.py hands to this file.
"""

import logging
from telegram import Bot
from telegram.constants import ParseMode

import config

logger = logging.getLogger("notifier")

_bot = Bot(token=config.TELEGRAM_BOT_TOKEN) if config.TELEGRAM_BOT_TOKEN else None


def _direction_emoji(direction: str) -> str:
    return "🟢" if direction == "long" else "🔴"


def format_module1_alert(symbol: str, timeframe: str, direction: str, price: float, tp: dict) -> str:
    emoji = _direction_emoji(direction)
    tp_line = f"🎯 TP target: `{tp['target_price']:.6f}` ({tp['target_type']})" if tp.get("target_price") else "🎯 TP target: none found"
    return (
        f"{emoji} *Module 1 — FVG/VWAP Convergence*\n"
        f"Symbol: `{symbol}`  TF: `{timeframe}`\n"
        f"Direction: *{direction.upper()}*\n"
        f"Price: `{price:.6f}`\n"
        f"{tp_line}"
    )


def format_module2_alert(symbol: str, timeframe: str, direction: str, price: float, confluence: str, tp: dict) -> str:
    emoji = _direction_emoji(direction)
    tag = "⭐ HIGH CONFLUENCE (double bottom/top)" if confluence == "high_confluence" else "Standard divergence"
    tp_line = f"🎯 TP target: `{tp['target_price']:.6f}` ({tp['target_type']})" if tp.get("target_price") else "🎯 TP target: none found"
    return (
        f"{emoji} *Module 2 — HTF RSI Divergence*\n"
        f"Symbol: `{symbol}`  TF: `{timeframe}`\n"
        f"Direction: *{direction.upper()}*\n"
        f"{tag}\n"
        f"Price: `{price:.6f}`\n"
        f"{tp_line}"
    )


def format_module3_alert(symbol: str, timeframe: str, direction: str, price: float, vol_exhaustion: bool, tp: dict) -> str:
    emoji = _direction_emoji(direction)
    vol_line = "✅ volume exhaustion confirmed" if vol_exhaustion else "⚠️ no volume exhaustion (weaker read)"
    tp_line = f"🎯 TP target: `{tp['target_price']:.6f}` ({tp['target_type']})" if tp.get("target_price") else "🎯 TP target: none found"
    return (
        f"{emoji} *Module 3 — Liquidity Sweep Reversal*\n"
        f"Symbol: `{symbol}`  TF: `{timeframe}`\n"
        f"Direction: *{direction.upper()}*\n"
        f"{vol_line}\n"
        f"Price: `{price:.6f}`\n"
        f"{tp_line}"
    )


async def send_alert(message: str):
    if _bot is None or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured -- printing alert instead:\n" + message)
        return
    try:
        await _bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
