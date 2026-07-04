"""
Telegram Notification Layer
=============================
Only formatting + sending lives here. Strategies and the scoring engine
never talk to Telegram directly.
"""

import logging
from telegram import Bot
from telegram.constants import ParseMode

import config

logger = logging.getLogger("notifier")

_bot = Bot(token=config.TELEGRAM_BOT_TOKEN) if config.TELEGRAM_BOT_TOKEN else None


def format_scored_alert(
    symbol: str,
    direction: str,
    score: int,
    threshold: int,
    breakdown: list,
    tp: dict = None,
) -> str:
    emoji = "🟢" if direction == "long" else "🔴"
    lines = [
        f"{emoji} *{direction.upper()} Signal — `{symbol}`*",
        f"Confluence Score: *{score}* (threshold: {threshold})",
        "",
        "*Contributing factors:*",
    ]
    for name, pts, details in breakdown:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items()) if details else ""
        line = f"• {name} (+{pts})"
        if detail_str:
            line += f" — {detail_str}"
        lines.append(line)

    if tp and tp.get("target_price"):
        lines.append("")
        lines.append(f"🎯 TP target: `{tp['target_price']:.6f}` ({tp['target_type']})")

    return "\n".join(lines)


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