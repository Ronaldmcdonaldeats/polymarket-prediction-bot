#!/usr/bin/env python3
"""
Memory System Module
Handles all JSON I/O operations for the memory system.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

MEMORY_DIR = "memory"


def load_json(path: str, default: Any = None) -> Any:
    """Load JSON file with default fallback."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path: str, data: Any):
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_predictions() -> List[Dict]:
    """Load predictions.json."""
    return load_json(f"{MEMORY_DIR}/predictions.json", [])


def save_prediction(prediction: Dict):
    """Append prediction to predictions.json."""
    predictions = load_predictions()
    predictions.append(prediction)
    save_json(f"{MEMORY_DIR}/predictions.json", predictions)


def update_prediction(market_id: str, updates: Dict):
    """Update an existing prediction by market_id."""
    predictions = load_predictions()
    for pred in predictions:
        if pred.get("market_id") == market_id:
            pred.update(updates)
    save_json(f"{MEMORY_DIR}/predictions.json", predictions)


def save_lesson(lesson: Dict):
    """Append a lesson to lessons.json."""
    lessons = load_lessons()
    if "lessons" not in lessons:
        lessons["lessons"] = []
    lessons["lessons"].append(lesson)
    lessons["last_updated"] = datetime.now().isoformat()
    save_json(f"{MEMORY_DIR}/lessons.json", lessons)


def load_lessons() -> Dict:
    """Load lessons.json."""
    return load_json(f"{MEMORY_DIR}/lessons.json", {
        "lessons": [],
        "pattern_insights": [],
        "last_updated": None
    })


def save_lessons(lessons: Dict):
    """Save lessons.json."""
    save_json(f"{MEMORY_DIR}/lessons.json", lessons)


def load_agent_scores() -> Dict:
    """Load agent_scores.json."""
    return load_json(f"{MEMORY_DIR}/agent_scores.json", {
        "quant": {"wins": 0, "losses": 0, "by_category": {}},
        "contrarian": {"wins": 0, "losses": 0, "by_category": {}},
        "journalist": {"wins": 0, "losses": 0, "by_category": {}},
        "risk_manager": {"wins": 0, "losses": 0, "by_category": {}}
    })


def save_agent_scores(scores: Dict):
    """Save agent_scores.json."""
    save_json(f"{MEMORY_DIR}/agent_scores.json", scores)


def load_multipliers() -> Dict:
    """Load multipliers.json."""
    return load_json(f"{MEMORY_DIR}/multipliers.json", {
        "version": 1,
        "last_tuned": None,
        "total_resolved": 0,
        "overall_accuracy": None,
        "kelly": {
            "base_fraction": 0.5,
            "bankroll": 500
        },
        "confidence_mult": {"high": 1.0, "medium": 0.6, "low": 0.3},
        "panel_mult": {"strong": 1.0, "moderate": 0.7, "weak": 0.4},
        "whale_mult": {"agrees": 1.15, "disagrees_or_unknown": 0.85},
        "cross_platform_mult": {"strong": 1.20, "moderate": 1.05, "weak": 0.90},
        "kalshi_mult": {"strong": 1.15, "moderate": 1.05, "aligned": 1.0, "unavailable": 1.0},
        "category_bonus": {
            "economics": 20,
            "politics": 10,
            "ai_tech": 5,
            "sports": -100,
            "crypto": -100
        },
        "min_volume": 50000,
        "min_edge_to_bet": 10,
        "notes": "Default values - not yet tuned"
    })


def save_multipliers(multipliers: Dict):
    """Save multipliers.json."""
    save_json(f"{MEMORY_DIR}/multipliers.json", multipliers)


def load_tuning_log() -> List[Dict]:
    """Load tuning_log.json."""
    return load_json(f"{MEMORY_DIR}/tuning_log.json", [])


def save_tuning_log(log: List[Dict]):
    """Save tuning_log.json."""
    save_json(f"{MEMORY_DIR}/tuning_log.json", log)


def load_recently_recommended() -> List[str]:
    """Load list of recently recommended market IDs from the last 24 hours."""
    data = load_json(f"{MEMORY_DIR}/recently_recommended.json", {})
    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        return []

    # Filter to last 3 hours (shorter window to allow more markets)
    cutoff = datetime.now() - timedelta(hours=3)
    recent = [
        r["market_id"] for r in recommendations
        if isinstance(r, dict)
        and "timestamp" in r
        and "market_id" in r
        and datetime.fromisoformat(r["timestamp"]) > cutoff
    ]
    return recent


