#!/usr/bin/env python3
"""
Gemini Cross-Market Synthesis Module
Uses Gemini to analyze related markets and synthesize insights.
"""

from typing import Dict, List, Any

from utils.model_helpers import call_gemini


def build_synthesis_prompt(market: Dict[str, Any], related_markets: List[Dict[str, Any]]) -> tuple:
    """
    Build prompt for Gemini synthesis.

    Args:
        market: The target market
        related_markets: List of related markets with probabilities

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    system = """You are a cross-market analyst. Given a target prediction market and a list of
related/competing markets with their current probabilities, analyze how they relate
to the target market. Synthesize key insights about market sentiment and pricing patterns.

Respond ONLY with valid JSON in this exact format:
{
  "related_count": integer,
  "avg_correlation": float (0-1),
  "price_discrepancy": "HIGHER|LOWER|SIMILAR",
  "sentiment_summary": "string",
  "key_factors": ["string", "string", ...],
  "confidence_adjustment": integer (-20 to +20)
}"""

    related_text = []
    for rm in related_markets:
        related_text.append(f"- {rm.get('title', '')}: {rm.get('probability', 50):.1f}%")

    user = f"""Target Market: {market.get('title', '')}
Current Polymarket Price: {market.get('yes_price', 50):.1f}%

Related Markets ({len(related_markets)} found):
{chr(10).join(related_text[:10])}

Analyze the relationship between the target market and these related markets.
Provide your JSON response with synthesis analysis."""

    return system, user


def synthesize_related_markets(market: Dict[str, Any], related_markets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use Gemini to synthesize insights from related markets.

    Args:
        market: The target market
        related_markets: List of related markets

    Returns:
        Synthesis result dict
    """
    if not related_markets:
        return {
            "related_count": 0,
            "avg_correlation": 0.5,
            "price_discrepancy": "UNKNOWN",
            "sentiment_summary": "No related markets found",
            "key_factors": [],
            "confidence_adjustment": 0
        }

    system, user = build_synthesis_prompt(market, related_markets)

    try:
        result = call_gemini(system, user, json_mode=True)

        # Validate and clean result
        return {
            "related_count": result.get("related_count", len(related_markets)),
            "avg_correlation": max(0, min(1, result.get("avg_correlation", 0.5))),
            "price_discrepancy": result.get("price_discrepancy", "SIMILAR"),
            "sentiment_summary": result.get("sentiment_summary", ""),
            "key_factors": result.get("key_factors", []),
            "confidence_adjustment": max(-20, min(20, result.get("confidence_adjustment", 0)))
        }
    except Exception as e:
        return {
            "related_count": len(related_markets),
            "avg_correlation": 0.5,
            "price_discrepancy": "UNKNOWN",
            "sentiment_summary": f"Synthesis error: {str(e)[:50]}",
            "key_factors": [],
            "confidence_adjustment": 0
        }


def batch_synthesize(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Synthesize insights for multiple markets.

    Args:
        markets: List of markets with related_markets field

    Returns:
        Markets with synthesis field added
    """
    enriched = []

    for market in markets:
        related = market.get("related_markets", [])
        synthesis = synthesize_related_markets(market, related)
        market["gemini_synthesis"] = synthesis
        enriched.append(market)

    return enriched


# Alias for main.py compatibility
synthesize_cross_market_insights = batch_synthesize


if __name__ == "__main__":
    # Test the module
    print("Testing Gemini Synthesis...")

    test_market = {
        "title": "Will Donald Trump win 2024?",
        "yes_price": 55.0
    }

    test_related = [
        {"title": "Will Trump win PA?", "probability": 52.0},
        {"title": "Will Trump win FL?", "probability": 60.0},
        {"title": "Will Trump win MI?", "probability": 48.0}
    ]

    result = synthesize_related_markets(test_market, test_related)
    print(f"Related count: {result['related_count']}")
    print(f"Avg correlation: {result['avg_correlation']}")
    print(f"Price discrepancy: {result['price_discrepancy']}")
    print(f"Sentiment: {result['sentiment_summary'][:100]}...")
