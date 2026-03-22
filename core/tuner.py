#!/usr/bin/env python3
"""
Self Tuner Module
Tunes multipliers based on resolved prediction performance.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

import requests

from utils.memory_system import load_json, save_json

MEMORY_DIR = "memory"


def calculate_accuracy(predictions: List[Dict[str, Any]]) -> float:
    """
    Calculate overall accuracy from resolved predictions.

    Args:
        predictions: List of prediction dicts

    Returns:
        Accuracy as float between 0.0 and 1.0
    """
    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]
    if not resolved:
        return 0.0

    wins = sum(1 for p in resolved if p["outcome"] == "WIN")
    return wins / len(resolved)


def calculate_agent_performance(predictions: List[Dict[str, Any]], agent_scores: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate performance by agent.

    Args:
        predictions: List of prediction dicts
        agent_scores: Current agent scores dict

    Returns:
        Dict mapping agent name to win rate percentage
    """
    performance = {}

    for agent_name, scores in agent_scores.items():
        total = scores.get("wins", 0) + scores.get("losses", 0)
        if total > 0:
            performance[agent_name] = (scores["wins"] / total) * 100
        else:
            performance[agent_name] = 0.0

    return performance


def calculate_category_performance(predictions: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """
    Calculate performance by category.

    Args:
        predictions: List of prediction dicts

    Returns:
        Dict mapping category to performance stats
    """
    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]

    category_stats = {}
    for pred in resolved:
        cat = pred.get("category", "other")
        if cat not in category_stats:
            category_stats[cat] = {"wins": 0, "losses": 0, "total": 0}

        category_stats[cat]["total"] += 1
        if pred["outcome"] == "WIN":
            category_stats[cat]["wins"] += 1
        else:
            category_stats[cat]["losses"] += 1

    # Calculate win rates
    result = {}
    for cat, stats in category_stats.items():
        result[cat] = {
            "win_rate": stats["wins"] / stats["total"] if stats["total"] > 0 else 0,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "total": stats["total"]
        }

    return result


def find_best_multiplier_range(param_name: str, predictions: List[Dict[str, Any]], step: float = 0.1) -> Tuple[float, float]:
    """
    Grid search for best multiplier value.

    Args:
        param_name: Name of the parameter to tune
        predictions: List of resolved predictions
        step: Step size for grid search

    Returns:
        Tuple of (best_value, best_score)
    """
    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]
    if len(resolved) < 5:
        return (1.0, 0.0)

    # Test values from 0.2 to 2.0
    test_values = [round(0.2 + (step * i), 2) for i in range(int(1.8 / step) + 1)]
    best_value = 1.0
    best_score = 0.0

    for value in test_values:
        # Simulate what score would be with this multiplier
        wins = 0
        for pred in resolved:
            # Simple simulation: higher multiplier = more likely to bet
            edge = pred.get("edge_percent", 0)
            if edge * value >= 10:  # Would have bet
                if pred["outcome"] == "WIN":
                    wins += 1

        score = wins / len(resolved) if resolved else 0
        if score > best_score:
            best_score = score
            best_value = value

    return (best_value, best_score)