def add_recently_recommended(market_ids: List[str]):
    """Add market IDs to recently recommended list."""
    data = load_json(f"{MEMORY_DIR}/recently_recommended.json", {"recommendations": []})

    for market_id in market_ids:
        data["recommendations"].append({
            "market_id": market_id,
            "timestamp": datetime.now().isoformat()
        })

    save_json(f"{MEMORY_DIR}/recently_recommended.json", data)


def load_keyword_performance() -> Dict:
    """Load keyword_performance.json with performance tracking for each keyword."""
    return load_json(f"{MEMORY_DIR}/keyword_performance.json", {})


def save_keyword_performance(performance: Dict):
    """Save keyword_performance.json."""
    save_json(f"{MEMORY_DIR}/keyword_performance.json", performance)


def load_whale_alerts_sent() -> List[Dict]:
    """
    Load list of whale/insider alerts already sent.
    Tracks alerts by wallet + market_id + alert_type combination.
    """
    data = load_json(f"{MEMORY_DIR}/whale_alerts_sent.json", {"alerts": []})
    return data.get("alerts", [])


def save_whale_alert_sent(market_id: str, wallet: str, alert_type: str, amount: float):
    """
    Save a whale/insider alert that was sent.

    Args:
        market_id: Market identifier
        wallet: Wallet address that triggered the alert
        alert_type: "WHALE" or "INSIDER"
        amount: Amount of the alert
    """
    data = load_json(f"{MEMORY_DIR}/whale_alerts_sent.json", {"alerts": []})

    # Create unique key for this alert
    alert_key = f"{wallet}_{market_id}_{alert_type}"

    data["alerts"].append({
        "market_id": market_id,
        "wallet": wallet,
        "alert_type": alert_type,
        "amount": amount,
        "alert_key": alert_key,
        "timestamp": datetime.now().isoformat()
    })

    # Keep only last 30 days of alerts to prevent file bloat
    cutoff = datetime.now() - timedelta(days=30)
    data["alerts"] = [
        a for a in data["alerts"]
        if datetime.fromisoformat(a["timestamp"]) > cutoff
    ]

    save_json(f"{MEMORY_DIR}/whale_alerts_sent.json", data)


def has_whale_alert_been_sent(market_id: str, wallet: str, alert_type: str) -> bool:
    """
    Check if a whale/insider alert has already been sent.

    Args:
        market_id: Market identifier
        wallet: Wallet address
        alert_type: "WHALE" or "INSIDER"

    Returns:
        True if alert was already sent
    """
    alerts = load_whale_alerts_sent()
    alert_key = f"{wallet}_{market_id}_{alert_type}"

    for alert in alerts:
        if alert.get("alert_key") == alert_key:
            return True

    return False


def ensure_memory_files():
    """Create all memory files if they don't exist."""
    os.makedirs(MEMORY_DIR, exist_ok=True)

    files = {
        "predictions.json": [],
        "lessons.json": {
            "lessons": [],
            "pattern_insights": [],
            "last_updated": None
        },
        "agent_scores.json": {
            "quant": {"wins": 0, "losses": 0, "by_category": {}},
            "contrarian": {"wins": 0, "losses": 0, "by_category": {}},
            "journalist": {"wins": 0, "losses": 0, "by_category": {}},
            "risk_manager": {"wins": 0, "losses": 0, "by_category": {}}
        },
        "keyword_performance.json": {},
        "multipliers.json": {
            "version": 1,
            "last_tuned": None,
            "total_resolved": 0,
            "overall_accuracy": None,
            "kelly": {
                "base_fraction": 0.5,
                "bankroll": 500
            },
            "confidence_mult": {"high": 1.0, "medium": 0.6, "low": 0.3},
            "panel_mult": {"strong": 1.0, "moderate": 0.7, "weak": 0.4},
            "whale_mult": {"agrees": 1.15, "disagrees_or_unknown": 0.85},
            "cross_platform_mult": {"strong": 1.20, "moderate": 1.05, "weak": 0.90},
            "category_bonus": {
                "economics": 20,
                "politics": 10,
                "ai_tech": 5,
                "sports": -100,
                "crypto": -100
            },
            "min_volume": 50000,
            "min_edge_to_bet": 10,
            "notes": "Default values - not yet tuned"
        },
        "tuning_log.json": [],
        "recently_recommended.json": {"recommendations": []},
        "whale_alerts_sent.json": {"alerts": []}
    }

    for filename, default_data in files.items():
        filepath = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(filepath):
            save_json(filepath, default_data)
            print(f"  Created {filepath}")
