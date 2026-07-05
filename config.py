"""
Central configuration. Nothing strategy-specific lives here except tunable
thresholds -- keep those here so you can tune without touching logic files.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # must run before any os.getenv() calls below

# ---------------------------------------------------------------------------
# Exchange / execution
# ---------------------------------------------------------------------------
EXCHANGE_ID = "kucoinfutures"   # ccxt id for KuCoin Perpetuals
MARKET_TYPE = "swap"            # perpetual futures

# API creds (read-only keys are fine -- this bot never places orders)
API_KEY = os.getenv("KUCOIN_API_KEY", "")
API_SECRET = os.getenv("KUCOIN_API_SECRET", "")
API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE", "")

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Timeframes
# ---------------------------------------------------------------------------
TF_1H = "1h"
TF_4H = "4h"
TF_1D = "1d"
TF_1W = "1w"

MODULE2_TIMEFRAMES = [TF_1D, TF_1W]


# How many candles of history to pull per timeframe (needs enough for
# 20-period vol MA, 14-period RSI, weekly VWAP anchor, etc.)
OHLCV_LIMIT = {
    TF_1H: 500,
    TF_4H: 500,
    TF_1D: 400,
    TF_1W: 200,
}

# ---------------------------------------------------------------------------
# Watchlist / screener (Phase 0)
# ---------------------------------------------------------------------------
USE_LIVE_SCREENER = True        # if False, ONLY use FALLBACK_WATCHLIST
SCREENER_REFRESH_MINUTES = 240  # rebuild the screened list every 4h

MIN_24H_VOLUME_USD = 50_000_000
MIN_RVOL = 1.5                  # current volume vs its own average
RVOL_LOOKBACK_BARS = 20         # bars used to compute "average" volume for RVOL

# Always-scanned pairs regardless of what the screener returns.
# Also the ONLY list used if USE_LIVE_SCREENER = False.
FALLBACK_WATCHLIST = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
]

MAX_WATCHLIST_SIZE = 40  # cap total pairs scanned per cycle (rate-limit safety)

# ---------------------------------------------------------------------------
# Indicator settings
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
RSI_SMA_PERIOD = 14          # SMA applied to the RSI line itself
ATR_PERIOD = 14
VOLUME_MA_PERIOD = 20
EMA_PERIODS = [9, 21, 50, 200]

# ---------------------------------------------------------------------------
# Module 1: FVG + VWAP convergence
# ---------------------------------------------------------------------------
FVG_VOLUME_MULT = 1.5          # expansion candle must be >= 1.5x the vol MA
FVG_PROXIMITY_PCT = 0.003      # alert within 0.3% of the gap
FVG_WICK_ENTRY_PCT = 0.25      # OR price has wicked into top/bottom 25% of gap
FVG_VWAP_TOLERANCE_PCT = 0.005 # "aligning with VWAP" = within 0.5% of the VWAP line

# ---------------------------------------------------------------------------
# Module 2: HTF RSI divergence (+ double bottom/top confluence)
# ---------------------------------------------------------------------------
DIVERGENCE_LOOKBACK_BARS = 20   # max bars between the two pivots being compared
LTF_PIVOT_WINDOW = 3   # pivot left/right window for 1H/4H (fast market, more noise -- tune independently)
HTF_PIVOT_WINDOW = 3   # pivot left/right window for 1D/1W (slower structure -- tune independently)
RSI_SMA_TOUCH_TOLERANCE = 1.0   # RSI within this many points of its SMA counts as "touching"

DOUBLE_PATTERN_TOLERANCE_PCT = 0.008  # the two lows/highs must be within 0.8% of each other

# ---------------------------------------------------------------------------
# EMA Reaction (TP / exit watch signal -- e.g. EMA50 rejection + RSI mid-lane)
# ---------------------------------------------------------------------------
EMA_REACTION_EMA = "ema_50"        # which EMA to watch for reaction (from EMA_PERIODS)
EMA_PROXIMITY_PCT = 0.005          # "price is at the EMA" = within 0.5%
EMA_REJECTION_LOOKBACK_BARS = 150  # how far back to count prior rejections at this EMA
EMA_MIN_PRIOR_REJECTIONS = 2       # need at least this many historical rejections to trust the level
EMA_REJECTION_CONFIRM_BARS = 3     # bars after a touch to check for reversal, when counting history
EMA_REJECTION_MOVE_PCT = 0.01      # min move away from EMA within confirm_bars to count as "rejected"
RSI_MIDLANE_LOW = 45
RSI_MIDLANE_HIGH = 60

# ---------------------------------------------------------------------------
# Deep Discount FVG strategy (scoring matrix Module 1)
# ---------------------------------------------------------------------------
MODULE4_TIMEFRAMES = [TF_4H, TF_1D]
OTE_ZONE_LEVELS = (0.706, 0.790)   # Optimal Trade Entry zone (narrower than the old 0.618 golden pocket)
FIB_SWING_LOOKBACK_BARS = 200        # how far back to find the anchoring swing high/low
MIN_LEG_ATR_MULT = 3.0               # swing leg must be >= this many ATRs to be trusted (filters choppy/ranging noise)

# ---------------------------------------------------------------------------
# Module 3: Liquidity Sweep Reversal
# ---------------------------------------------------------------------------
LSR_BUFFER_ATR_MULT = 0.1
LSR_CONFLUENCE_WINDOW = 5
LSR_REQUIRE_VOLUME_EXHAUSTION = False  # surfaced as info in the alert either way

# ---------------------------------------------------------------------------
# Take-profit logic
# ---------------------------------------------------------------------------
TP_SEARCH_MAX_BARS_BACK = 300  # how far back to look for unmitigated FVGs as targets

# ---------------------------------------------------------------------------
# Stop-loss logic
# ---------------------------------------------------------------------------
SL_STRUCTURE_BUFFER_ATR_MULT = 0.25  # push the SL past the structural swing by this many ATRs
SL_FALLBACK_ATR_MULT = 1.5           # pure ATR-multiple stop, only used if no structural swing exists yet
MIN_RR_RATIO = 1.0                   # don't open/alert a tracked signal if computed R:R is below this

# ---------------------------------------------------------------------------
# Signal tracking / R-multiple performance journal
# ---------------------------------------------------------------------------
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
SIGNAL_STATE_FILE = os.path.join(STATE_DIR, "signals.json")
PERFORMANCE_SUMMARY_INTERVAL_HOURS = 24  # how often to push a performance summary to Telegram

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
SCAN_INTERVAL_SECONDS = 900     # 15 minutes between full scan cycles
MAX_CONCURRENT_FETCHES = 10     # throttle concurrent ccxt calls