def apply_tuned_values(multipliers: Dict[str, Any], tuned: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply tuned values to multipliers.

    Args:
        multipliers: Current multipliers dict
        tuned: Tuned values dict from run_tuning

    Returns:
        Updated multipliers dict
    """
    if "confidence_mult" in tuned:
        for key, value in tuned["confidence_mult"].items():
            if key in multipliers.get("confidence_mult", {}):
                multipliers["confidence_mult"][key] = value

    if "panel_mult" in tuned:
        for key, value in tuned["panel_mult"].items():
            if key in multipliers.get("panel_mult", {}):
                multipliers["panel_mult"][key] = value

    if "category_bonus" in tuned:
        for key, value in tuned["category_bonus"].items():
            multipliers["category_bonus"][key] = value

    if "min_edge_to_bet" in tuned:
        multipliers["min_edge_to_bet"] = tuned["min_edge_to_bet"]

    multipliers["last_tuned"] = datetime.now().isoformat()

    return multipliers


def should_tune() -> Tuple[bool, int]:
    """
    Check if 3+ resolved predictions exist.

    Returns:
        Tuple of (should_tune, resolved_count)
    """
    predictions = load_json(f"{MEMORY_DIR}/predictions.json", [])
    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]

    return (len(resolved) >= 3, len(resolved))


def format_tuning_report(tuned: Dict[str, Any]) -> str:
    """
    Format human-readable tuning report.

    Args:
        tuned: Tuned values dict from run_tuning

    Returns:
        Formatted report string
    """
    lines = ["=" * 60]
    lines.append("Self-Tuning Report")
    lines.append("=" * 60)
    lines.append(f"Timestamp: {tuned.get('timestamp', 'N/A')}")
    lines.append(f"Total Resolved: {tuned.get('total_resolved', 0)}")
    lines.append(f"Overall Accuracy: {tuned.get('overall_accuracy', 0) * 100:.1f}%")
    lines.append("")

    if "confidence_mult" in tuned:
        lines.append("Confidence Multipliers:")
        for key, value in tuned["confidence_mult"].items():
            lines.append(f"  {key}: {value:.3f}")
        lines.append("")

    if "panel_mult" in tuned:
        lines.append("Panel Multipliers:")
        for key, value in tuned["panel_mult"].items():
            lines.append(f"  {key}: {value:.3f}")
        lines.append("")

    if "category_bonus" in tuned:
        lines.append("Category Bonuses:")
        for key, value in tuned["category_bonus"].items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    if "changes" in tuned and tuned["changes"]:
        lines.append("Changes Made:")
        for change in tuned["changes"]:
            lines.append(f"  {change['field']}: {change['old']} -> {change['new']}")
    else:
        lines.append("No significant changes made.")

    lines.append("")
    return "\n".join(lines)


def run_tuning(predictions: List[Dict[str, Any]], agent_scores: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main tuning function.

    Args:
        predictions: List of resolved predictions
        agent_scores: Current agent scores

    Returns:
        Tuned values dict
    """
    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]
    total_resolved = len(resolved)

    if total_resolved < 3:
        return {
            "timestamp": datetime.now().isoformat(),
            "total_resolved": total_resolved,
            "error": "Need at least 3 resolved predictions"
        }

    overall_accuracy = calculate_accuracy(predictions)

    tuned = {
        "timestamp": datetime.now().isoformat(),
        "total_resolved": total_resolved,
        "overall_accuracy": overall_accuracy,
        "confidence_mult": {},
        "panel_mult": {},
        "category_bonus": {},
        "changes": []
    }

    # Signal analysis
    signals_to_tune = [
        ("confidence_level", ["high", "medium", "low"]),
        ("panel_agreement", ["strong", "moderate", "weak"]),
    ]

    multipliers = load_json(f"{MEMORY_DIR}/multipliers.json", {})

    for signal_name, values in signals_to_tune:
        for value in values:
            matches = [p for p in resolved if p.get(signal_name) == value]

            if len(matches) >= 3:
                signal_wins = sum(1 for p in matches if p["outcome"] == "WIN")
                signal_win_rate = signal_wins / len(matches)

                performance_ratio = signal_win_rate / overall_accuracy if overall_accuracy > 0 else 1

                mult_key_map = {
                    "confidence_level": "confidence_mult",
                    "panel_agreement": "panel_mult"
                }

                mult_key = mult_key_map.get(signal_name)
                if mult_key and value.lower() in multipliers.get(mult_key, {}):
                    old_val = multipliers[mult_key][value.lower()]
                    new_val = (old_val * 0.70) + (performance_ratio * 0.30)
                    new_val = max(0.2, min(2.0, new_val))

                    if abs(new_val - old_val) / old_val > 0.05:
                        tuned[mult_key][value.lower()] = round(new_val, 3)
                        tuned["changes"].append({
                            "field": f"{mult_key}.{value}",
                            "old": old_val,
                            "new": round(new_val, 3),
                            "sample_size": len(matches),
                            "win_rate": round(signal_win_rate * 100, 1)
                        })

    # Category tuning
    categories = {}
    for p in resolved:
        cat = p.get("category", "other")
        categories.setdefault(cat, []).append(p)

    for cat, matches in categories.items():
        if len(matches) >= 3:
            cat_wins = sum(1 for p in matches if p["outcome"] == "WIN")
            cat_win_rate = cat_wins / len(matches)

            if cat_win_rate > 0.65:
                tuned["category_bonus"][cat] = min(30, multipliers.get("category_bonus", {}).get(cat, 0) + 5)
            elif cat_win_rate < 0.45:
                tuned["category_bonus"][cat] = multipliers.get("category_bonus", {}).get(cat, 0) - 5

    # Edge threshold tuning
    edge_buckets = {"<10": [], "10-20": [], "20-30": [], "30+": []}
    for p in resolved:
        edge = p.get("edge_percent", 0)
        if edge < 10:
            edge_buckets["<10"].append(p)
        elif edge < 20:
            edge_buckets["10-20"].append(p)
        elif edge < 30:
            edge_buckets["20-30"].append(p)
        else:
            edge_buckets["30+"].append(p)

    if len(edge_buckets["<10"]) >= 3:
        low_edge_wins = sum(1 for p in edge_buckets["<10"] if p["outcome"] == "WIN")
        if low_edge_wins / len(edge_buckets["<10"]) < 0.45:
            tuned["min_edge_to_bet"] = 15
            tuned["changes"].append({
                "field": "min_edge_to_bet",
                "old": 10,
                "new": 15,
                "reason": "Edge <10% win rate <45%",
                "sample_size": len(edge_buckets["<10"])
            })

    return tuned


