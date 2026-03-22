#!/usr/bin/env python3
"""
Polymarket Data Fetcher Module
Fetches market data from Polymarket Gamma and CLOB APIs
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

import requests

from utils.memory_system import load_keyword_performance, save_keyword_performance
from utils.config import (
    MARKET_MIN_LIQUIDITY,
    MARKET_MIN_VOLUME,
    MAX_DAYS_UNTIL_RESOLUTION,
    MID_TERM_DAYS_UPPER,
    DAYS_SWEET_SPOT_LOWER,
    DAYS_SWEET_SPOT_UPPER,
    MAX_MARKETS_PER_FETCH,
    VOLUME_SCORE_1M,
    VOLUME_SCORE_500K,
    VOLUME_SCORE_100K,
    VOLUME_SCORE_50K,
    VOLUME_SCORE_10K,
)

# Base keyword weights - used as defaults and for weight adjustment calculations
BASE_KEYWORD_WEIGHTS = {
    # Politics/Elections
    "election": 30, "trump": 25, "biden": 25, "vote": 20, "poll": 15,
    "congress": 20, "senate": 20, "house": 15, "legislation": 20,
    "war": 25, "ukraine": 20, "russia": 20, "china": 15, "israel": 20,
    "president": 25, "prime minister": 25,

    # Economic/Policy
    "fed": 30, "federal reserve": 30, "interest rate": 30, "inflation": 25, "recession": 25,
    "cpi": 25, "jobs": 15, "unemployment": 20, "gdp": 20,
    "tariff": 25, "tariffs": 25, "trade war": 25, "sanction": 20, "sanctions": 20,
    "gaza": 20, "hamas": 20, "hezbollah": 15, "middle east": 15,

    # Tech/Product launches
    "openai": 30, "gpt": 25, "chatgpt": 25, "llm": 20,
    "tesla": 20, "apple": 20, "google": 20, "microsoft": 20,
    "launch": 15, "release": 15, "announce": 15, "product": 10,
    "ai": 20, "artificial intelligence": 25, "model": 10,

    # Business/Corporate
    "earnings": 25, "revenue": 15, "profit": 15, "ipo": 20,
    "acquisition": 25, "acquire": 25, "merge": 25, "merger": 25, "buyout": 25, "bankruptcy": 25,
    "ceo": 15, "resign": 20, "fired": 20, "appointed": 15,

    # Legal/Regulatory
    "lawsuit": 25, "sec": 25, "fine": 20, "approve": 15, "approval": 15,
    "regulation": 25, "regulations": 25, "ai regulation": 25, "crypto regulation": 25,
    "ban": 20, "legal": 15, "court": 20, "ruling": 20,

    # Crypto/ETF
    "bitcoin": 25, "btc": 25, "ethereum": 25, "eth": 25, "solana": 20, "sol": 20,
    "cardano": 15, "ada": 15, "ripple": 15, "xrp": 15, "binance": 15, "bsc": 15,
    "coinbase": 15, "crypto etf": 20, "bitcoin etf": 20, "ethereum etf": 20,
    "sec approval": 25, "sec denial": 25, "crypto regulation": 25,

    # Weather (meteorological events)
    "hurricane": 25, "storm": 20, "tornado": 20, "flood": 20,
    "drought": 20, "temperature": 15, "heatwave": 20, "cold wave": 20,
    "landfall": 20, "cyclone": 20, "typhoon": 20,

    # Events
    "summit": 20, "conference": 15, "deadline": 20,
    "by": 10, "before": 10, "after": 10, "during": 10,
}

# ==================== FILTERING CONSTANTS ====================
# Allowed categories (whitelist) - only these categories pass through
# If category is missing/empty, fall through to keyword check (don't skip)
ALLOWED_CATEGORIES = {
    'politics', 'elections', 'economics', 'finance', 'business',
    'technology', 'crypto', 'science', 'world', 'geopolitics',
    'government', 'macro', 'policy', 'weather'
}

# Sports/entertainment blacklist - markets with ANY of these are excluded
# regardless of category or other keywords
SPORTS_BLACKLIST = [
    # Sports events
    "world cup", "fifa", "uefa", "copa", "champions league",
    "premier league", "la liga", "bundesliga", "serie a",
    "olympics", "olympic games", "paralympic",
    "super bowl", "nfl", "nba", "mlb", "nhl", "nascar",
    "world series", "stanley cup", "march madness",
    "wimbledon", "us open", "french open", "australian open",
    "masters", "pga", "lpga", "ufc", "mma", "boxing",
    "wrestl", "formula 1", "f1 race", "grand prix",

    # Sports actions
    "qualify for", "qualification", "will win the",
    "championship", "tournament bracket", "playoff",
    "relegation", "promotion", "transfer fee",
    "draft pick", "top scorer", "golden boot",

    # Entertainment/celebrity
    "grammy", "oscar", "emmy", "box office",
    "billboard", "album", "chart", "tour",
    "reality show", "game show",
    "married", "divorce", "dating",
]


def fetch_gamma_markets(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Fetch active markets from Polymarket Gamma API.

    Args:
        limit: Maximum number of markets to fetch (default 100)

    Returns:
        List of market dictionaries
    """
    url = f"https://gamma-api.polymarket.com/markets?closed=false&active=true&liquidityMin={MARKET_MIN_LIQUIDITY}&limit={limit}"

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    markets = response.json()
    return markets if isinstance(markets, list) else []


