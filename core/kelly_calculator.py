#!/usr/bin/env python3
"""
Kelly Criterion Stake Calculator
Calculates optimal bet size using Kelly Criterion.
"""

from typing import Dict, Any

from utils.memory_system import load_multipliers
from utils.config import MIN_STAKE_USD, MAX_STAKE_USD, DEFAULT_KELLY_BASE_FRACTION, DEFAULT_BANKROLL, MIN_EDGE_THRESHOLD


def calculate_stake(market_id: str, direction: str, our_probability: float,
                   market_probability: float, confidence: str,
                   panel_agreement: str = "weak",
                   whale_signal: str = "UNKNOWN",
                   cross_platform: str = "WEAK",
                   category: str = "other") -> Dict[str, Any]:
    """
    Calculate stake for a bet (wrapper for main.py compatibility).

    Args:
        market_id: Market identifier
        direction: "YES" or "NO"
        our_probability: Our estimated probability (0-1)
        market_probability: Market probability (0-1)
        confidence: "high", "medium", or "low"

    Returns:
        Dict with stake calculation
    """
    multipliers = load_multipliers()

    # Calculate Kelly fraction
    if direction == "YES":
        p = our_probability
        market_price = market_probability
    else:
        p = 1 - our_probability
        market_price = 1 - market_probability

    # Calculate odds
    if market_price <= 0:
        b = 1.0
    else:
        b = (1 - market_price) / market_price

    # Kelly formula
    if b <= 0:
        kelly_fraction = 0
    else:
        kelly_fraction = (p * (b + 1) - 1) / b

    kelly_fraction = max(0, min(1, kelly_fraction))

    # Get base parameters
    kelly_config = multipliers.get("kelly", {"base_fraction": DEFAULT_KELLY_BASE_FRACTION, "bankroll": DEFAULT_BANKROLL})
    base_fraction = kelly_config.get("base_fraction", DEFAULT_KELLY_BASE_FRACTION)
    bankroll = kelly_config.get("bankroll", DEFAULT_BANKROLL)

    # Apply multipliers
    conf_mult = multipliers.get("confidence_mult", {}).get(confidence, 0.3)
    panel_mult = multipliers.get("panel_mult", {}).get(panel_agreement, 0.4)

    # Whale multiplier - only if whale agrees with our bet
    if whale_signal == direction:
        whale_mult = multipliers.get("whale_mult", {}).get("agrees", 1.0)
    else:
        whale_mult = multipliers.get("whale_mult", {}).get("disagrees_or_unknown", 0.85)

    cross_mult = multipliers.get("cross_platform_mult", {}).get(cross_platform, 0.90)
    category_bonus = multipliers.get("category_bonus", {}).get(category, 0)

    # Calculate final multiplier
    total_mult = conf_mult * panel_mult * whale_mult * cross_mult
    total_mult *= (1 + category_bonus / 100) if category_bonus != 0 else 1

    # Calculate stake
    adjusted_kelly = kelly_fraction * base_fraction
    stake = adjusted_kelly * bankroll * total_mult

    # Clamp to min/max
    final_stake = max(MIN_STAKE_USD, min(MAX_STAKE_USD, stake))

    # Calculate edge (as percentage for consistency with judge output)
    if direction == "YES":
        edge = (our_probability - market_probability) * 100
    else:
        edge = ((1 - our_probability) - (1 - market_probability)) * 100

    return {
        "stake_usd": round(final_stake, 2),
        "kelly_fraction": adjusted_kelly,
        "edge": round(edge, 2),
        "total_multiplier": round(total_mult, 4)
    }


