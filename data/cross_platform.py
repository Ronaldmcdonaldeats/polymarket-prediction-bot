#!/usr/bin/env python3
"""
Cross-Platform Consensus Module
Fetches and compares probabilities from Metaculus, Manifold, and Polymarket
"""

import urllib.parse
import requests
from typing import Dict, List, Any, Optional


def fetch_metaculus_probability(question_id: str) -> Optional[float]:
    """
    Fetch prediction probability from Metaculus API.

    Args:
        question_id: Metaculus question ID

    Returns:
        Probability as percentage (0-100) or None if not found
    """
    url = f"https://www.metaculus.com/api/v2/questions/{question_id}/"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        prediction = data.get("community_prediction", {})

        if prediction and "full" in prediction:
            # q2 is the median prediction
            prob = prediction["full"].get("q2", None)
            if prob is not None:
                return float(prob) * 100  # Convert to percentage

        return None

    except Exception:
        return None


def fetch_manifold_probability(question_id: str) -> Optional[float]:
    """
    Fetch prediction probability from Manifold Markets API.

    Args:
        question_id: Manifold market slug or ID

    Returns:
        Probability as percentage (0-100) or None if not found
    """
    url = f"https://api.manifold.markets/v0/slug/{question_id}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        prob = data.get("probability", None)

        if prob is not None:
            return float(prob) * 100  # Convert to percentage

        return None

    except Exception:
        return None