def filter_active_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter markets by volume, end date, category, and exclude sports/entertainment.

    Filters:
    - volume > $5k
    - end date <= 60 days from now
    - Category whitelist (politics, economics, finance, business, technology, crypto, weather)
    - Sports/entertainment blacklist (checked BEFORE included keywords to catch sports with political names)
    - Included keywords (breaking news, politics, finance, etc.)

    Returns:
        Filtered list of markets with enriched data
    """
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=MAX_DAYS_UNTIL_RESOLUTION)
    filtered = []

    # Debug counters
    debug_counts = {
        'total_fetched': len(markets),
        'volume_filter': 0,
        'category_filter': 0,
        'sports_blacklist': 0,
        'keyword_filter': 0,
        'end_date_filter': 0,
        'parsing_errors': 0,
        'passed': 0
    }

    for m in markets:
        try:
            # Volume filter
            volume = float(m.get("volume", 0))
            if volume < MARKET_MIN_VOLUME:
                debug_counts['volume_filter'] += 1
                continue

            # Get title for keyword filtering
            title_lower = m.get("question", "").lower()
            description_lower = m.get("description", "").lower()
            combined_text = title_lower + " " + description_lower

            # CATEGORY WHITELIST FILTER (if category is present and non-empty)
            # Allow markets with missing/empty category to fall through to keyword check
            market_category = m.get("category", "").strip().lower()
            if market_category:
                if market_category not in ALLOWED_CATEGORIES:
                    debug_counts['category_filter'] += 1
                    continue

            # SPORTS/ENTERTAINMENT BLACKLIST - checked EARLY (before keyword inclusion)
            # This catches sports markets that contain political country names (e.g., "Ukraine qualify for World Cup")
            if any(blacklist in combined_text for blacklist in SPORTS_BLACKLIST):
                debug_counts['sports_blacklist'] += 1
                continue

            # EXCLUDE: Entertainment only (remaining ones not in sports blacklist)
            excluded_keywords = [
                # Entertainment/Celebrity
                "album", "music", "song", "movie", "film", "netflix",
                "rihanna", "drake", "taylor swift", "beyonce",
                "jesus christ", "rapture", "armageddon", "apocalypse"
            ]
            if any(keyword in combined_text for keyword in excluded_keywords):
                debug_counts['keyword_filter'] += 1
                continue

            # INCLUDE: Breaking news, Politics, Finance, Economy, Elections, Popular Crypto, Weather
            # Note: Weather events already in BASE_KEYWORD_WEIGHTS
            included_keywords = [
                # Breaking news
                "breaking", "urgent", "developing", "just announced",
                # Politics
                "trump", "biden", "president", "white house", "congress",
                "senate", "house", "legislation", "bill", "policy",
                "supreme court", "federal", "government", "minister",
                "prime minister", "parliament", "war", "ceasefire",
                "ukraine", "russia", "china", "taiwan", "israel", "gaza", "hamas", "hezbollah",
                # Finance
                "fed", "federal reserve", "interest rate", "rate hike",
                "rate cut", "fomc", "treasury", "bank", "earnings",
                "revenue", "profit", "ipo", "merger", "acquisition",
                "bankruptcy", "stock", "shares", "sec", "lawsuit",
                "ceo", "executive", "resign", "fired", "board",
                "quarterly", "fiscal", "dividend",
                # Economy
                "gdp", "recession", "inflation", "cpi", "economic",
                "unemployment", "jobs", "labor market", "trade",
                "tariff", "tariffs", "sanction", "sanctions", "trade war",
                # Elections
                "election", "vote", "voting", "ballot", "polling",
                "electoral", "campaign", "candidate", "presidential race",
                # Crypto
                "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
                "cardano", "ada", "ripple", "xrp", "binance", "bsc",
                "coinbase", "crypto etf", "bitcoin etf", "ethereum etf",
                "sec approval", "sec denial", "crypto regulation",
                # Weather (from BASE_KEYWORD_WEIGHTS)
                "hurricane", "storm", "tornado", "flood", "drought",
                "temperature", "heatwave", "cold wave", "landfall",
                "cyclone", "typhoon",
            ]

            # Only keep if it matches at least one INCLUDED keyword
            if not any(keyword in combined_text for keyword in included_keywords):
                debug_counts['keyword_filter'] += 1
                continue

            # End date filter
            end_date_str = m.get("endDate", "")
            if end_date_str:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                # Skip if end date is in the past (market already finished)
                if end_date < datetime.now(timezone.utc):
                    debug_counts['end_date_filter'] += 1
                    continue
                # Skip if end date is too far in the future
                if end_date > cutoff_date:
                    debug_counts['end_date_filter'] += 1
                    continue

            # Parse prices
            outcome_prices = m.get("outcomePrices", "[0, 0]")
            prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices

            yes_price = float(prices[0]) * 100 if isinstance(prices, list) else 50
            no_price = float(prices[1]) * 100 if isinstance(prices, list) else 50

            # Get event slug for URL construction
            events = m.get("events", [])
            event_slug = events[0].get("slug", "") if events else ""
            market_slug = m.get("slug", "")

            # Construct URL: /event/{event_slug}/{market_slug} or fallback
            if event_slug and market_slug:
                url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
            else:
                url = f"https://polymarket.com/market/{market_slug}"

            filtered.append({
                "title": m.get("question", ""),
                "slug": market_slug,
                "event_slug": event_slug,
                "conditionId": m.get("conditionId", ""),
                "url": url,
                "volume": volume,
                "yes_price": yes_price,
                "no_price": no_price,
                "category": m.get("category", "other"),
                "end_date": end_date_str,
                "description": m.get("description", "")
            })
            debug_counts['passed'] += 1

        except Exception as e:
            debug_counts['parsing_errors'] += 1
            # Silently skip parsing errors but count them
            continue

    # Print filtering summary (ASCII-safe for Windows)
    print("\n[FILTERING DEBUG]")
    print(f"  Total markets fetched: {debug_counts['total_fetched']}")
    print(f"  [OK] Passed all filters: {debug_counts['passed']}")
    print(f"  [SKIP] Volume filter: {debug_counts['volume_filter']}")
    print(f"  [SKIP] Category filter (wrong category): {debug_counts['category_filter']}")
    print(f"  [SKIP] Sports blacklist: {debug_counts['sports_blacklist']}")
    print(f"  [SKIP] Keyword filter (no relevant keywords): {debug_counts['keyword_filter']}")
    print(f"  [SKIP] End date filter: {debug_counts['end_date_filter']}")
    print(f"  [SKIP] Parsing errors: {debug_counts['parsing_errors']}")
    print("[/FILTERING DEBUG]\n")

    return filtered


def get_market_orderbook(market_id: str) -> Dict[str, Any]:
    """
    Fetch orderbook data from Polymarket CLOB API.

    Args:
        market_id: The conditionId/tokenId of the market

    Returns:
        Orderbook data with bids and asks
    """
    url = f"https://clob.polymarket.com/book?token_id={market_id}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"bids": [], "asks": [], "error": f"Status {response.status_code}"}
    except Exception as e:
        return {"bids": [], "asks": [], "error": str(e)}


def get_spread(market_id: str) -> Dict[str, Any]:
    """
    Calculate bid-ask spread for a market.

    Args:
        market_id: The conditionId/tokenId of the market

    Returns:
        Dict with spread info: spread (as decimal), best_bid, best_ask, mid_price
    """
    orderbook = get_market_orderbook(market_id)

    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    if not bids or not asks:
        return {
            "spread": 0.10,  # Default high spread if no data
            "best_bid": 0.0,
            "best_ask": 1.0,
            "mid_price": 0.5,
            "has_data": False
        }

    try:
        best_bid = float(bids[0].get("price", 0))
        best_ask = float(asks[0].get("price", 1))

        spread = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2

        return {
            "spread": spread,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "has_data": True
        }
    except (ValueError, IndexError):
        return {
            "spread": 0.10,
            "best_bid": 0.0,
            "best_ask": 1.0,
            "mid_price": 0.5,
            "has_data": False
        }


def get_dynamic_keyword_weight(keyword: str, default_weight: int) -> float:
    """
    Calculate dynamic weight for a keyword based on its historical performance.

    Formula:
    - If keyword has >= 3 samples: weight = default × (win_rate / 0.5)
    - Clamp multiplier between 0.5x and 2.0x
    - If keyword not tracked or samples < 3: return default weight

    Args:
        keyword: The keyword to look up
        default_weight: The base weight for this keyword

    Returns:
        Adjusted weight based on historical performance
    """
    performance_data = load_keyword_performance()

    if keyword not in performance_data:
        return float(default_weight)

    keyword_data = performance_data[keyword]
    samples = keyword_data.get("samples", 0)

    if samples < 3:
        return float(default_weight)

    win_rate = keyword_data.get("win_rate", 0.5)

    # Calculate multiplier: win_rate / 0.5 (baseline)
    # 50% win rate = 1.0x (no change)
    # 75% win rate = 1.5x (increase)
    # 25% win rate = 0.5x (decrease)
    multiplier = win_rate / 0.5

    # Clamp between 0.5x and 2.0x
    multiplier = max(0.5, min(2.0, multiplier))

    return float(default_weight * multiplier)


def update_keyword_performance(market_title: str, outcome: str):
    """
    Update keyword performance tracking when a bet resolves.

    Args:
        market_title: The title of the market that resolved
        outcome: 'WIN' or 'LOSS' indicating whether our prediction was correct
    """
    title_lower = market_title.lower()
    performance_data = load_keyword_performance()

    # Check each base keyword against the market title
    for keyword in BASE_KEYWORD_WEIGHTS:
        if keyword in title_lower:
            # Initialize keyword data if not exists
            if keyword not in performance_data:
                performance_data[keyword] = {
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "total_score": 0,
                    "samples": 0
                }

            keyword_data = performance_data[keyword]

            # Update counts
            if outcome == "WIN":
                keyword_data["wins"] += 1
            else:
                keyword_data["losses"] += 1

            # Recalculate derived metrics
            total = keyword_data["wins"] + keyword_data["losses"]
            keyword_data["samples"] = total
            keyword_data["win_rate"] = keyword_data["wins"] / total if total > 0 else 0.0
            keyword_data["total_score"] = keyword_data["wins"] * BASE_KEYWORD_WEIGHTS[keyword]

    # Save updated performance data
    save_keyword_performance(performance_data)


def score_market_predictability(market: Dict[str, Any]) -> float:
    """
    Score how well a market can be predicted from news headlines.
    Higher score = more news-predictable.

    Uses dynamic weights based on historical keyword performance.

    Scoring criteria:
    - Category priority (news-driven vs random)
    - Price range (markets near 50% most interesting)
    - Keywords indicating news-relevance (dynamically weighted)
    - Time horizon (not too far, not too soon)
    """
    score = 0.0
    title = market.get("title", "").lower()
    category = market.get("category", "other").lower()

    # Category priority (news-driven outcomes)
    category_scores = {
        "politics": 100,      # Elections, legislation - highly predictable from news
        "economics": 90,      # Fed rates, economic indicators - news-driven
        "business": 80,       # M&A, earnings - news-driven
        "technology": 75,     # AI launches, product releases - predictable
        "crypto": 30,         # Hard to predict from news, prices are random
        "sports": 10,         # Games happen, news is just reporting
        "entertainment": 20,  # Subjective, hard to predict
        "science": 70,        # Research breakthroughs - somewhat predictable
        "weather": 10,        # Random, news doesn't help predict
    }
    score += category_scores.get(category, 40)

    # ==================== PRIORITY BONUSES ====================
    # These bonuses steer selection toward high-impact, news-driven markets
    title_lower = market.get("title", "").lower()

    # +25: Election/government leadership keywords
    election_keywords = [
        "election", "vote", "ballot", "referendum", "president",
        "prime minister", "congress", "senate", "parliament", "chancellor"
    ]
    if any(kw in title_lower for kw in election_keywords):
        score += 25

    # +20: Central bank/economic policy keywords
    econ_keywords = [
        "fed", "federal reserve", "interest rate", "inflation",
        "gdp", "recession", "tariff", "sanctions", "central bank", "fomc"
    ]
    if any(kw in title_lower for kw in econ_keywords):
        score += 20

    # +15: Geopolitical conflict/security keywords
    geo_keywords = [
        "war", "ceasefire", "invasion", "nuclear",
        "treaty", "alliance", "nato", "coup", "protest"
    ]
    if any(kw in title_lower for kw in geo_keywords):
        score += 15

    # +10: Regulatory/legislative keywords
    reg_keywords = [
        "regulation", "ban", "law", "bill", "policy",
        "approve", "reject", "veto", "legislation"
    ]
    if any(kw in title_lower for kw in reg_keywords):
        score += 10

    # +5: Crypto regulatory keywords (distinguish from price predictions)
    crypto_keywords = [
        "bitcoin", "ethereum", "crypto", "sec",
        "approval", "etf"
    ]
    if any(kw in title_lower for kw in crypto_keywords):
        score += 5

    # -50: Sports blacklist (belt and suspenders – already filtered but penalize if slipped through)
    if any(blacklist in title_lower for blacklist in SPORTS_BLACKLIST):
        score -= 50

    # ==================== END PRIORITY BONUSES ====================

    # Apply dynamic weights based on keyword performance
    for keyword, default_points in BASE_KEYWORD_WEIGHTS.items():
        if keyword in title:
            dynamic_weight = get_dynamic_keyword_weight(keyword, default_points)
            score += dynamic_weight

    # Price factor - markets near 50% are most interesting (highest uncertainty)
    yes_price = market.get("yes_price", 50)
    distance_from_50 = abs(yes_price - 50)
    # Closer to 50 = higher score (max 20 points)
    score += max(0, 20 - distance_from_50 * 0.4)

    # Volume factor - higher volume = more confidence (max 10 points)
    volume = market.get("volume", 0)
    if volume > VOLUME_SCORE_1M:
        score += 10
    elif volume > VOLUME_SCORE_500K:
        score += 7
    elif volume > VOLUME_SCORE_100K:
        score += 5
    elif volume > VOLUME_SCORE_50K:
        score += 3
    elif volume > VOLUME_SCORE_10K:
        score += 1

    # Time horizon - ideal is 2-8 weeks out (news coverage peak)
    end_date_str = market.get("end_date", "")
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            days_until = (end_date - datetime.now(timezone.utc)).days

            if DAYS_SWEET_SPOT_LOWER <= days_until <= DAYS_SWEET_SPOT_UPPER:  # 2-8 weeks - sweet spot
                score += 15
            elif 7 <= days_until < DAYS_SWEET_SPOT_LOWER:  # 1-2 weeks
                score += 10
            elif MAX_DAYS_UNTIL_RESOLUTION < days_until <= MID_TERM_DAYS_UPPER:  # 2-4 months
                score += 5
            elif days_until < 7:  # Less than a week - may be decided
                score -= 10
            else:  # Far future - low news coverage
                score -= 5
        except:
            pass

    return score


def prioritize_markets_for_news_prediction(markets: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    """
    Select markets that are most predictable from news headlines.

    Args:
        markets: List of filtered markets
        top_n: Number of markets to return

    Returns:
        Top N markets sorted by news-predictability score
    """
    # Score each market
    scored_markets = []
    for market in markets:
        score = score_market_predictability(market)
        scored_markets.append((score, market))

    # Sort by score descending
    scored_markets.sort(key=lambda x: x[0], reverse=True)

    # Return top N
    return [market for score, market in scored_markets[:top_n]]


def fetch_filtered_markets(top_n: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch and filter markets, prioritizing news-predictable ones.

    Args:
        top_n: Number of top-scored markets to return (default 100)
              Higher number ensures enough markets after exclusions

    Returns:
        Top N markets most predictable from news headlines
    """
    markets = fetch_gamma_markets(limit=MAX_MARKETS_PER_FETCH)
    filtered = filter_active_markets(markets)

    if len(filtered) <= top_n:
        return filtered

    return prioritize_markets_for_news_prediction(filtered, top_n=top_n)


if __name__ == "__main__":
    # Test the module
    print("Testing Polymarket Data Fetcher...")

    markets = fetch_gamma_markets(limit=50)
    print(f"Fetched {len(markets)} markets")

    filtered = filter_active_markets(markets[:10])
    print(f"After filtering: {len(filtered)} markets")

    if filtered:
        test_market = filtered[0]
        print(f"\nTest market: {test_market['title'][:50]}...")

        spread_info = get_spread(test_market["conditionId"])
        print(f"Spread: {spread_info['spread']:.4f}")
        print(f"Best bid: {spread_info['best_bid']:.2f}")
        print(f"Best ask: {spread_info['best_ask']:.2f}")
