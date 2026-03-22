#!/usr/bin/env python3
"""
Kalshi Fetcher Module
Fetches market data from Kalshi (CFTC-regulated prediction market)
No authentication required - data is fully public.
"""

import re
import requests
from typing import Dict, List, Any, Set, Tuple

from utils.config import MAX_MARKETS_PER_FETCH, KALSHI_MIN_MATCH_SCORE, KALSHI_STRONG_GAP, KALSHI_MODERATE_GAP, KALSHI_ENTITY_WEIGHTS


# Named entities with their weights and aliases for matching
NAMED_ENTITIES = {
    # People - Politics (HIGH weights for key figures)
    "trump": {"weight": 12, "aliases": ["donald trump", "donald j trump", "president trump", "trump's"]},
    "biden": {"weight": 12, "aliases": ["joe biden", "joseph biden", "president biden", "biden's"]},
    "harris": {"weight": 11, "aliases": ["kamala harris", "vp harris", "vice president harris", "kamala"]},
    "musk": {"weight": 7, "aliases": ["elon musk", "elon"]},
    "powell": {"weight": 10, "aliases": ["jerome powell", "chairman powell", "fed chair"]},
    "netanyahu": {"weight": 7, "aliases": ["bibi", "benjamin netanyahu"]},
    "zelensky": {"weight": 7, "aliases": ["zelenskyy", "volodymyr zelensky"]},
    "putin": {"weight": 7, "aliases": ["vladimir putin"]},
    "xi": {"weight": 7, "aliases": ["xi jinping", "president xi"]},
    "macron": {"weight": 6, "aliases": ["emmanuel macron"]},
    "merz": {"weight": 6, "aliases": ["friedrich merz"]},
    "scholz": {"weight": 6, "aliases": ["olaf scholz"]},
    "milei": {"weight": 6, "aliases": ["javier milei"]},

    # Organizations
    "fed": {"weight": 11, "aliases": ["federal reserve", "fomc", "federal reserve board", "the fed"]},
    "sec": {"weight": 8, "aliases": ["securities and exchange commission"]},
    "openai": {"weight": 7, "aliases": ["open ai"]},
    "tesla": {"weight": 6, "aliases": ["tsla"]},
    "apple": {"weight": 6, "aliases": ["aapl"]},
    "google": {"weight": 6, "aliases": ["alphabet", "googl", "goog"]},
    "microsoft": {"weight": 6, "aliases": ["msft"]},
    "amazon": {"weight": 6, "aliases": ["amzn"]},
    "meta": {"weight": 6, "aliases": ["facebook", "instagram", "whatsapp"]},
    "nvidia": {"weight": 6, "aliases": ["nvda"]},
    "spacex": {"weight": 6, "aliases": ["space x"]},
    "nasdaq": {"weight": 5, "aliases": []},
    "nyse": {"weight": 5, "aliases": []},
    "ec": {"weight": 7, "aliases": ["european commission", "european council"]},

    # Countries/Regions
    "usa": {"weight": 5, "aliases": ["united states", "america", "us", "u.s.", "u.s.a."]},
    "china": {"weight": 6, "aliases": ["prc", "people's republic of china", "mainland china"]},
    "russia": {"weight": 6, "aliases": ["russian federation"]},
    "ukraine": {"weight": 6, "aliases": []},
    "israel": {"weight": 6, "aliases": ["israeli"]},
    "taiwan": {"weight": 6, "aliases": ["roc", "republic of china"]},
    "iran": {"weight": 6, "aliases": []},
    "uk": {"weight": 5, "aliases": ["united kingdom", "britain", "great britain"]},
    "eu": {"weight": 5, "aliases": ["european union", "europe"]},
    "germany": {"weight": 5, "aliases": ["german", "deutschland"]},
    "france": {"weight": 5, "aliases": ["french"]},
    "japan": {"weight": 5, "aliases": ["japanese"]},
    "india": {"weight": 5, "aliases": ["indian"]},
    "brazil": {"weight": 5, "aliases": ["brazilian"]},
    "mexico": {"weight": 5, "aliases": ["mexican"]},
    "canada": {"weight": 5, "aliases": ["canadian"]},
    "korea": {"weight": 5, "aliases": ["south korea", "north korea", "korean"]},
    "argentina": {"weight": 5, "aliases": ["argentine"]},

    # Cryptocurrencies
    "btc": {"weight": 8, "aliases": ["bitcoin", "xbt"]},
    "bitcoin": {"weight": 8, "aliases": ["btc"]},
    "eth": {"weight": 8, "aliases": ["ethereum", "ether"]},
    "ethereum": {"weight": 8, "aliases": ["eth"]},
    "sol": {"weight": 6, "aliases": ["solana"]},
    "solana": {"weight": 6, "aliases": ["sol"]},
    "ada": {"weight": 5, "aliases": ["cardano"]},
    "cardano": {"weight": 5, "aliases": ["ada"]},
    "xrp": {"weight": 5, "aliases": ["ripple"]},
    "ripple": {"weight": 5, "aliases": ["xrp"]},
    "bnb": {"weight": 5, "aliases": ["binance", "binance coin"]},
    "avax": {"weight": 5, "aliases": ["avalanche"]},
    "doge": {"weight": 5, "aliases": ["dogecoin"]},
    "crypto": {"weight": 4, "aliases": ["cryptocurrency", "cryptocurrencies", "digital asset"]},

    # Events/Political terms
    "election": {"weight": 10, "aliases": ["electoral", "general election", "presidential election", "midterm"]},
    "vote": {"weight": 9, "aliases": ["voting", "ballot", "referendum", "poll"]},
    "president": {"weight": 9, "aliases": ["presidential", "presidency"]},
    "inauguration": {"weight": 7, "aliases": []},
    "war": {"weight": 8, "aliases": ["conflict", "military action", "invasion", "hostilities"]},
    "ceasefire": {"weight": 8, "aliases": ["cease fire", "truce", "peace agreement"]},
    "gdp": {"weight": 8, "aliases": ["gross domestic product", "economic growth"]},
    "cpi": {"weight": 8, "aliases": ["consumer price index", "inflation rate"]},
    "inflation": {"weight": 8, "aliases": ["deflation", "price level"]},
    "recession": {"weight": 8, "aliases": ["economic contraction", "downturn"]},
    "unemployment": {"weight": 8, "aliases": ["jobless", "unemployment rate", "jobs report"]},
    "tariff": {"weight": 8, "aliases": ["tariffs", "trade barrier", "import tax"]},
    "sanction": {"weight": 8, "aliases": ["sanctions", "embargo"]},
    "trade war": {"weight": 8, "aliases": ["trade dispute", "trade conflict"]},
    "brexit": {"weight": 6, "aliases": []},
    "nato": {"weight": 5, "aliases": []},
    "wto": {"weight": 5, "aliases": ["world trade organization"]},
    "opec": {"weight": 5, "aliases": []},

    # Financial/Economic terms
    "interest rate": {"weight": 9, "aliases": ["rates", "federal funds rate", "policy rate"]},
    "rate cut": {"weight": 8, "aliases": ["rate cuts", "easing", "monetary easing"]},
    "rate hike": {"weight": 8, "aliases": ["rate hikes", "tightening", "monetary tightening"]},
    "white house": {"weight": 6, "aliases": ["administration", "biden administration", "trump administration"]},
    "congress": {"weight": 6, "aliases": ["legislature", "legislative branch", "capitol hill"]},
    "senate": {"weight": 6, "aliases": ["senators", "upper chamber"]},
    "house": {"weight": 6, "aliases": ["house of representatives", "lower chamber", "congressional"]},
    "supreme court": {"weight": 6, "aliases": ["scotus", "high court"]},
    "prime minister": {"weight": 6, "aliases": ["pm", "premier", "chancellor"]},
    "parliament": {"weight": 5, "aliases": []},
    "ipo": {"weight": 6, "aliases": ["initial public offering", "going public"]},
    "merger": {"weight": 6, "aliases": ["mergers", "acquisition", "acquisitions", "m&a"]},
    "earnings": {"weight": 6, "aliases": ["profit", "revenue", "quarterly results", "financial results"]},
    "lawsuit": {"weight": 6, "aliases": ["litigation", "legal action", "court case", "sued"]},
    "bankruptcy": {"weight": 6, "aliases": ["chapter 11", "insolvency", "restructuring"]},

    # Tech/AI
    "ai": {"weight": 6, "aliases": ["artificial intelligence", "machine learning", "ml", "large language model", "llm"]},
    "gpt": {"weight": 6, "aliases": ["chatgpt", "generative ai"]},
    "chatgpt": {"weight": 6, "aliases": ["chat gpt"]},
    "deepseek": {"weight": 6, "aliases": []},

    # Sports
    "world cup": {"weight": 5, "aliases": ["fifa world cup", "worldcup"]},
    "olympics": {"weight": 5, "aliases": ["olympic games", "olympic"]},
    "championship": {"weight": 4, "aliases": ["championships", "finals"]},
    "nba": {"weight": 4, "aliases": ["national basketball association"]},
    "nfl": {"weight": 4, "aliases": ["national football league", "super bowl", "superbowl"]},
    "mlb": {"weight": 4, "aliases": ["major league baseball", "world series"]},
    "nhl": {"weight": 4, "aliases": ["national hockey league", "stanley cup"]},
    "fifa": {"weight": 4, "aliases": []},
    "uefa": {"weight": 4, "aliases": ["champions league"]},

    # Other
    "etf": {"weight": 6, "aliases": ["exchange traded fund", "exchange-traded fund"]},
    "covid": {"weight": 5, "aliases": ["coronavirus", "pandemic", "covid-19"]},
    "climate": {"weight": 5, "aliases": ["climate change", "global warming", "emissions"]},
    "weather": {"weight": 5, "aliases": ["hurricane", "storm", "temperature", "forecast"]},
}

