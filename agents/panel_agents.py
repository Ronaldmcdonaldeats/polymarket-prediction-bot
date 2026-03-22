#!/usr/bin/env python3
"""
Panel Agents Module
4 specialized agents that vote on betting opportunities.
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any

from utils.model_helpers import call_groq, call_cerebras, call_mistral, call_openrouter
from utils.config import (
    INSIDER_STRONG_THRESHOLD,
    INSIDER_BOOST_PROBABILITY,
    INSIDER_REDUCE_PROBABILITY,
    INSIDER_MAX_PROBABILITY,
    INSIDER_MIN_PROBABILITY,
    PANEL_STRONG_MAJORITY,
    PANEL_MODERATE_MAJORITY,
    DEFAULT_AGENT_ACCURACY,
    DEFAULT_BANKROLL
)


def agent_3a_quant(market: Dict[str, Any], memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quant Agent - Analyzes price action, volume, and market microstructure.
    Uses Groq (llama-3.3-70b).

    Args:
        market: Market data dict
        memory_context: Memory context for learning

    Returns:
        Vote dict with direction and confidence
    """
    system = """You are Agent 3A - THE QUANT (Price Action Analyst).

Your job: Analyze market microstructure, price action, and quantitative factors.
Focus on: bid-ask spread, volume patterns, whale activity, price momentum, and Kalshi price signals.

KALSHI SIGNAL WEIGHTING:
- STRONG signal (15%+ gap): Treat as significant whale-level signal. Kalshi is CFTC-regulated with institutional participation.
- MODERATE signal (8-15% gap): Consider as supporting evidence below whale weight.
- ALIGNED/NO GAP (<8% gap): Increases confidence in current price.
- UNAVAILABLE/NO MATCH: Ignore in analysis.

Respond ONLY with valid JSON in this exact format:
{
  "direction": "YES|NO|SKIP",
  "confidence": "high|medium|low",
  "estimated_probability": float (0-100),
  "reasoning": "string",
  "key_factors": ["string", "string", ...],
  "quant_score": integer (0-100)
}"""

    user = f"""Market: {market.get('title', '')}
Category: {market.get('category', 'unknown')}
Current YES Price: {market.get('yes_price', 50):.1f}%
Current NO Price: {market.get('no_price', 50):.1f}%
Volume: ${market.get('volume', 0):,.0f}

Market Data:
- Spread: {market.get('spread_info', {}).get('spread', 'N/A')}
- Whale Signal: {market.get('whale_signal', 'UNKNOWN')} (confidence: {market.get('whale_confidence', 0)})
- Cross-Platform Signal: {market.get('cross_platform_signal', 'WEAK')} (gap: {market.get('cross_platform_gap', 0)}%)
- Kalshi Signal: {market.get('kalshi_signal', 'UNAVAILABLE')}
- Kalshi YES Price: {market.get('kalshi_yes_price', 'N/A')}%
- Kalshi Gap: {market.get('kalshi_gap', 'N/A')}%
- Arbitrage Flag: {market.get('arb_flag', False)}

Research Confidence: {market.get('research', {}).get('confidence', 'low')}
Articles Found: {market.get('research', {}).get('articles_found', 0)}

Memory Context:
- Your past accuracy: {memory_context.get('quant_accuracy', DEFAULT_AGENT_ACCURACY)}%
- Category performance: {memory_context.get('category_stats', {}).get(market.get('category', 'other'), {}).get('win_rate', 'N/A')}

Analyze quantitatively and vote."""

    try:
        result = call_groq(system, user, json_mode=True)
        return {
            "agent": "quant",
            "direction": result.get("direction", "SKIP"),
            "confidence": result.get("confidence", "low"),
            "estimated_probability": result.get("estimated_probability", DEFAULT_AGENT_ACCURACY),
            "reasoning": result.get("reasoning", ""),
            "key_factors": result.get("key_factors", []),
            "quant_score": result.get("quant_score", DEFAULT_AGENT_ACCURACY)
        }
    except Exception as e:
        return {
            "agent": "quant",
            "direction": "SKIP",
            "confidence": "low",
            "estimated_probability": DEFAULT_AGENT_ACCURACY,
            "reasoning": f"Error: {str(e)[:100]}",
            "key_factors": [],
            "quant_score": 0
        }


