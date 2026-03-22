#!/usr/bin/env python3
"""
Centralized configuration constants.
All magic numbers and thresholds should be defined here.
"""

# ==================== Risk Classification ====================
# Edge thresholds (percentage points)
LOW_RISK_EDGE_HIGH_CONF = 3.0   # high confidence, edge >= this is low risk
LOW_RISK_EDGE_MED_CONF = 5.0    # medium confidence, edge >= this is low risk
# Note: high risk is anything not meeting low risk criteria

# Bet selection counts
MAX_LOW_RISK_BETS = 5
MAX_HIGH_RISK_BETS = 5

# ==================== Insider Detection ====================
INSIDER_STRONG_THRESHOLD = 70         # score >= 70 is strong insider signal
INSIDER_WEAK_THRESHOLD = 40           # score < 40 is ignored (40-70 weak)
INSIDER_BOOST_PROBABILITY = 10        # increase estimated probability by 10 points
INSIDER_REDUCE_PROBABILITY = 10      # decrease estimated probability by 10 points
INSIDER_MAX_PROBABILITY = 95          # upper cap after boost
INSIDER_MIN_PROBABILITY = 5           # lower cap after reduce
INSIDER_FOLLOW_THRESHOLD = 70         # score >= 70 triggers FOLLOW_INSIDER

# ==================== Whale Tracking ====================
WHALE_MIN_ORDER_SIZE = 5000           # minimum USD order size to consider

# Wallet history thresholds (hours)
WHALE_WALLET_AGE_FRESH_HOURS = 24     # < 24h = fresh wallet (+30 points)
WHALE_WALLET_AGE_NEW_HOURS = 168      # < 1 week = new wallet (+15 points)

# Trader performance thresholds
WHALE_WIN_RATE_HIGH = 0.80            # win rate >= 80% (+30 points)
WHALE_WIN_RATE_GOOD = 0.65            # win rate >= 65% (+15 points)

# Position concentration
WHALE_POSITION_CONCENTRATION_MAX = 2  # open positions <= 2 considered concentrated (+10 points)
WHALE_CONCENTRATED_BET_VOLUME = 10000
WHALE_NEW_WALLET_VOLUME = 10000  # for new wallets: total_volume >= $10k (+30) # for new wallets: total_volume >= $10k (+30)

# Volume thresholds for scoring
WHALE_MIN_TRADES_FOR_VOLUME = 5       # need >=5 trades to consider avg size
WHALE_LARGE_BET_AVG_SIZE = 5000       # average order size >= $5k (+20 points)
WHALE_LARGE_BET_TOTAL_VOLUME = 20000  # total volume >= $20k (bonus +20)

# Known insider bonus
WHALE_KNOWN_INSIDER_BONUS = 50        # additional points if wallet in known list

# Insider score filtering
WHALE_INSIDER_SCORE_FILTER = 40       # skip if final score < 40

# Position ratio for bullish/bearish detection
WHALE_BULLISH_RATIO = 1.5             # buy_value > sell_value * 1.5 => BULLISH
WHALE_BEARISH_RATIO = 1.5             # sell_value > buy_value * 1.5 => BEARISH

# Confidence scoring
CONFIDENCE_PER_ORDER = 10             # 10 points per order (max 10 orders = 100)
CONFIDENCE_BONUS_LARGE_VOLUME = 20    # bonus added when total_value > LARGE_VOLUME_THRESHOLD
MAX_CONFIDENCE_SCORE = 100            # maximum confidence cap
LARGE_VOLUME_THRESHOLD = 100000       # total_value > $100k triggers bonus

# ==================== Panel Voting ====================
# Consensus thresholds (out of 4 agents)
PANEL_STRONG_MAJORITY = 3             # >=3 votes for same direction = strong
PANEL_MODERATE_MAJORITY = 2           # >=2 votes = moderate (but <3)

# Agent default accuracies (used when no historical data)
DEFAULT_AGENT_ACCURACY = 50.0         # fallback accuracy percentage

# Minimum edge threshold for placing bets (percentage points)
MIN_EDGE_THRESHOLD = 10.0

# ==================== Kelly Calculator ====================
MIN_STAKE_USD = 10.0
MAX_STAKE_USD = 100.0

# ==================== Timing & Retries ====================
CYCLE_INTERVAL_SECONDS = 3600         # 1 hour between cycles
RETRY_DELAY_SECONDS = 300             # 5 minutes wait after cycle error
DEFAULT_RATE_LIMIT_DELAY = 10         # base delay for rate limit backoff (seconds)

# ==================== API Rate Limits (seconds) ====================
RATE_LIMIT_GROQ = 2.0
RATE_LIMIT_CEREBRAS = 2.0
RATE_LIMIT_MISTRAL = 2.0
RATE_LIMIT_OPENROUTER = 5.0
RATE_LIMIT_GEMINI = 2.0
# Ollama: no rate limit (local)

# ==================== Concurrency ====================
MAX_CONCURRENT_LLM_CALLS = 6

# ==================== Kalshi Matching ====================
KALSHI_STRONG_GAP = 15.0      # percentage gap >= 15% => STRONG signal
KALSHI_MODERATE_GAP = 8.0     # 8-15% => MODERATE
KALSHI_MIN_MATCH_SCORE = 6    # minimum entity match score (raised to avoid false positives from sports markets)

# Entity weights for matching (used in kalshi_fetcher)
KALSHI_ENTITY_WEIGHTS = {
    "trump": 8,
    "biden": 8,
    "fed": 7,
    "bitcoin": 6,
    "btc": 6,
    "ethereum": 5,
    "eth": 5,
    "crypto": 4,
    "economy": 3,
    "weather": 2,
    "elections": 5,
    "sports": 1
}

# ==================== Market Data Fetching ====================
MARKET_MIN_LIQUIDITY = 500           # minimum liquidity filter (USD)
MARKET_MIN_VOLUME = 5000             # minimum trading volume (USD)
MAX_DAYS_UNTIL_RESOLUTION = 365      # maximum days until resolution (1 year - captures elections, Fed, etc.)
MID_TERM_DAYS_UPPER = 180            # upper bound for medium-term markets (60-180 days)
DAYS_SWEET_SPOT_LOWER = 14           # ideal range lower bound (2-8 weeks)
DAYS_SWEET_SPOT_UPPER = 60           # ideal range upper bound
MAX_MARKETS_PER_FETCH = 200          # limit for Gamma API fetch

# Volume scoring thresholds (for market prioritization)
VOLUME_SCORE_1M = 1000000           # +10 points
VOLUME_SCORE_500K = 500000          # +7 points
VOLUME_SCORE_100K = 100000          # +5 points
VOLUME_SCORE_50K = 50000            # +3 points
VOLUME_SCORE_10K = 10000            # +1 point

# ==================== Whale Tracking ====================
CONFIDENCE_PER_ORDER = 10            # confidence points per order (max 100/10=10 orders)
CONFIDENCE_BONUS_LARGE_VOLUME = 20   # bonus when total_value > LARGE_VOLUME_THRESHOLD
MAX_CONFIDENCE_SCORE = 100           # maximum confidence score cap

# ==================== Kelly Calculator ====================
DEFAULT_KELLY_BASE_FRACTION = 0.5    # base Kelly fraction multiplier
DEFAULT_BANKROLL = 500.0             # default trading bankroll (USD)
