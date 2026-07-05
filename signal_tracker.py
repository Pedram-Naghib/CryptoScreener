"""
Signal Tracker -- persistent R-multiple performance journal
==============================================================
Owns the on-disk record of every signal the bot has opened: entry/SL/TP,
whether it's still open, and (once closed) whether TP or SL was hit and the
resulting R-multiple.

This is also what powers alert dedup: main.py checks has_open_signal()
before firing a new alert, so you don't get re-alerted every 15 minutes on
a symbol/direction that's already being tracked.

State lives in a single JSON file (config.SIGNAL_STATE_FILE). Every public
function is async and goes through the module-level asyncio.Lock, since
main.py processes symbols concurrently via asyncio.gather and file writes
must not interleave.

R-multiple convention:
  - A signal closed at SL is always recorded as exactly -1.0R -- the SL
    distance IS the 1R risk unit, by definition.
  - A signal closed at TP is recorded at its pre-computed R:R ratio (e.g. a
    signal opened with a 1:2.3 R:R that hits TP records as +2.3R).
  - CAVEAT: if a single candle's high/low range contains BOTH the SL and TP
    price, we cannot know which was actually touched first intrabar. We
    conservatively assume SL was hit first (standard risk-management
    assumption -- never assume the better outcome). If this fires often for
    a given symbol, your SL/TP are likely too tight for the 1H timeframe
    being used to check them.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import config

logger = logging.getLogger("signal_tracker")

_lock = asyncio.Lock()

_EMPTY_STATE = {"open": {}, "closed": [], "meta": {"last_summary_sent_at": None}}


def _ensure_state_dir():
    os.makedirs(config.STATE_DIR, exist_ok=True)


def _load() -> dict:
    _ensure_state_dir()
    if not os.path.exists(config.SIGNAL_STATE_FILE):
        return {"open": {}, "closed": [], "meta": {"last_summary_sent_at": None}}
    with open(config.SIGNAL_STATE_FILE) as f:
        return json.load(f)


def _save(state: dict):
    _ensure_state_dir()
    # write-then-rename so a crash mid-write can't corrupt the live file
    tmp_path = config.SIGNAL_STATE_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp_path, config.SIGNAL_STATE_FILE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def has_open_signal(symbol: str, direction: str) -> bool:
    async with _lock:
        state = _load()
        return any(
            s["symbol"] == symbol and s["direction"] == direction
            for s in state["open"].values()
        )


async def get_open_symbols() -> set:
    async with _lock:
        state = _load()
        return {s["symbol"] for s in state["open"].values()}


async def open_signal(symbol: str, direction: str, levels: dict, score: int) -> dict:
    """levels: the dict returned by scoring_engine.suggest_trade_levels_for_direction."""
    async with _lock:
        state = _load()
        sig_id = uuid.uuid4().hex[:12]
        record = {
            "id": sig_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": levels["entry_price"],
            "sl_price": levels["sl_price"],
            "sl_type": levels["sl_type"],
            "tp_price": levels["tp_price"],
            "tp_type": levels["tp_type"],
            "rr": levels["rr"],
            "score_at_entry": score,
            "opened_at": _now_iso(),
        }
        state["open"][sig_id] = record
        _save(state)
        logger.info(f"Opened {direction} signal {sig_id} on {symbol} (R:R {levels['rr']})")
        return record


def _close(state: dict, sig_id: str, exit_price: float, outcome: str, result_r: float) -> dict:
    record = state["open"].pop(sig_id)
    record.update(
        {
            "status": f"closed_{outcome}",
            "outcome": outcome,
            "exit_price": exit_price,
            "result_r": result_r,
            "closed_at": _now_iso(),
        }
    )
    state["closed"].append(record)
    logger.info(f"Closed signal {sig_id} on {record['symbol']}: {outcome} -> {result_r:+.2f}R")
    return record


async def check_symbol_signals(symbol: str, df_1h) -> list:
    """
    Checks every open signal for `symbol` against the latest 1H candle's
    high/low. Returns a list of newly-closed records (empty if none hit).
    """
    if df_1h is None or df_1h.empty:
        return []

    last = df_1h.iloc[-1]
    high, low = float(last["high"]), float(last["low"])
    closed = []

    async with _lock:
        state = _load()
        for sig_id, sig in list(state["open"].items()):
            if sig["symbol"] != symbol:
                continue

            direction = sig["direction"]
            if direction == "long":
                sl_hit = low <= sig["sl_price"]
                tp_hit = high >= sig["tp_price"]
            else:
                sl_hit = high >= sig["sl_price"]
                tp_hit = low <= sig["tp_price"]

            if sl_hit:  # conservative tie-break when both hit in the same candle -- see module docstring
                closed.append(_close(state, sig_id, sig["sl_price"], "sl", -1.0))
            elif tp_hit:
                closed.append(_close(state, sig_id, sig["tp_price"], "tp", sig["rr"]))

        if closed:
            _save(state)

    return closed


async def get_performance_summary(hours: int = None) -> dict:
    """hours=None returns all-time stats; otherwise only signals closed within the window."""
    async with _lock:
        state = _load()

    closed = state["closed"]
    if hours is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        closed = [c for c in closed if datetime.fromisoformat(c["closed_at"]).timestamp() >= cutoff]

    count = len(closed)
    wins = sum(1 for c in closed if c["result_r"] > 0)
    losses = sum(1 for c in closed if c["result_r"] <= 0)
    total_r = sum(c["result_r"] for c in closed)

    return {
        "count": count,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / count * 100) if count else 0.0,
        "total_r": total_r,
        "avg_r": (total_r / count) if count else 0.0,
    }


async def should_send_summary() -> bool:
    async with _lock:
        state = _load()
        last = state.get("meta", {}).get("last_summary_sent_at")
        if last is None:
            return True
        elapsed_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600
        return elapsed_hours >= config.PERFORMANCE_SUMMARY_INTERVAL_HOURS


async def mark_summary_sent():
    async with _lock:
        state = _load()
        state.setdefault("meta", {})["last_summary_sent_at"] = _now_iso()
        _save(state)