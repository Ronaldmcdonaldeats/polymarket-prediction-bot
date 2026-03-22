#!/usr/bin/env python3
"""
Judge Module
Makes final decision based on panel votes and all signals.
Uses Cerebras (llama-3.3-70b).
"""

from typing import Dict, List, Any

from utils.model_helpers import call_cerebras
from utils.config import KALSHI_STRONG_GAP


def build_judge_prompt(market: Dict[str, Any], panel_votes: Dict[str, Any],
                       multipliers: Dict[str, Any]) -> tuple:
    """
    Build prompt for Judge agent.

    Args:
        market: Market data dict
        panel_votes: Panel voting results
        multipliers: Current multipliers

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    system = f"""You are THE JUDGE - Final Decision Maker for the Polymarket Prediction Bot.

Your job: Review all evidence and panel votes, then make a final decision.
You have access to all research, signals, and agent votes.

Be decisive but cautious. Only bet when there's clear edge.

IMPORTANT: If arbitrage_flag is True (Kalshi gap {KALSHI_STRONG_GAP}%+), weight that market more heavily in your decision. A large gap between Polymarket and Kalshi prices indicates potential mispricing.

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "YES|NO|SKIP",
  "final_confidence": "high|medium|low",
  "estimated_probability": float (0-100),
  "edge_percent": float (absolute difference from market price),
  "reasoning": "string - your detailed reasoning",
  "one_sentence_summary": "string - punchy summary for Discord",
  "risk_level": "LOW|MEDIUM|HIGH"
}}"""  # noqa: E501

    # Build vote summary
    votes = panel_votes.get("votes", {})
    vote_summary = []
    for agent_name, vote in votes.items():
        vote_summary.append(
            f"  {agent_name}: {vote.get('direction', 'SKIP')} "
            f"(conf: {vote.get('confidence', 'low')}, "
            f"prob: {vote.get('estimated_probability', 50):.1f}%)"
        )

    user = f"""=== MARKET ===
Title: {market.get('title', '')}
Category: {market.get('category', 'unknown')}
Current YES Price: {market.get('yes_price', 50):.1f}%
Volume: ${market.get('volume', 0):,.0f}

=== PANEL VOTES ===
{chr(10).join(vote_summary)}

Panel Consensus: {panel_votes.get('consensus_direction', 'TIED')}
Agreement Level: {panel_votes.get('agreement', 'weak')}
Average Estimated Probability: {panel_votes.get('avg_estimated_probability', 50):.1f}%

=== SIGNALS ===
Research Confidence: {market.get('research', {}).get('confidence', 'low')}
Whale Signal: {market.get('whale_signal', 'UNKNOWN')}
Cross-Platform Signal: {market.get('cross_platform_signal', 'WEAK')}
Kalshi Signal: {market.get('kalshi_signal', 'UNAVAILABLE')}
Kalshi Gap: {market.get('kalshi_gap', 'N/A')}%
Arbitrage Flag: {market.get('arb_flag', False)}

=== SYNTHESIS ===
{market.get('gemini_synthesis', {}).get('sentiment_summary', 'No synthesis available')[:200]}

=== CURRENT MULTIPLIERS ===
Confidence: {multipliers.get('confidence_mult', {})}
Panel: {multipliers.get('panel_mult', {})}
Category Bonus: {multipliers.get('category_bonus', {}).get(market.get('category', 'other'), 0)}

Make your final decision."""

    return system, user


def judge_decision(market: Dict[str, Any], panel_votes: Dict[str, Any],
                   multipliers: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Judge makes final decision.

    Args:
        market: Market data dict
        panel_votes: Panel voting results
        multipliers: Current multipliers

    Returns:
        Decision dict
    """
    if multipliers is None:
        multipliers = {}
    system, user = build_judge_prompt(market, panel_votes, multipliers)

    try:
        result = call_cerebras(system, user, json_mode=True)

        # Calculate edge in code - don't rely on LLM
        estimated_prob = result.get("estimated_probability", 50)
        market_price = market.get("market_probability", 0.5) * 100
        edge_percent = abs(estimated_prob - market_price)

        return {
            "decision": result.get("decision", "SKIP"),
            "final_confidence": result.get("final_confidence", "low"),
            "estimated_probability": estimated_prob,
            "edge_percent": edge_percent,
            "reasoning": result.get("reasoning", ""),
            "one_sentence_summary": result.get("one_sentence_summary", ""),
            "risk_level": result.get("risk_level", "HIGH")
        }
    except Exception as e:
        return {
            "decision": "SKIP",
            "final_confidence": "low",
            "estimated_probability": 50,
            "edge_percent": 0,
            "reasoning": f"Error in judgment: {str(e)[:100]}",
            "one_sentence_summary": "Error - skipping bet",
            "risk_level": "HIGH"
        }


def compare_judge_to_panel(decision: Dict[str, Any], panel_votes: Dict[str, Any]) -> bool:
    """
    Check if Judge disagrees with panel majority.

    Args:
        decision: Judge decision
        panel_votes: Panel votes

    Returns:
        True if Judge disagrees
    """
    judge_dir = decision.get("decision", "SKIP")
    panel_consensus = panel_votes.get("consensus_direction", "TIED")

    if judge_dir == "SKIP" or panel_consensus == "TIED":
        return False

    return judge_dir != panel_consensus


if __name__ == "__main__":
    # Test the module
    print("Testing Judge...")

    test_market = {
        "title": "Will Ethereum hit $5000 in 2024?",
        "category": "crypto",
        "yes_price": 35.0,
        "volume": 75000,
        "research": {"confidence": "medium"},
        "whale_signal": "YES",
        "cross_platform_signal": "MODERATE"
    }

    test_votes = {
        "votes": {
            "quant": {"direction": "YES", "confidence": "medium"},
            "contrarian": {"direction": "NO", "confidence": "low"},
            "journalist": {"direction": "YES", "confidence": "medium"},
            "risk_manager": {"direction": "YES", "confidence": "high"}
        },
        "consensus_direction": "YES",
        "agreement": "moderate",
        "avg_estimated_probability": 55.0
    }

    test_multipliers = {
        "confidence_mult": {"high": 1.0, "medium": 0.6, "low": 0.3},
        "panel_mult": {"strong": 1.0, "moderate": 0.7, "weak": 0.4},
        "category_bonus": {"crypto": -100}
    }

    result = judge_decision(test_market, test_votes, test_multipliers)
    print(f"Decision: {result['decision']}")
    print(f"Confidence: {result['final_confidence']}")
    print(f"Edge: {result['edge_percent']:.1f}%")
    print(f"Summary: {result['one_sentence_summary']}")