def calculate_kelly_stake(market: Dict[str, Any], judge_decision: Dict[str, Any],
                          multipliers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate Kelly stake for a bet.

    Formula: f* = (p(b+1) - 1) / b
    Where:
    - p = estimated probability of winning (as decimal)
    - b = odds received (as decimal) = (1 - market_price) / market_price

    Args:
        market: Market data dict
        judge_decision: Judge decision dict
        multipliers: Current multipliers

    Returns:
        Dict with stake calculation
    """
    # Get base parameters
    estimated_prob = judge_decision.get("estimated_probability", 0.5)
    market_price = market.get("yes_price", 50) / 100

    # Calculate implied probability from market price
    # If betting YES: we win (1 - price) / price if correct
    # If betting NO: we win price / (1 - price) if correct

    decision = judge_decision.get("decision", "SKIP")
    if decision == "SKIP":
        return {
            "stake": 0,
            "kelly_fraction": 0,
            "edge_percent": 0,
            "reason": "Judge skipped"
        }

    # Calculate odds
    if decision == "YES":
        # Betting on YES at market_price
        # If correct, we win (1 - market_price) per $1 bet
        b = (1 - market_price) / market_price if market_price > 0 else 1
        p = estimated_prob
    else:  # NO
        # Betting on NO at (1 - market_price)
        b = market_price / (1 - market_price) if market_price < 1 else 1
        p = 1 - estimated_prob

    # Kelly fraction: f* = (p(b+1) - 1) / b
    if b <= 0:
        kelly_fraction = 0
    else:
        kelly_fraction = (p * (b + 1) - 1) / b

    # Kelly should be between 0 and 1
    kelly_fraction = max(0, min(1, kelly_fraction))

    # Get base fraction and bankroll from multipliers
    kelly_config = multipliers.get("kelly", {"base_fraction": DEFAULT_KELLY_BASE_FRACTION, "bankroll": DEFAULT_BANKROLL})
    base_fraction = kelly_config.get("base_fraction", DEFAULT_KELLY_BASE_FRACTION)
    bankroll = kelly_config.get("bankroll", DEFAULT_BANKROLL)

    # Apply base fraction (half-Kelly, quarter-Kelly, etc.)
    adjusted_kelly = kelly_fraction * base_fraction

    # Apply multipliers
    confidence = judge_decision.get("final_confidence", "low")
    panel_agreement = market.get("panel_agreement", "weak")
    whale_signal = market.get("whale_signal", "UNKNOWN")
    cross_platform = market.get("cross_platform_signal", "WEAK")

    # Get multiplier values
    conf_mult = multipliers.get("confidence_mult", {}).get(confidence, 0.3)
    panel_mult = multipliers.get("panel_mult", {}).get(panel_agreement, 0.4)

    # Whale multiplier - only if whale agrees with our bet
    if whale_signal == decision:
        whale_mult = multipliers.get("whale_mult", {}).get("agrees", 1.0)
    else:
        whale_mult = multipliers.get("whale_mult", {}).get("disagrees_or_unknown", 0.85)

    cross_mult = multipliers.get("cross_platform_mult", {}).get(cross_platform, 0.90)

    # Category bonus (can be negative)
    category = market.get("category", "other")
    category_bonus = multipliers.get("category_bonus", {}).get(category, 0)

    # Calculate final multiplier
    total_mult = conf_mult * panel_mult * whale_mult * cross_mult
    total_mult *= (1 + category_bonus / 100) if category_bonus != 0 else 1

    # Calculate final stake
    raw_stake = adjusted_kelly * bankroll * total_mult

    # Clamp to min/max
    final_stake = max(MIN_STAKE_USD, min(MAX_STAKE_USD, raw_stake))

    # Edge calculation
    if decision == "YES":
        edge = (estimated_prob - market_price) * 100
    else:
        edge = ((1 - estimated_prob) - (1 - market_price)) * 100

    return {
        "stake": round(final_stake, 2),
        "raw_kelly": round(kelly_fraction, 4),
        "adjusted_kelly": round(adjusted_kelly, 4),
        "kelly_fraction": base_fraction,
        "bankroll": bankroll,
        "edge_percent": round(edge, 2),
        "multipliers": {
            "confidence": conf_mult,
            "panel": panel_mult,
            "whale": whale_mult,
            "cross_platform": cross_mult,
            "category_bonus": category_bonus,
            "total": round(total_mult, 4)
        },
        "reason": f"Kelly {base_fraction:.0%} with edge {edge:.1f}%"
    }


def should_place_bet(stake_calc: Dict[str, Any], min_edge: float = MIN_EDGE_THRESHOLD) -> bool:
    """
    Determine if bet should be placed.

    Args:
        stake_calc: Stake calculation result
        min_edge: Minimum edge threshold (default 10%)

    Returns:
        True if bet should be placed
    """
    edge = stake_calc.get("edge_percent", 0)
    stake = stake_calc.get("stake", 0)

    return edge >= min_edge and stake >= MIN_STAKE_USD


if __name__ == "__main__":
    # Test the module
    print("Testing Kelly Calculator...")

    test_market = {
        "title": "Test Market",
        "yes_price": 45.0,
        "category": "politics",
        "panel_agreement": "moderate",
        "whale_signal": "YES",
        "cross_platform_signal": "MODERATE"
    }

    test_decision = {
        "decision": "YES",
        "final_confidence": "high",
        "estimated_probability": 65.0
    }

    test_multipliers = load_multipliers()

    result = calculate_kelly_stake(test_market, test_decision, test_multipliers)

    print(f"Stake: ${result['stake']:.2f}")
    print(f"Raw Kelly: {result['raw_kelly']:.4f}")
    print(f"Edge: {result['edge_percent']:.2f}%")
    print(f"Total multiplier: {result['multipliers']['total']:.4f}")
    print(f"Should bet: {should_place_bet(result)}")
