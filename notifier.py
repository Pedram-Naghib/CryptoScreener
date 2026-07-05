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


def _format_detail_value(v) -> str:
    def _fmt_one(x):
        s = str(x)
        if ":" in s:
            tf_part, rest = s.split(":", 1)
            return f"{tf_part.upper()}:{rest}"
        return s.upper() if len(s) <= 3 else s

    if isinstance(v, list):
        return "[" + ", ".join(_fmt_one(x) for x in v) + "]"
    return _fmt_one(v)


def format_scored_alert(
    symbol: str,
    direction: str,
    score: int,
    threshold: int,
    breakdown: list,
    levels: dict = None,
) -> str:
    emoji = "🟢" if direction == "long" else "🔴"
    lines = [
        f"{emoji} *{direction.upper()} Signal — `{symbol}`*",
        f"Confluence Score: *{score}* (threshold: {threshold})",
        "",
        "*Contributing factors:*",
    ]
    for name, pts, details in breakdown:
        detail_str = ", ".join(f"{k}={_format_detail_value(v)}" for k, v in details.items()) if details else ""
        line = f"• {name} (+{pts})"
        if detail_str:
            line += f" — {detail_str}"
        lines.append(line)

    if levels:
        lines.append("")
        lines.append(f"Entry: `{levels['entry_price']:.6f}`")
        lines.append(f"🛑 SL: `{levels['sl_price']:.6f}` ({levels['sl_type']})")
        lines.append(f"🎯 TP: `{levels['tp_price']:.6f}` ({levels['tp_type']})")
        lines.append(f"R:R — *1 : {levels['rr']}*")

    return "\n".join(lines)


def format_signal_closed(record: dict) -> str:
    r = record["result_r"]
    emoji = "✅" if r > 0 else "❌"
    sign = "+" if r >= 0 else ""
    return (
        f"{emoji} *{record['direction'].upper()} Closed — `{record['symbol']}`*\n"
        f"Outcome: {record['outcome'].upper()} @ `{record['exit_price']:.6f}`\n"
        f"Result: *{sign}{r:.2f}R*"
    )


def format_performance_summary(stats: dict, period_label: str) -> str:
    sign = "+" if stats["total_r"] >= 0 else ""
    avg_sign = "+" if stats["avg_r"] >= 0 else ""
    return (
        f"📊 *Performance Summary ({period_label})*\n"
        f"Closed signals: {stats['count']}\n"
        f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
        f"Win rate: {stats['win_rate']:.0f}%\n"
        f"Total: *{sign}{stats['total_r']:.2f}R*\n"
        f"Avg per trade: {avg_sign}{stats['avg_r']:.2f}R"
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