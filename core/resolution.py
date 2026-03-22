#!/usr/bin/env python3
"""
Resolution Checker Module
Checks for newly resolved Polymarket predictions and updates scores.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from utils.memory_system import load_json, save_json

from data.data_fetcher import update_keyword_performance

MEMORY_DIR = "memory"


def fetch_polymarket_data(market_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch market data from Polymarket Gamma API.

    Args:
        market_id: The market slug or condition ID

    Returns:
        Market data dict or None if not found/error
    """
    try:
        url = f"https://gamma-api.polymarket.com/markets?slug={market_id}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) == 0:
            return None

        return data[0]
    except Exception:
        return None


def is_market_resolved(market_data: Dict[str, Any]) -> bool:
    """
    Check if market is resolved.

    Args:
        market_data: Market data from Polymarket API

    Returns:
        True if market is resolved, False otherwise
    """
    if not market_data:
        return False
    return market_data.get("closed") and "resolutionPrice" in market_data


def get_winning_outcome(market_data: Dict[str, Any]) -> Optional[str]:
    """
    Get winning outcome (YES/NO).

    Args:
        market_data: Market data from Polymarket API

    Returns:
        'YES' if resolutionPrice is 1.0, 'NO' if 0.0, None otherwise
    """
    if not is_market_resolved(market_data):
        return None

    resolution = float(market_data.get("resolutionPrice", -1))
    if resolution == 1.0:
        return "YES"
    elif resolution == 0.0:
        return "NO"
    return None


def check_prediction_resolution(prediction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check if a single prediction is resolved.

    Args:
        prediction: Prediction dict with 'slug' field

    Returns:
        Updated prediction if resolved, None otherwise
    """
    if prediction.get("resolved", False):
        return None

    slug = prediction.get("market_slug", "")
    if not slug:
        return None

    market_data = fetch_polymarket_data(slug)
    if not market_data:
        return None

    if is_market_resolved(market_data):
        outcome = get_winning_outcome(market_data)
        if outcome:
            prediction["resolved"] = True
            prediction["resolution"] = float(market_data["resolutionPrice"])
            prediction["outcome"] = "WIN" if outcome == prediction.get("bet_direction") else "LOSS"
            prediction["resolved_at"] = datetime.now().isoformat()
            return prediction

    return None


def update_prediction_outcome(prediction: Dict[str, Any], outcome: str) -> Dict[str, Any]:
    """
    Update prediction with outcome.

    Args:
        prediction: Prediction dict to update
        outcome: 'WIN' or 'LOSS'

    Returns:
        Updated prediction dict
    """
    prediction["outcome"] = outcome
    prediction["resolved"] = True
    prediction["resolved_at"] = datetime.now().isoformat()
    return prediction


def update_agent_scores(prediction: Dict[str, Any], outcome: str, agent_scores: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update win/loss counts for agents based on prediction outcome.

    Args:
        prediction: Prediction dict containing vote_breakdown
        outcome: 'WIN' or 'LOSS'
        agent_scores: Current agent scores dict

    Returns:
        Updated agent scores dict
    """
    vote_breakdown = prediction.get("vote_breakdown", {})
    bet_direction = prediction.get("bet_direction")

    if not bet_direction:
        return agent_scores

    for agent_name, vote in vote_breakdown.items():
        if isinstance(vote, dict) and "direction" in vote:
            if agent_name not in agent_scores:
                agent_scores[agent_name] = {"wins": 0, "losses": 0, "by_category": {}}

            if vote["direction"] == bet_direction:
                agent_scores[agent_name]["wins"] += 1
            else:
                agent_scores[agent_name]["losses"] += 1

    return agent_scores


def run_resolution_check() -> List[Dict[str, Any]]:
    """
    Main function to check all pending predictions.

    Returns:
        List of newly resolved predictions
    """
    print("=" * 60)
    print("Resolution Checker")
    print("=" * 60)

    predictions = load_json(f"{MEMORY_DIR}/predictions.json", [])
    agent_scores = load_json(f"{MEMORY_DIR}/agent_scores.json", {
        "quant": {"wins": 0, "losses": 0, "by_category": {}},
        "contrarian": {"wins": 0, "losses": 0, "by_category": {}},
        "journalist": {"wins": 0, "losses": 0, "by_category": {}},
        "risk_manager": {"wins": 0, "losses": 0, "by_category": {}}
    })

    newly_resolved = []

    for pred in predictions:
        if pred.get("resolved", False):
            continue

        slug = pred.get("slug", "")
        if not slug:
            continue

        try:
            market_data = fetch_polymarket_data(slug)
            if market_data and is_market_resolved(market_data):
                outcome = get_winning_outcome(market_data)
                if outcome:
                    bet_dir = pred.get("bet_direction", "")
                    result = "WIN" if outcome == bet_dir else "LOSS"

                    pred["resolved"] = True
                    pred["resolution"] = float(market_data["resolutionPrice"])
                    pred["outcome"] = result
                    pred["resolved_at"] = datetime.now().isoformat()

                    # Update keyword performance tracking
                    market_title = pred.get("market_title", "")
                    if market_title:
                        update_keyword_performance(market_title, result)

                    newly_resolved.append(pred)
                    print(f"  Resolved: {pred['market_title'][:50]}... -> {result}")

        except Exception as e:
            print(f"  Error checking {slug}: {e}")
            continue

    if newly_resolved:
        save_json(f"{MEMORY_DIR}/predictions.json", predictions)

        # Update agent scores
        for pred in newly_resolved:
            agent_scores = update_agent_scores(pred, pred["outcome"], agent_scores)

        save_json(f"{MEMORY_DIR}/agent_scores.json", agent_scores)

        wins = sum(1 for p in newly_resolved if p["outcome"] == "WIN")
        losses = len(newly_resolved) - wins
        print(f"\n[OK] Resolution check complete - {len(newly_resolved)} resolved ({wins}W / {losses}L)")
    else:
        print("[OK] Resolution check - 0 new resolutions")

    return newly_resolved


def check_resolved_predictions() -> List[Dict[str, Any]]:
    """
    Check for resolved predictions.
    Alias for run_resolution_check.
    """
    return run_resolution_check()


def update_all_scores(resolved_predictions: List[Dict[str, Any]]):
    """
    Update all scores after predictions are resolved.
    This is called after check_resolved_predictions to ensure scores are updated.
    """
    # Scores are already updated by run_resolution_check
    # This function exists for explicit score recalculation if needed
    from utils.memory_system import load_agent_scores, save_agent_scores

    agent_scores = load_agent_scores()

    for pred in resolved_predictions:
        outcome = pred.get("outcome", "")
        if outcome:
            agent_scores = update_agent_scores(pred, outcome, agent_scores)

    save_agent_scores(agent_scores)
    print(f"  Updated agent scores with {len(resolved_predictions)} resolved predictions")


if __name__ == "__main__":
    run_resolution_check()