# Category mappings for cross-market matching
CATEGORY_WEIGHTS = {
    "politics": 8,
    "elections": 8,
    "finance": 7,
    "economy": 7,
    "crypto": 6,
    "technology": 6,
    "sports": 4,
    "entertainment": 3,
    "weather": 5,
    "science": 5,
}

# Event type keywords for temporal matching
EVENT_TYPES = {
    "election": ["election", "vote", "ballot", "poll", "electoral"],
    "earnings": ["earnings", "revenue", "profit", "quarterly", "fiscal", "financial results"],
    "ipo": ["ipo", "initial public offering", "going public"],
    "rate_decision": ["rate decision", "fomc", "fed meeting", "interest rate", "rate cut", "rate hike"],
    "legal": ["lawsuit", "court", "ruling", "decision", "verdict", "settlement", "trial"],
    "regulatory": ["approval", "denial", "sec", "regulation", "regulatory"],
    "conflict": ["war", "ceasefire", "peace", "conflict", "invasion", "attack"],
    "weather_event": ["hurricane", "storm", "earthquake", "flood", "disaster"],
    "sports_event": ["championship", "finals", "world cup", "olympics", "super bowl"],
}


def extract_market_tags(market: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract searchable tags from a Polymarket market dictionary.

    Extracts:
    - Named entities (people, orgs, countries, tickers)
    - Event types (election, earnings, etc.)
    - Keywords from title and description
    - Category information

    Returns dict with:
    - entities: List of found entity keys with weights
    - event_types: List of detected event types
    - keywords: List of significant keywords
    - category: Market category
    - combined_text: Normalized text for searching
    """
    title = market.get("title", "")
    description = market.get("description", "")
    category = market.get("category", "other")

    # Combine and normalize text
    combined_text = f"{title} {description}".lower()

    # Clean up text for matching
    combined_text = re.sub(r'[^\w\s]', ' ', combined_text)
    combined_text = re.sub(r'\s+', ' ', combined_text).strip()

    found_entities = []
    entity_weights = {}
    found_aliases = {}  # Maps alias -> entity key for reverse lookup

    # Find entities and their aliases
    for entity_key, entity_data in NAMED_ENTITIES.items():
        weight = entity_data["weight"]
        aliases = entity_data["aliases"]

        # Check if entity key is in text
        if re.search(r'\b' + re.escape(entity_key) + r'\b', combined_text):
            found_entities.append(entity_key)
            entity_weights[entity_key] = weight
            # Store all aliases for this entity
            for alias in aliases:
                found_aliases[alias] = entity_key
            continue

        # Check aliases
        for alias in aliases:
            if re.search(r'\b' + re.escape(alias) + r'\b', combined_text):
                found_entities.append(entity_key)
                entity_weights[entity_key] = weight
                found_aliases[alias] = entity_key
                break

    # Detect event types
    detected_events = []
    for event_type, keywords in EVENT_TYPES.items():
        for keyword in keywords:
            if keyword in combined_text:
                detected_events.append(event_type)
                break

    # Extract additional keywords (significant words not already captured)
    common_words = {
        "will", "the", "a", "an", "in", "on", "at", "by", "for", "to", "of", "and", "or",
        "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does",
        "did", "can", "could", "would", "should", "may", "might", "must", "shall",
        "before", "after", "during", "between", "among", "within", "until", "till",
        "this", "that", "these", "those", "with", "without", "from", "into", "through",
        "over", "under", "above", "below", "up", "down", "out", "off", "about", "against",
        "yes", "no", "true", "false", "happen", "occur", "take", "place", "end", "year",
        "month", "week", "day", "date", "time", "period", "term", "deadline", "2024",
        "2025", "2026", "next", "coming", "current", "now", "today", "tomorrow",
    }

    words = set(combined_text.split())
    keywords = [w for w in words if len(w) > 2 and w not in common_words and w not in NAMED_ENTITIES]
    # Limit to most significant keywords
    keywords = sorted(keywords, key=lambda x: len(x), reverse=True)[:15]

    # Get category weight
    category_lower = category.lower()
    category_weight = CATEGORY_WEIGHTS.get(category_lower, 3)

    result = {
        "entities": found_entities,
        "entity_weights": entity_weights,
        "entity_aliases": found_aliases,
        "event_types": detected_events,
        "keywords": keywords,
        "category": category,
        "category_weight": category_weight,
        "combined_text": combined_text,
        "title_lower": title.lower(),
        "description_lower": description.lower(),
    }

    # DEBUG: Log entity extraction for troubleshooting
    if found_entities:
        print(f"    [KALSHI EXTRACT] '{title[:40]}...' -> entities: {found_entities}")

    return result


def calculate_match_score(poly_tags: Dict[str, Any], kalshi_market: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """
    Calculate a match score between Polymarket tags and a Kalshi market.

    Returns:
        Tuple of (score, match_details)
    """
    kalshi_title = kalshi_market.get("title", "").lower()
    kalshi_category = kalshi_market.get("category", "").lower()

    score = 0
    match_details = {
        "entity_matches": [],
        "event_matches": [],
        "keyword_matches": [],
        "category_bonus": 0,
    }

    # Entity matching - highest weight
    for entity_key in poly_tags["entities"]:
        weight = poly_tags["entity_weights"].get(entity_key, 5)
        entity_data = NAMED_ENTITIES.get(entity_key, {})

        # Check if entity or any alias appears in Kalshi title
        match_found = False

        # Direct match (full word)
        if re.search(r'\b' + re.escape(entity_key) + r'\b', kalshi_title):
            score += weight
            match_found = True
            match_details["entity_matches"].append(f"{entity_key} (direct)")
        else:
            # Check aliases
            for alias in entity_data.get("aliases", []):
                if re.search(r'\b' + re.escape(alias) + r'\b', kalshi_title):
                    score += weight
                    match_found = True
                    match_details["entity_matches"].append(f"{entity_key} (via '{alias}')")
                    break

        # Partial match (entity in text but not word-boundary) - half weight
        if not match_found and entity_key in kalshi_title:
            score += max(1, weight // 2)  # At least 1 point
            match_details["entity_matches"].append(f"{entity_key} (partial)")

    # Event type matching (increased weight)
    for event_type in poly_tags["event_types"]:
        event_keywords = EVENT_TYPES.get(event_type, [])
        for keyword in event_keywords:
            if keyword in kalshi_title:
                score += 5  # Increased from 4
                match_details["event_matches"].append(event_type)
                break

    # Category matching (bonus) - only if Kalshi category matches our allowed categories
    allowed_kalshi_categories = {'politics', 'economics', 'finance', 'crypto', 'weather', 'events'}
    if poly_tags["category"] and poly_tags["category"] in allowed_kalshi_categories:
        if poly_tags["category"] in kalshi_category:
            score += poly_tags["category_weight"]
            match_details["category_bonus"] = poly_tags["category_weight"]

    # Keyword matching (lower weight but can add up)
    for keyword in poly_tags["keywords"]:
        if len(keyword) > 4 and keyword in kalshi_title:
            score += 2  # Increased from 1 for important keywords
            match_details["keyword_matches"].append(keyword)

    return score, match_details


def fetch_kalshi_markets():
    """
    Fetch active Kalshi markets — no auth required.
    Returns list of market dicts or empty list on failure.
    """
    try:
        url = "https://api.elections.kalshi.com/trade-api/v2/markets"
        params = {
            "limit": MAX_MARKETS_PER_FETCH,
            "status": "open",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"  Kalshi returned {r.status_code} — skipping")
            return []

        data = r.json()
        markets = data.get("markets", [])

        parsed = []
        for m in markets:
            try:
                # Kalshi yes price is mid of bid/ask (in dollars, not cents)
                yes_bid = float(m.get("yes_bid_dollars", 0) or 0)  # already in dollars
                yes_ask = float(m.get("yes_ask_dollars", 0) or 0)

                # Calculate price: use mid if both available, otherwise use whichever is available
                if yes_bid > 0 and yes_ask > 0:
                    yes_price = (yes_bid + yes_ask) / 2
                elif yes_bid > 0:
                    yes_price = yes_bid
                elif yes_ask > 0:
                    yes_price = yes_ask
                else:
                    yes_price = None

                volume = float(m.get("volume_fp", 0) or 0)  # use volume_fp field

                # Skip markets with no price (volume not required for signal)
                if yes_price is None:
                    continue

                parsed.append({
                    "ticker": m.get("ticker", ""),
                    "title": m.get("title", ""),
                    "yes_price": yes_price,
                    "volume": volume,
                    "close_time": m.get("close_time", ""),
                    "category": m.get("category", ""),
                })
            except:
                continue

        print(f"OK Kalshi - {len(parsed)} markets loaded")
        return parsed

    except Exception as e:
        print(f"ERROR Kalshi fetch failed: {e} - continuing without")
        return []


def match_kalshi(polymarket_market: Dict[str, Any], kalshi_markets: List[Dict]) -> Dict[str, Any]:
    """
    Find matching Kalshi market using enhanced entity extraction and weighted scoring.

    Args:
        polymarket_market: Full Polymarket market dict with title, description, category, etc.
        kalshi_markets: List of Kalshi market dicts to match against

    Returns:
        Dict with signal info including kalshi_signal, kalshi_yes_price, etc.
    """
    if not kalshi_markets:
        return {
            "kalshi_signal": "UNAVAILABLE",
            "kalshi_yes_price": None,
            "kalshi_gap": None,
            "arb_flag": False,
            "arb_note": None,
        }

    # Extract tags from the Polymarket market
    poly_tags = extract_market_tags(polymarket_market)

    # Get the yes price for gap calculation
    polymarket_yes_price = polymarket_market.get("yes_price", 50) / 100  # Convert from percentage to decimal

    # Score each Kalshi market
    best_match = None
    best_score = 0
    best_match_details = {}

    for km in kalshi_markets:
        score, match_details = calculate_match_score(poly_tags, km)

        if score > best_score:
            best_score = score
            best_match = km
            best_match_details = match_details

    # Need minimum score for a real match
    if best_score < KALSHI_MIN_MATCH_SCORE or best_match is None:
        # DEBUG: Log why no match
        print(f"    [KALSHI DEBUG] No match for '{polymarket_market.get('title', '')[:50]}...'")
        print(f"      Best score: {best_score} (threshold: {KALSHI_MIN_MATCH_SCORE})")
        if best_match_details:
            print(f"      Matched entities: {best_match_details.get('entity_matches', [])}")
            print(f"      Event matches: {best_match_details.get('event_matches', [])}")
            print(f"      Keyword matches: {best_match_details.get('keyword_matches', [])}")
        return {
            "kalshi_signal": "NO MATCH",
            "kalshi_yes_price": None,
            "kalshi_gap": None,
            "arb_flag": False,
            "arb_note": None,
        }

    # DEBUG: Log successful match
    print(f"    [KALSHI MATCH] '{polymarket_market.get('title', '')[:40]}...' -> score {best_score}")
    print(f"      Kalshi: '{best_match['title'][:50]}...'")
    print(f"      Matched: {best_match_details.get('entity_matches', [])}")

    kalshi_price = best_match["yes_price"]
    if kalshi_price is None:
        return {
            "kalshi_signal": "NO PRICE",
            "kalshi_yes_price": None,
            "kalshi_gap": None,
            "arb_flag": False,
            "arb_note": None,
        }

    gap = abs(kalshi_price - polymarket_yes_price)
    gap_pct = round(gap * 100, 1)

    # Determine signal strength
    if gap >= KALSHI_STRONG_GAP / 100:
        signal = f"STRONG — {gap_pct}% gap"
        arb_flag = True
        arb_note = (f"Kalshi {round(kalshi_price*100)}% vs "
                   f"Poly {round(polymarket_yes_price*100)}% "
                   f"on '{best_match['title'][:60]}'")
    elif gap >= KALSHI_MODERATE_GAP / 100:
        signal = f"MODERATE — {gap_pct}% gap"
        arb_flag = False
        arb_note = None
    else:
        signal = f"ALIGNED — {gap_pct}% gap"
        arb_flag = False
        arb_note = None

    return {
        "kalshi_signal": signal,
        "kalshi_yes_price": round(kalshi_price * 100, 1),
        "kalshi_title": best_match["title"],
        "kalshi_gap": gap_pct,
        "arb_flag": arb_flag,
        "arb_note": arb_note,
        "match_score": best_score,
        "matched_entities": best_match_details.get("entity_matches", []),
    }


def test_kalshi_connectivity():
    """Test if Kalshi API is reachable."""
    try:
        url = "https://api.elections.kalshi.com/trade-api/v2/exchange/status"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True, "✓ Kalshi API reachable"
        else:
            return False, f"⚠️ Kalshi returned {r.status_code}"
    except Exception as e:
        return False, f"⚠️ Kalshi unreachable: {e}"


if __name__ == "__main__":
    print("Testing Kalshi Fetcher...")
    markets = fetch_kalshi_markets()
    print(f"Fetched {len(markets)} markets")

    if markets:
        # Test matching with sample markets
        test_markets = [
            {
                "title": "Will Donald Trump win the 2024 US Presidential Election?",
                "description": "Resolves YES if Donald Trump is elected President of the United States in 2024.",
                "category": "politics",
                "yes_price": 52,
            },
            {
                "title": "Will Bitcoin reach $100k by end of 2024?",
                "description": "Resolves YES if BTC/USD trades at or above $100,000 on a major exchange before January 1, 2025.",
                "category": "crypto",
                "yes_price": 35,
            },
            {
                "title": "Will the Fed cut rates in March 2024?",
                "description": "Resolves YES if the Federal Reserve announces a rate cut at their March 2024 FOMC meeting.",
                "category": "finance",
                "yes_price": 45,
            },
            {
                "title": "Will there be a ceasefire in Gaza by June 2024?",
                "description": "Resolves YES if a ceasefire agreement is announced between Israel and Hamas before June 30, 2024.",
                "category": "politics",
                "yes_price": 40,
            },
        ]

        for test_market in test_markets:
            print(f"\n{'='*60}")
            print(f"Testing: {test_market['title'][:60]}...")
            print(f"{'='*60}")

            # Show extracted tags
            tags = extract_market_tags(test_market)
            print(f"  Entities found: {tags['entities']}")
            print(f"  Event types: {tags['event_types']}")
            print(f"  Keywords: {tags['keywords'][:8]}")

            # Run match
            result = match_kalshi(test_market, markets)
            print(f"  Signal: {result['kalshi_signal']}")
            print(f"  Kalshi price: {result['kalshi_yes_price']}")
            print(f"  Gap: {result['kalshi_gap']}%")
            print(f"  Match score: {result.get('match_score', 0)}")
            if result.get('matched_entities'):
                print(f"  Matched entities: {result['matched_entities']}")
            if result.get('kalshi_title'):
                print(f"  Kalshi title: {result['kalshi_title'][:70]}...")