def main():
    """Main entry point for self-tuner."""
    print("\n" + "=" * 60)
    print("Self Tuner")
    print("=" * 60)

    should_run, resolved_count = should_tune()

    if not should_run:
        print(f"⏳ Need {3 - resolved_count} more resolved bets before tuning")
        return

    if resolved_count % 3 != 0:
        print(f"⏳ Tuning runs every 3 bets (currently {resolved_count})")
        return

    predictions = load_json(f"{MEMORY_DIR}/predictions.json", [])
    agent_scores = load_json(f"{MEMORY_DIR}/agent_scores.json", {})
    multipliers = load_json(f"{MEMORY_DIR}/multipliers.json", {})

    tuned = run_tuning(predictions, agent_scores)

    # Apply tuned values
    multipliers = apply_tuned_values(multipliers, tuned)
    multipliers["total_resolved"] = resolved_count
    multipliers["overall_accuracy"] = tuned.get("overall_accuracy")

    save_json(f"{MEMORY_DIR}/multipliers.json", multipliers)

    # Log changes
    log = load_json(f"{MEMORY_DIR}/tuning_log.json", [])
    for change in tuned.get("changes", []):
        log.append({
            "timestamp": datetime.now().isoformat(),
            "total_resolved_at_time": resolved_count,
            **change
        })
    save_json(f"{MEMORY_DIR}/tuning_log.json", log)

    print(f"[OK] Self-tuning complete — {len(tuned.get('changes', []))} multipliers adjusted")
    print(f"  Running accuracy: {tuned.get('overall_accuracy', 0) * 100:.1f}% over {resolved_count} bets")

    # Print report
    print(format_tuning_report(tuned))


def run_self_tuning() -> Dict[str, Any]:
    """
    Run self-tuning check (wrapper for main.py compatibility).

    Returns:
        Dict with tuning result info
    """
    should_run, resolved_count = should_tune()

    if not should_run:
        return {
            "tuned": False,
            "reason": f"Need {3 - resolved_count} more resolved bets before tuning"
        }

    if resolved_count % 3 != 0:
        return {
            "tuned": False,
            "reason": f"Tuning runs every 3 bets (currently {resolved_count})"
        }

    # Load data
    predictions = load_json(f"{MEMORY_DIR}/predictions.json", [])
    agent_scores = load_json(f"{MEMORY_DIR}/agent_scores.json", {})
    multipliers = load_json(f"{MEMORY_DIR}/multipliers.json", {})

    # Run tuning
    tuned = run_tuning(predictions, agent_scores)

    # Apply tuned values
    multipliers = apply_tuned_values(multipliers, tuned)
    multipliers["total_resolved"] = resolved_count
    multipliers["overall_accuracy"] = tuned.get("overall_accuracy")

    save_json(f"{MEMORY_DIR}/multipliers.json", multipliers)

    # Log changes
    log = load_json(f"{MEMORY_DIR}/tuning_log.json", [])
    for change in tuned.get("changes", []):
        log.append({
            "timestamp": datetime.now().isoformat(),
            "total_resolved_at_time": resolved_count,
            **change
        })
    save_json(f"{MEMORY_DIR}/tuning_log.json", log)

    return {
        "tuned": True,
        "accuracy": tuned.get("overall_accuracy", 0),
        "changes": len(tuned.get("changes", [])),
        "total_resolved": resolved_count
    }


if __name__ == "__main__":
    main()