def search_related_platforms(market_title: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search for related questions on Metaculus and Manifold.

    Args:
        market_title: The title of the Polymarket market to search for

    Returns:
        Dict with search results from each platform
    """
    encoded_title = urllib.parse.quote(market_title)
    results = {"metaculus": [], "manifold": []}

    # Search Metaculus
    try:
        meta_url = f"https://www.metaculus.com/api/v2/questions/?search={encoded_title}&status=open&limit=3"
        meta_resp = requests.get(meta_url, timeout=10)
        if meta_resp.status_code == 200:
            meta_data = meta_resp.json()
            for q in meta_data.get("results", []):
                prediction = q.get("community_prediction", {})
                prob = None
                if prediction and "full" in prediction:
                    prob = prediction["full"].get("q2", None)

                results["metaculus"].append({
                    "id": q.get("id"),
                    "title": q.get("title", ""),
                    "url": f"https://www.metaculus.com/questions/{q.get('id', '')}",
                    "probability": prob * 100 if prob is not None else None
                })
    except Exception:
        pass

    # Search Manifold
    try:
        man_url = f"https://api.manifold.markets/v0/search-markets?term={encoded_title}&limit=3"
        man_resp = requests.get(man_url, timeout=10)
        if man_resp.status_code == 200:
            man_data = man_resp.json()
            for m in man_data:
                prob = m.get("probability")
                results["manifold"].append({
                    "id": m.get("id"),
                    "slug": m.get("slug", ""),
                    "title": m.get("question", ""),
                    "url": f"https://manifold.markets/{m.get('creatorUsername', '')}/{m.get('slug', '')}",
                    "probability": prob * 100 if prob is not None else None
                })
    except Exception:
        pass

    return results


def calculate_consensus(polymarket_prob: float, external_probs: List[float]) -> Dict[str, Any]:
    """
    Calculate consensus signal from multiple platform probabilities.

    Args:
        polymarket_prob: Polymarket probability (0-100)
        external_probs: List of probabilities from other platforms

    Returns:
        Dict with consensus signal, gap, and analysis
    """
    if not external_probs:
        return {
            "signal": "WEAK",
            "max_gap": 0,
            "avg_external": None,
            "platforms_used": 0,
            "suggestion": "No external data available"
        }

    # Calculate statistics
    avg_external = sum(external_probs) / len(external_probs)
    max_prob = max([polymarket_prob] + external_probs)
    min_prob = min([polymarket_prob] + external_probs)
    max_gap = max_prob - min_prob

    # Determine signal strength
    if max_gap > 15:
        signal = "STRONG"
        suggestion = "Significant discrepancy - potential edge"
    elif max_gap > 8:
        signal = "MODERATE"
        suggestion = "Moderate discrepancy - possible edge"
    else:
        signal = "WEAK"
        suggestion = "Platforms largely agree - no clear edge"

    # Calculate confidence in the direction
    polymarket_higher = polymarket_prob > avg_external

    return {
        "signal": signal,
        "max_gap": round(max_gap, 2),
        "polymarket_prob": round(polymarket_prob, 2),
        "avg_external": round(avg_external, 2),
        "platforms_used": len(external_probs) + 1,
        "polymarket_higher": polymarket_higher,
        "suggestion": suggestion
    }


def get_cross_platform_signal(market_title: str, polymarket_prob: float) -> Dict[str, Any]:
    """
    Main function to get cross-platform consensus signal.

    Args:
        market_title: Title of the Polymarket market
        polymarket_prob: Current Polymarket probability (0-100)

    Returns:
        Dict with full cross-platform analysis
    """
    # Search for related questions
    search_results = search_related_platforms(market_title)

    # Collect external probabilities
    external_probs = []
    platform_details = []

    # Add Metaculus probabilities
    for result in search_results["metaculus"]:
        if result["probability"] is not None:
            external_probs.append(result["probability"])
            platform_details.append({
                "platform": "metaculus",
                "title": result["title"],
                "probability": result["probability"],
                "url": result["url"]
            })

    # Add Manifold probabilities
    for result in search_results["manifold"]:
        if result["probability"] is not None:
            external_probs.append(result["probability"])
            platform_details.append({
                "platform": "manifold",
                "title": result["title"],
                "probability": result["probability"],
                "url": result["url"]
            })

    # Calculate consensus
    consensus = calculate_consensus(polymarket_prob, external_probs)

    return {
        "signal": consensus.get("signal", "WEAK"),
        "max_gap": consensus.get("max_gap", 0),
        "polymarket_prob": consensus.get("polymarket_prob", round(polymarket_prob, 2)),
        "avg_external": consensus.get("avg_external"),
        "platforms_used": consensus.get("platforms_used", 1),
        "polymarket_higher": consensus.get("polymarket_higher", False),
        "suggestion": consensus.get("suggestion", "No external data available"),
        "external_markets": platform_details,
        "raw_search_results": search_results
    }


def enrich_markets_with_consensus(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich a list of markets with cross-platform consensus data.

    Args:
        markets: List of market dictionaries with 'title' and 'yes_price' keys

    Returns:
        List of markets enriched with cross_platform_signal
    """
    enriched = []

    for market in markets:
        title = market.get("title", "")
        yes_price = market.get("yes_price", 50)

        consensus_data = get_cross_platform_signal(title, yes_price)

        market["cross_platform_signal"] = consensus_data["signal"]
        market["cross_platform_gap"] = consensus_data["max_gap"]
        market["cross_platform_analysis"] = consensus_data

        enriched.append(market)

    return enriched


def fetch_consensus_for_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fetch cross-platform consensus for markets.
    Alias for enrich_markets_with_consensus.
    """
    return enrich_markets_with_consensus(markets)


if __name__ == "__main__":
    # Test the module
    print("Testing Cross-Platform Consensus...")

    test_title = "Will Donald Trump win the 2024 US Presidential Election?"
    test_prob = 55.0

    result = get_cross_platform_signal(test_title, test_prob)

    print(f"Signal: {result['signal']}")
    print(f"Max gap: {result['max_gap']:.1f}%")
    print(f"Polymarket: {result['polymarket_prob']}%")
    print(f"Avg External: {result['avg_external']}%")
    print(f"Suggestion: {result['suggestion']}")
    print(f"\nExternal markets found: {len(result['external_markets'])}")

    for m in result["external_markets"]:
        print(f"  - {m['platform']}: {m['title'][:50]}... @ {m['probability']:.1f}%")