def agent_3b_contrarian(market: Dict[str, Any], memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Contrarian Agent - Looks for overreaction, herd behavior, and mispricing.
    Uses Cerebras (llama-3.3-70b).

    Args:
        market: Market data dict
        memory_context: Memory context for learning

    Returns:
        Vote dict with direction and confidence
    """
    system = """You are Agent 3B - THE CONTRARIAN (Behavioral Bias Hunter).

Your job: Find overreactions, herd behavior, and market inefficiencies.
Look for: narrative traps, recency bias, crowd positioning, overvalued favorites.

Respond ONLY with valid JSON in this exact format:
{
  "direction": "YES|NO|SKIP",
  "confidence": "high|medium|low",
  "estimated_probability": float (0-100),
  "reasoning": "string",
  "key_factors": ["string", "string", ...],
  "contrarian_score": integer (0-100)
}"""

    user = f"""Market: {market.get('title', '')}
Category: {market.get('category', 'unknown')}
Current YES Price: {market.get('yes_price', 50):.1f}%
Current NO Price: {market.get('no_price', 50):.1f}%

Research Confidence: {market.get('research', {}).get('confidence', 'low')}

Synthesis Summary: {market.get('gemini_synthesis', {}).get('sentiment_summary', 'N/A')}
Price Discrepancy: {market.get('gemini_synthesis', {}).get('price_discrepancy', 'UNKNOWN')}

Memory Context:
- Your past accuracy: {memory_context.get('contrarian_accuracy', DEFAULT_AGENT_ACCURACY)}%
- Lessons learned: {len(memory_context.get('lessons', []))} lessons

Analyze for contrarian opportunities and vote."""

    try:
        result = call_cerebras(system, user, json_mode=True)
        return {
            "agent": "contrarian",
            "direction": result.get("direction", "SKIP"),
            "confidence": result.get("confidence", "low"),
            "estimated_probability": result.get("estimated_probability", DEFAULT_AGENT_ACCURACY),
            "reasoning": result.get("reasoning", ""),
            "key_factors": result.get("key_factors", []),
            "contrarian_score": result.get("contrarian_score", DEFAULT_AGENT_ACCURACY)
        }
    except Exception as e:
        return {
            "agent": "contrarian",
            "direction": "SKIP",
            "confidence": "low",
            "estimated_probability": DEFAULT_AGENT_ACCURACY,
            "reasoning": f"Error: {str(e)[:100]}",
            "key_factors": [],
            "contrarian_score": 0
        }


def agent_3c_journalist(market: Dict[str, Any], memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Journalist Agent - Analyzes news, sentiment, and event timeline.
    Uses Mistral (mistral-large).

    Args:
        market: Market data dict
        memory_context: Memory context for learning

    Returns:
        Vote dict with direction and confidence
    """
    # Get insider data from market
    insider_score = market.get('insider_score', 0)
    insider_direction = market.get('insider_direction', 'UNKNOWN')
    has_strong_insider = insider_score >= INSIDER_STRONG_THRESHOLD and insider_direction != 'UNKNOWN'

    system = """You are Agent 3C - THE JOURNALIST (News & Timeline Analyst).

Your job: Analyze news coverage, sentiment, and event timeline.
Focus on: information gaps, catalyst timing, sentiment vs reality."""

    # Add insider analysis instructions if strong insider signal detected
    if has_strong_insider:
        system += """

INSIDER ACTIVITY ANALYSIS:
- Strong insider activity detected on this market
- Insiders often have non-public information or deep expertise
- Factor insider direction into your probability estimate:
  * If insider is betting YES and score >= 70: INCREASE your probability estimate
  * If insider is betting NO and score >= 70: DECREASE your probability estimate
- Include "FOLLOW_INSIDER" in your key_factors when insider score >= 70
- Consider: Is the insider's bet aligned with or contrary to public news?"""

    system += """

Respond ONLY with valid JSON in this exact format:
{
  "direction": "YES|NO|SKIP",
  "confidence": "high|medium|low",
  "estimated_probability": float (0-100),
  "reasoning": "string",
  "key_factors": ["string", "string", ...],
  "journalist_score": integer (0-100)
}"""

    # Build article summary
    articles = market.get('research', {}).get('articles', [])
    article_summary = "\n".join([
        f"- [{a.get('source', 'unknown')}] {a.get('title', '')[:80]}... (relevance: {a.get('relevance_score', 0)})"
        for a in articles[:5]
    ])

    # Build insider section
    insider_section = ""
    if has_strong_insider:
        insider_section = f"""
INSIDER ACTIVITY (STRONG SIGNAL):
- Insider Direction: {insider_direction}
- Insider Score: {insider_score}/100
- Wallet: {market.get('insider_wallet', 'unknown')[:10]}...
- Pattern: {market.get('insider_pattern', 'unknown')}
"""
    elif insider_score > 0:
        insider_section = f"""
INSIDER ACTIVITY (WEAK SIGNAL):
- Insider Direction: {insider_direction}
- Insider Score: {insider_score}/100 (below 70 threshold)
"""

    user = f"""Market: {market.get('title', '')}
Category: {market.get('category', 'unknown')}
Current YES Price: {market.get('yes_price', 50):.1f}%

Research Articles ({market.get('research', {}).get('articles_found', 0)} found):
{article_summary if article_summary else "No relevant articles found"}

Research Confidence: {market.get('research', {}).get('confidence', 'low')}
{insider_section}
Memory Context:
- Your past accuracy: {memory_context.get('journalist_accuracy', DEFAULT_AGENT_ACCURACY)}%
- Category performance: {memory_context.get('category_stats', {}).get(market.get('category', 'other'), {}).get('win_rate', 'N/A')}

Analyze news, sentiment, and insider activity (if present) and vote."""

    try:
        result = call_mistral(system, user, json_mode=True)

        # Add FOLLOW_INSIDER signal if insider score >= 70
        key_factors = result.get("key_factors", [])
        if has_strong_insider and "FOLLOW_INSIDER" not in key_factors:
            key_factors.append("FOLLOW_INSIDER")

        # Adjust probability based on insider signal if not already done by LLM
        estimated_prob = result.get("estimated_probability", DEFAULT_AGENT_ACCURACY)
        if has_strong_insider:
            # If insider betting YES, ensure probability reflects upward bias
            if insider_direction == "YES" and estimated_prob < (INSIDER_MAX_PROBABILITY - INSIDER_BOOST_PROBABILITY):
                estimated_prob = min(estimated_prob + INSIDER_BOOST_PROBABILITY, INSIDER_MAX_PROBABILITY)
            # If insider betting NO, ensure probability reflects downward bias
            elif insider_direction == "NO" and estimated_prob > (INSIDER_MIN_PROBABILITY + INSIDER_REDUCE_PROBABILITY):
                estimated_prob = max(estimated_prob - INSIDER_REDUCE_PROBABILITY, INSIDER_MIN_PROBABILITY)

        return {
            "agent": "journalist",
            "direction": result.get("direction", "SKIP"),
            "confidence": result.get("confidence", "low"),
            "estimated_probability": estimated_prob,
            "reasoning": result.get("reasoning", ""),
            "key_factors": key_factors,
            "journalist_score": result.get("journalist_score", DEFAULT_AGENT_ACCURACY),
            "insider_signal": "FOLLOW_INSIDER" if has_strong_insider else None
        }
    except Exception as e:
        return {
            "agent": "journalist",
            "direction": "SKIP",
            "confidence": "low",
            "estimated_probability": DEFAULT_AGENT_ACCURACY,
            "reasoning": f"Error: {str(e)[:100]}",
            "key_factors": ["FOLLOW_INSIDER"] if has_strong_insider else [],
            "journalist_score": 0,
            "insider_signal": "FOLLOW_INSIDER" if has_strong_insider else None
        }


def agent_3d_risk_manager(market: Dict[str, Any], memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Risk Manager Agent - Assesses downside, volatility, and position sizing.
    Uses OpenRouter (llama-3.3-70b).

    Args:
        market: Market data dict
        memory_context: Memory context for learning

    Returns:
        Vote dict with direction and confidence
    """
    system = """You are Agent 3D - THE RISK MANAGER (Downside & Volatility Analyst).

Your job: Assess tail risks, volatility, time decay, and position sizing.
Focus on: black swan risks, liquidity issues, downside scenarios.

Respond ONLY with valid JSON in this exact format:
{
  "direction": "YES|NO|SKIP",
  "confidence": "high|medium|low",
  "estimated_probability": float (0-100),
  "reasoning": "string",
  "key_factors": ["string", "string", ...],
  "risk_score": integer (0-100, higher = safer),
  "position_size_recommendation": "SMALL|MEDIUM|LARGE"
}"""

    user = f"""Market: {market.get('title', '')}
Category: {market.get('category', 'unknown')}
Current YES Price: {market.get('yes_price', 50):.1f}%
Current NO Price: {market.get('no_price', 50):.1f}%
Volume: ${market.get('volume', 0):,.0f}
End Date: {market.get('end_date', 'unknown')}

Spread: {market.get('spread_info', {}).get('spread', 'N/A')}
Whale Signal: {market.get('whale_signal', 'UNKNOWN')}

Memory Context:
- Current bankroll: ${memory_context.get('bankroll', DEFAULT_BANKROLL)}
- Your past accuracy: {memory_context.get('risk_accuracy', DEFAULT_AGENT_ACCURACY)}%

Assess risk and vote."""

    try:
        result = call_openrouter(system, user, json_mode=True)
        return {
            "agent": "risk_manager",
            "direction": result.get("direction", "SKIP"),
            "confidence": result.get("confidence", "low"),
            "estimated_probability": result.get("estimated_probability", DEFAULT_AGENT_ACCURACY),
            "reasoning": result.get("reasoning", ""),
            "key_factors": result.get("key_factors", []),
            "risk_score": result.get("risk_score", DEFAULT_AGENT_ACCURACY),
            "position_size_recommendation": result.get("position_size_recommendation", "SMALL")
        }
    except Exception as e:
        return {
            "agent": "risk_manager",
            "direction": "SKIP",
            "confidence": "low",
            "estimated_probability": DEFAULT_AGENT_ACCURACY,
            "reasoning": f"Error: {str(e)[:100]}",
            "key_factors": [],
            "risk_score": 0,
            "position_size_recommendation": "SMALL"
        }


def run_panel_vote(market: Dict[str, Any], memory_context: Dict[str, Any], insider_signals: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run all 4 panel agents in parallel.

    Args:
        market: Market data dict
        memory_context: Memory context for learning
        insider_signals: Optional dict with wallet -> insider_score mapping and direction

    Returns:
        Vote summary dict
    """
    # Attach insider signals to market if present
    if insider_signals:
        market['insider_score'] = insider_signals.get('score', 0)
        market['insider_direction'] = insider_signals.get('direction', 'UNKNOWN')
        market['insider_wallet'] = insider_signals.get('wallet', 'unknown')
        market['insider_pattern'] = insider_signals.get('pattern', 'unknown')

    # Run Quant, Contrarian, and Journalist in parallel to reduce latency
    # Stagger submissions by 1-3 secondsrandom to avoid burst rate limits
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        # Submit Quant agent (Groq)
        time.sleep(random.uniform(1, 3))
        futures['quant'] = executor.submit(agent_3a_quant, market, memory_context)

        # Submit Contrarian agent (Cerebras)
        time.sleep(random.uniform(1, 3))
        futures['contrarian'] = executor.submit(agent_3b_contrarian, market, memory_context)

        # Submit Journalist agent (Mistral)
        time.sleep(random.uniform(1, 3))
        futures['journalist'] = executor.submit(agent_3c_journalist, market, memory_context)

        # Collect results
        quant_vote = futures['quant'].result()
        contrarian_vote = futures['contrarian'].result()
        journalist_vote = futures['journalist'].result()

    # Determine if we need Risk Manager (OpenRouter) - optimize to save API calls
    if quant_vote.get("direction") != "SKIP" or contrarian_vote.get("direction") != "SKIP":
        # Run Risk Manager with staggering to be polite to OpenRouter
        time.sleep(random.uniform(1, 3))
        risk_vote = agent_3d_risk_manager(market, memory_context)
    else:
        # Both say SKIP - Risk Manager vote is None (excluded from consensus)
        risk_vote = None

    # Collect votes (risk_manager may be None)
    votes = {
        "quant": quant_vote,
        "contrarian": contrarian_vote,
        "journalist": journalist_vote,
        "risk_manager": risk_vote
    }

    # Filter out None votes (e.g., when Risk Manager is skipped)
    non_null_votes = [v for v in votes.values() if v is not None]

    # Calculate consensus from non-null votes
    yes_votes = sum(1 for v in non_null_votes if v.get("direction") == "YES")
    no_votes = sum(1 for v in non_null_votes if v.get("direction") == "NO")
    skip_votes = sum(1 for v in non_null_votes if v.get("direction") == "SKIP")

    # Determine consensus direction with tie-breaker
    if yes_votes > no_votes:
        consensus_direction = "YES"
    elif no_votes > yes_votes:
        consensus_direction = "NO"
    else:
        # TIE-BREAKER: 2-2 split
        # Rule 1: Quant agent breaks ties (price action is strongest signal)
        quant_dir = quant_vote.get("direction", "SKIP")
        if quant_dir in ["YES", "NO"]:
            consensus_direction = quant_dir
        else:
            # Rule 2: Use highest confidence agent
            conf_scores = {"high": 3, "medium": 2, "low": 1}
            best_conf = 0
            best_dir = "SKIP"
            for agent_name, vote in votes.items():
                if vote.get("direction") in ["YES", "NO"]:
                    conf = conf_scores.get(vote.get("confidence", "low"), 1)
                    if conf > best_conf:
                        best_conf = conf
                        best_dir = vote.get("direction")
            consensus_direction = best_dir

    # Determine agreement level (including post-tie-break consensus)
    majority = max(yes_votes, no_votes)
    if majority >= PANEL_STRONG_MAJORITY:
        agreement = "strong"
    elif majority >= PANEL_MODERATE_MAJORITY:
        agreement = "moderate"
    else:
        agreement = "weak"

    # Calculate average estimated probability (ignore None and SKIP)
    valid_probs = [v.get("estimated_probability", DEFAULT_AGENT_ACCURACY) for v in non_null_votes if v.get("direction") != "SKIP"]
    avg_prob = sum(valid_probs) / len(valid_probs) if valid_probs else DEFAULT_AGENT_ACCURACY

    return {
        "votes": votes,
        "yes_count": yes_votes,
        "no_count": no_votes,
        "skip_count": skip_votes,
        "agreement": agreement,
        "avg_estimated_probability": avg_prob,
        "consensus_direction": consensus_direction
    }


def run_panel_voting(markets: List[Dict[str, Any]], memory_context: Dict[str, Any] = None, insider_signals: Dict[str, Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Run panel voting on multiple markets.
    Wrapper for main.py compatibility.

    Args:
        markets: List of market data dicts
        memory_context: Optional memory context for learning
        insider_signals: Optional dict mapping market_id/wallet to insider data
                         Format: {market_id: {'score': int, 'direction': 'YES|NO', 'wallet': str, 'pattern': str}}

    Returns:
        List of markets with panel_vote field added
    """
    if memory_context is None:
        memory_context = {
            "quant_accuracy": DEFAULT_AGENT_ACCURACY,
            "contrarian_accuracy": DEFAULT_AGENT_ACCURACY,
            "journalist_accuracy": DEFAULT_AGENT_ACCURACY,
            "risk_accuracy": DEFAULT_AGENT_ACCURACY
        }

    if insider_signals is None:
        insider_signals = {}

    results = []
    for market in markets:
        # Look up insider signals for this market
        market_id = market.get('id', market.get('title', 'unknown'))
        market_insider = insider_signals.get(market_id, {})

        vote = run_panel_vote(market, memory_context, market_insider if market_insider else None)
        market["panel_vote"] = vote
        results.append(market)

    return results


if __name__ == "__main__":
    # Test the module
    print("Testing Panel Agents...")

    test_market = {
        "title": "Will Bitcoin hit $100k by end of 2024?",
        "category": "crypto",
        "yes_price": 45.0,
        "no_price": 55.0,
        "volume": 100000,
        "research": {
            "confidence": "medium",
            "articles_found": 3
        }
    }

    memory = {
        "quant_accuracy": 60,
        "contrarian_accuracy": 55,
        "journalist_accuracy": 45,
        "risk_accuracy": 50
    }

    result = run_panel_vote(test_market, memory)
    print(f"Yes votes: {result['yes_count']}")
    print(f"No votes: {result['no_count']}")
    print(f"Agreement: {result['agreement']}")
    print(f"Consensus: {result['consensus_direction']}")
