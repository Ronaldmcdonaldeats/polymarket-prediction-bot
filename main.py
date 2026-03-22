#!/usr/bin/env python3
"""
Polymarket Prediction Bot - Main Entry Point
4-Agent Panel with Judge, Memory System, and Cross-Platform Consensus
"""

import os
import sys
import time
import json
import signal
from typing import List, Dict
from datetime import datetime, timedelta

# Import all modules
from utils.config import (
    LOW_RISK_EDGE_HIGH_CONF,
    LOW_RISK_EDGE_MED_CONF,
    MAX_LOW_RISK_BETS,
    MAX_HIGH_RISK_BETS,
    CYCLE_INTERVAL_SECONDS,
    RETRY_DELAY_SECONDS,
    MIN_STAKE_USD
)
from utils.conversions import smart_truncate
from core.startup import startup_checks
from utils.memory_system import (
    load_predictions, save_prediction, update_prediction,
    load_agent_scores, save_agent_scores,
    load_lessons, save_lesson,
    load_recently_recommended, add_recently_recommended,
    load_multipliers, has_whale_alert_been_sent, save_whale_alert_sent
)
from data.data_fetcher import fetch_filtered_markets
from data.research_fetcher import fetch_research_for_markets
from data.cross_platform import fetch_consensus_for_markets
from alerts.whale_tracker import (
    fetch_whale_activity_for_markets,
    check_whale_insider_for_markets,
    format_est_time
)
from agents.gemini_synthesis import synthesize_cross_market_insights
from agents.panel_agents import run_panel_voting
from agents.judge import judge_decision
from core.kelly_calculator import calculate_stake
from alerts.discord_webhook import send_bet_embed, send_error_embed, send_batch_bet_embeds, send_whale_alert_embed
from core.resolution import check_resolved_predictions, update_all_scores
from core.tuner import run_self_tuning
from data.kalshi_fetcher import fetch_kalshi_markets, match_kalshi
from concurrent.futures import ThreadPoolExecutor

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    print("\n\n[SHUTDOWN] Stop requested. Finishing current cycle...")
    shutdown_requested = True


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def classify_risk(bet: Dict) -> str:
    """
    Classify bet as LOW or HIGH risk based on confidence and edge.

    LOW RISK: High confidence + moderate edge
    HIGH RISK: Lower confidence but high potential edge
    """
    confidence = bet.get("confidence", "low")
    edge = bet.get("edge", 0)  # Already percentage from judge

    # Low risk: high confidence with reasonable edge
    if confidence == "high" and edge >= LOW_RISK_EDGE_HIGH_CONF:
        return "LOW"
    elif confidence == "medium" and edge >= LOW_RISK_EDGE_MED_CONF:
        return "LOW"
    else:
        return "HIGH"


def get_top_bets(panel_results: List[Dict], multipliers: Dict, exclude_ids: List[str] = None, low_risk_count: int = 5, high_risk_count: int = 5) -> List[Dict]:
    """
    Get top N LOW RISK and top N HIGH RISK bets from panel results.

    Args:
        panel_results: List of markets with panel votes
        multipliers: Current multipliers
        exclude_ids: Market IDs to exclude (already recommended recently)
        low_risk_count: Number of low risk bets to return
        high_risk_count: Number of high risk bets to return

    Returns:
        List of bet decisions (low risk first, then high risk)
    """
    exclude_ids = exclude_ids or []

    all_bets = []

    for market in panel_results:
        market_id = market.get("conditionId", "")

        # Skip if recently recommended
        if market_id in exclude_ids:
            continue

        panel_votes = market.get("panel_vote", {})
        if not panel_votes:
            continue

        decision = judge_decision(market, panel_votes, multipliers)

        if decision.get("decision") in ["YES", "NO"]:
            # Calculate score based on edge and confidence
            edge = decision.get("edge_percent", 0)
            confidence = decision.get("final_confidence", "low")
            conf_score = {"high": 3, "medium": 2, "low": 1}.get(confidence, 1)
            score = edge * conf_score

            # Build full bet dict
            bet = {
                "market_id": market_id,
                "market_title": market.get("title", ""),
                "market_slug": market.get("slug", ""),
                "event_slug": market.get("event_slug", ""),
                "market_probability": market.get("yes_price", 50) / 100,
                "our_probability": decision.get("estimated_probability", 50) / 100,
                "direction": decision.get("decision", "SKIP"),
                "confidence": confidence,
                "edge": edge,
                "consensus": panel_votes.get("consensus_direction", "TIED"),
                "whale_signal": market.get("whale_signal", "UNKNOWN"),
                "panel_agreement": market.get("panel_agreement", "weak"),
                "cross_platform_signal": market.get("cross_platform_signal", "WEAK"),
                "category": market.get("category", "other"),
                "panel_votes": panel_votes,
                "vote_breakdown": panel_votes.get("vote_breakdown", {}),
                "reasoning": decision.get("reasoning", ""),
                "score": score
            }

            # Classify risk
            bet["risk_level"] = classify_risk(bet)
            all_bets.append(bet)

    # Separate into low and high risk
    low_risk_bets = [b for b in all_bets if b["risk_level"] == "LOW"]
    high_risk_bets = [b for b in all_bets if b["risk_level"] == "HIGH"]

    # Sort each by score
    low_risk_bets.sort(key=lambda x: x["score"], reverse=True)
    high_risk_bets.sort(key=lambda x: x["score"], reverse=True)

    # Take top N from each
    selected_low = low_risk_bets[:low_risk_count]
    selected_high = high_risk_bets[:high_risk_count]

    # Combine: low risk first, then high risk
    top_bets = selected_low + selected_high

    print(f"  [INFO] Selected {len(selected_low)} LOW risk bets, {len(selected_high)} HIGH risk bets")

    return top_bets


def run_cycle():
    """Run a single betting cycle. Returns number of bets placed."""
    start_time = time.time()
    cycle_timestamp = datetime.now().isoformat()
    print("\n" + "=" * 60)
    print(f">>> CYCLE START: {cycle_timestamp}")
    print("=" * 60)

    # Step 1: Run startup checks
    print("\n[1] Step 1: Running startup checks...")
    if not startup_checks():
        print("[X] Startup checks failed. Skipping cycle.")
        return 0
    print("[OK] Startup checks passed")

    # Step 2: Check for resolved predictions and update scores
    print("\n[2] Step 2: Checking resolved predictions...")
    resolved = check_resolved_predictions()
    if resolved:
        print(f"[OK] Updated {len(resolved)} resolved predictions")
        update_all_scores(resolved)
    else:
        print("[i] No newly resolved predictions")

    # Step 3: Run self-tuning if we have new data
    print("\n[3] Step 3: Running self-tuning...")
    tuning_result = run_self_tuning()
    if tuning_result.get("tuned", False):
        print(f"[OK] Tuning complete - New accuracy: {tuning_result.get('accuracy', 'N/A')}")
    else:
        print(f"[i] {tuning_result.get('reason', 'No tuning needed')}")

    # Step 4: Fetch markets from Polymarket
    print("\n[4] Step 4: Fetching markets from Polymarket...")
    try:
        markets = fetch_filtered_markets()
        if not markets:
            print("[WARN] No markets found matching criteria")
            send_error_embed("No Markets Found", "No active markets found matching volume/time filters")
            return 0
        print(f"[OK] Found {len(markets)} candidate markets")
    except Exception as e:
        print(f"[X] Error fetching markets: {e}")
        send_error_embed("Market Fetch Error", str(e))
        return 0

    # Step 4.5: Fetch Kalshi markets and match
    print("\n[KALSHI] Step 4.5: Fetching Kalshi markets...")
    try:
        kalshi_markets = fetch_kalshi_markets()
        if kalshi_markets:
            # Enrich each market with Kalshi data in parallel
            def enrich_with_kalshi(market):
                kalshi_data = match_kalshi(market, kalshi_markets)
                market["kalshi_signal"] = kalshi_data.get("kalshi_signal", "UNAVAILABLE")
                market["kalshi_yes_price"] = kalshi_data.get("kalshi_yes_price")
                market["kalshi_gap"] = kalshi_data.get("kalshi_gap")
                market["arb_flag"] = kalshi_data.get("arb_flag", False)
                market["arb_note"] = kalshi_data.get("arb_note")
                market["kalshi_title"] = kalshi_data.get("kalshi_title")
                market["kalshi_match_score"] = kalshi_data.get("match_score", 0)
                market["kalshi_matched_entities"] = kalshi_data.get("matched_entities", [])
                return market

            with ThreadPoolExecutor(max_workers=5) as executor:
                markets = list(executor.map(enrich_with_kalshi, markets))

            # Count matches and strong signals
            matched = sum(1 for m in markets if m.get("kalshi_signal") not in ["NO MATCH", "UNAVAILABLE"])
            strong = sum(1 for m in markets if m.get("arb_flag"))
            print(f"  [OK] Kalshi matching — {matched}/{len(markets)} matched, {strong} STRONG signals")
        else:
            print("  [WARN] Kalshi fetch failed — continuing without")
    except Exception as e:
        print(f"  [WARN] Kalshi enrichment error: {e} — continuing without")

    # Step 5: Fetch research for each market (parallel)
    print("\n[NEWS] Step 5: Gathering research for markets...")
    try:
        markets_with_research = fetch_research_for_markets(markets)
        print(f"[OK] Research gathered for {len(markets_with_research)} markets")
    except Exception as e:
        print(f"[WARN] Research fetch error: {e}")
        markets_with_research = markets

    # Step 6: Fetch cross-platform consensus (parallel)
    print("\n[WEB] Step 6: Fetching cross-platform consensus...")
    try:
        markets_with_consensus = fetch_consensus_for_markets(markets_with_research)
        print("[OK] Cross-platform data gathered")
    except Exception as e:
        print(f"[WARN] Consensus fetch error: {e}")
        markets_with_consensus = markets_with_research

    # Step 7: Fetch whale activity (parallel)
    print("\n[WHALE] Step 7: Tracking whale activity...")
    try:
        markets_with_whales = fetch_whale_activity_for_markets(markets_with_consensus)
        print("[OK] Whale activity tracked")
    except Exception as e:
        print(f"[WARN] Whale tracking error: {e}")
        markets_with_whales = markets_with_consensus

    # Step 7.5: Check for whale/insider alerts (independent of panel voting)
    print("\n[WHALE ALERT] Step 7.5: Checking for whale/insider activity...")
    try:
        alerts_result = check_whale_insider_for_markets(markets_with_whales)
        profile_alerts = alerts_result.get("profile_alerts", [])
        follow_alerts = alerts_result.get("follow_alerts", [])

        profile_alerts_sent = 0
        follow_alerts_sent = 0

        # Send PROFILE ALERTS (insider detected - regardless of market status)
        print(f"\n  [PROFILE ALERTS] Processing {len(profile_alerts)} insider profile alerts...")
        for alert_info in profile_alerts:
            market = alert_info["market"]
            alert = alert_info["alert"]
            alert_type = alert.get("alert_type", "INSIDER_PROFILE")
            wallet = alert.get("wallet", "unknown")
            market_id = market.get("conditionId", "")
            amount = alert.get("amount", 0)

            # Create whale_data dict for Discord embed
            whale_data = {
                "wallet": wallet,
                "amount": amount,
                "direction": alert.get("direction", "UNKNOWN"),
                "timestamp": alert.get("timestamp", ""),
                "insider_score": alert.get("insider_score", 0),
                "pattern_indicators": alert.get("patterns", []),
                "concentration": alert.get("concentration", 0),
                "is_fresh_wallet": alert.get("is_fresh_wallet", False),
                "first_transaction": alert.get("first_transaction")
            }

            # Determine Discord alert type based on score
            insider_score = alert.get("insider_score", 0)
            if insider_score >= 70:
                discord_alert_type = "HIGH_PROBABILITY_INSIDER"
            elif insider_score >= 40:
                discord_alert_type = "SUSPECTED_INSIDER"
            else:
                discord_alert_type = "INSIDER"

            # Check if we already sent this alert
            if not has_whale_alert_been_sent(market_id, wallet, f"PROFILE_{discord_alert_type}"):
                result = send_whale_alert_embed(market, whale_data, discord_alert_type)
                if result:
                    save_whale_alert_sent(market_id, wallet, f"PROFILE_{discord_alert_type}", amount)
                    profile_alerts_sent += 1
                    print(f"    [PROFILE] {discord_alert_type}: {wallet[:12]}... on '{smart_truncate(market.get('title', 'Unknown'), 60)}...' - Score: {insider_score}")
            else:
                print(f"    [SKIP] Duplicate profile alert for {wallet[:10]}...")

        # Send FOLLOW ALERTS (only for active markets with score >= 70)
        print(f"\n  [FOLLOW ALERTS] Processing {len(follow_alerts)} insider follow recommendations...")
        for alert_info in follow_alerts:
            market = alert_info["market"]
            alert = alert_info["alert"]
            wallet = alert.get("wallet", "unknown")
            market_id = market.get("conditionId", "")
            amount = alert.get("amount", 0)
            direction = alert.get("direction", "UNKNOWN")
            insider_score = alert.get("insider_score", 0)
            market_price = market.get("market_probability", 0.5) * 100

            # Create whale_data dict for Discord embed
            whale_data = {
                "wallet": wallet,
                "amount": amount,
                "direction": direction,
                "timestamp": alert.get("timestamp", ""),
                "insider_score": insider_score,
                "pattern_indicators": alert.get("patterns", []),
                "is_fresh_wallet": alert.get("is_fresh_wallet", False)
            }

            # Check if we already sent this follow alert
            if not has_whale_alert_been_sent(market_id, wallet, "FOLLOW_INSIDER"):
                # Create a special embed for follow alerts
                from alerts.discord_webhook import send_discord_notification

                event_slug = market.get("event_slug", "")
                market_slug = market.get("slug", "")
                if event_slug and market_slug:
                    market_url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
                else:
                    market_url = f"https://polymarket.com/market/{market_slug}"

                wallet_short = wallet[:10] + "..." + wallet[-4:] if len(wallet) > 14 else wallet
                profile_url = f"https://polymarket.com/profile/{wallet}" if wallet.startswith("0x") and len(wallet) == 42 else None
                wallet_field = f"[`{wallet_short}`]({profile_url})" if profile_url else f"`{wallet_short}`"

                embed = {
                    "title": "🎯 FOLLOW INSIDER BET",
                    "description": f"Active market with confirmed insider activity (Score: {insider_score}/100)",
                    "url": market_url,
                    "color": 0x00FF00,  # Green for follow recommendation
                    "fields": [
                        {"name": "Market", "value": smart_truncate(market.get("title", "Unknown"), 100), "inline": False},
                        {"name": "Insider Wallet", "value": wallet_field, "inline": True},
                        {"name": "Insider Bet", "value": f"{direction} ${amount:,.0f}", "inline": True},
                        {"name": "Market Price", "value": f"{market_price:.1f}%", "inline": True},
                        {"name": "Recommendation", "value": f"**Bet {direction}** - Follow the insider", "inline": False},
                        {"name": "Insider Score", "value": f"{insider_score}/100", "inline": True},
                        {"name": "Patterns", "value": smart_truncate(", ".join(alert.get("patterns", [])), 100), "inline": True},
                        {"name": "Time", "value": format_est_time(), "inline": True}
                    ],
                    "footer": {"text": "Polymarket Bot - Insider Follow Signal"},
                    "timestamp": alert.get("timestamp", "")
                }

                result = send_discord_notification([embed])
                if result:
                    save_whale_alert_sent(market_id, wallet, "FOLLOW_INSIDER", amount)
                    follow_alerts_sent += 1
                    print(f"    [FOLLOW] Bet {direction}: '{smart_truncate(market.get('title', 'Unknown'), 60)}...' at {market_price:.1f}%")
            else:
                print(f"    [SKIP] Duplicate follow alert for {wallet[:10]}...")

        if profile_alerts_sent > 0 or follow_alerts_sent > 0:
            print(f"\n[OK] Sent {profile_alerts_sent} profile alerts and {follow_alerts_sent} follow alerts")
        else:
            print("[i] No new whale/insider activity detected")
    except Exception as e:
        print(f"[WARN] Whale alert error: {e}")
        import traceback
        traceback.print_exc()

    # Step 8: Run Gemini cross-market synthesis
    print("\n[SYN] Step 8: Running cross-market synthesis...")
    try:
        markets_with_synthesis = synthesize_cross_market_insights(markets_with_whales)
        print("[OK] Cross-market synthesis complete")
    except Exception as e:
        print(f"[WARN] Synthesis error: {e}")
        markets_with_synthesis = markets_with_whales

    # Step 9: Run 4-agent panel voting (parallel)
    print("\n[VOTE] Step 9: Running 4-agent panel voting...")
    try:
        panel_results = run_panel_voting(markets_with_synthesis)
        print(f"[OK] Panel voting complete for {len(panel_results)} markets")
    except Exception as e:
        print(f"[X] Panel voting error: {e}")
        send_error_embed("Panel Voting Error", str(e))
        return 0

    # Step 10: Load multipliers and recently recommended
    print("\n[JUDGE] Step 10: Judge evaluating panel votes...")
    multipliers = load_multipliers()
    recently_recommended = load_recently_recommended()
    print(f"[i] Excluding {len(recently_recommended)} recently recommended markets")

    # Step 11: Get top low risk and high risk bets
    try:
        top_bets = get_top_bets(panel_results, multipliers, recently_recommended,
                                low_risk_count=MAX_LOW_RISK_BETS,
                                high_risk_count=MAX_HIGH_RISK_BETS)

        if not top_bets:
            print("[BLOCK] Judge decided: NO BET this cycle")
            send_error_embed(
                "No Bet This Cycle",
                "Judge determined no markets have sufficient edge/confidence"
            )
            save_lesson({
                "timestamp": datetime.now().isoformat(),
                "type": "no_bet",
                "reason": "Judge decided no markets have sufficient edge/confidence",
                "markets_considered": len(markets)
            })
            return 0

        print(f"[OK] Judge selected {len(top_bets)} bets")
    except Exception as e:
        print(f"[X] Judge decision error: {e}")
        send_error_embed("Judge Decision Error", str(e))
        return 0

    # Step 12: Calculate Kelly stake for each bet
    print("\n[12] Step 12: Calculating Kelly stakes...")
    final_bets = []
    for bet in top_bets:
        try:
            stake_info = calculate_stake(
                bet.get("market_id", ""),
                bet.get("direction", ""),
                bet.get("our_probability", 0.5),
                bet.get("market_probability", 0.5),
                bet.get("confidence", "medium"),
                bet.get("panel_agreement", "weak"),
                bet.get("whale_signal", "UNKNOWN"),
                bet.get("cross_platform_signal", "WEAK"),
                bet.get("category", "other")
            )
            bet["stake_usd"] = stake_info.get("stake_usd", MIN_STAKE_USD)
            bet["kelly_fraction"] = stake_info.get("kelly_fraction", 0.1)
            bet["timestamp"] = datetime.now().isoformat()
            bet["resolved"] = False
            bet["outcome"] = None
            bet["profit_loss"] = None
            final_bets.append(bet)
            print(f"  [OK] Bet: {bet['direction']} {smart_truncate(bet['market_title'], 60)}... Stake: ${bet['stake_usd']:.2f}")
        except Exception as e:
            print(f"  [WARN] Kelly calculation error for bet: {e}")
            bet["stake_usd"] = MIN_STAKE_USD
            bet["kelly_fraction"] = 0.1
            bet["timestamp"] = datetime.now().isoformat()
            bet["resolved"] = False
            bet["outcome"] = None
            bet["profit_loss"] = None
            final_bets.append(bet)

    # Step 13: Save predictions to memory
    print("\n[SAVE] Step 13: Saving predictions to memory...")
    for bet in final_bets:
        save_prediction(bet)

    # Track these markets as recently recommended
    add_recently_recommended([b["market_id"] for b in final_bets])
    print(f"[OK] {len(final_bets)} predictions saved")

    # Step 14: Send Discord notification
    print("\n[SEND] Step 14: Sending Discord notification...")
    try:
        agent_scores = load_agent_scores()
        multipliers = load_multipliers()
        send_batch_bet_embeds(final_bets, agent_scores, multipliers)
        print("[OK] Discord notification sent")
    except Exception as e:
        print(f"[WARN] Discord send error: {e}")

    # Calculate runtime
    elapsed = time.time() - start_time
    minutes, seconds = divmod(int(elapsed), 60)

    print("\n" + "=" * 60)
    print(f"[DONE] CYCLE COMPLETE in {minutes}m {seconds}s")
    print("=" * 60)
    # Separate bets by risk level
    low_risk = [b for b in final_bets if b.get("risk_level") == "LOW"]
    high_risk = [b for b in final_bets if b.get("risk_level") == "HIGH"]

    print(f"\n[SUMMARY] Placed {len(final_bets)} bets this cycle:")

    if low_risk:
        print(f"\n  📗 LOW RISK BETS ({len(low_risk)}):")
        for i, bet in enumerate(low_risk, 1):
            print(f"    {i}. {bet['direction']} '{smart_truncate(bet['market_title'], 60)}...' - ${bet['stake_usd']:.2f} (edge: {bet['edge']:.1f}%, conf: {bet['confidence']})")

    if high_risk:
        print(f"\n  📕 HIGH RISK BETS ({len(high_risk)}):")
        for i, bet in enumerate(high_risk, 1):
            print(f"    {i}. {bet['direction']} '{smart_truncate(bet['market_title'], 60)}...' - ${bet['stake_usd']:.2f} (edge: {bet['edge']:.1f}%, conf: {bet['confidence']})")

    # Save cycle summary
    summary = {
        "timestamp": cycle_timestamp,
        "runtime_seconds": elapsed,
        "markets_considered": len(markets),
        "bets_placed": len(final_bets),
        "bets": [
            {
                "market_id": b["market_id"],
                "direction": b["direction"],
                "stake_usd": b["stake_usd"],
                "edge": b["edge"]
            }
            for b in final_bets
        ]
    }

    os.makedirs("memory", exist_ok=True)
    with open("memory/last_session.json", "w") as f:
        json.dump(summary, f, indent=2)

    return len(final_bets)


def main():
    """Main entry point - runs infinite loop with 1-hour delays."""
    print("=" * 60)
    print(">>> POLYMARKET PREDICTION BOT - CONTINUOUS MODE")
    print(">>> Press Ctrl+C to stop gracefully")
    print("=" * 60)

    cycle_count = 0

    while not shutdown_requested:
        try:
            bets_placed = run_cycle()
            cycle_count += 1

            if shutdown_requested:
                print("\n[SHUTDOWN] Shutting down gracefully...")
                break

            # Sleep for configured interval
            print(f"\n[SLEEP] Cycle {cycle_count} complete. Sleeping for {CYCLE_INTERVAL_SECONDS // 60} minutes...")
            next_time = datetime.now() + timedelta(seconds=CYCLE_INTERVAL_SECONDS)
            print(f"[SLEEP] Next cycle at {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Sleep in chunks to allow for responsive shutdown (10-second chunks)
            for _ in range(CYCLE_INTERVAL_SECONDS // 10):
                if shutdown_requested:
                    break
                time.sleep(10)  # Sleep 10 seconds at a time

        except Exception as e:
            print(f"\n[X] Cycle failed with error: {e}")
            send_error_embed("Cycle Error", f"Cycle {cycle_count + 1} failed: {str(e)[:500]}")

            if not shutdown_requested:
                print(f"[RETRY] Waiting {RETRY_DELAY_SECONDS // 60} minutes before retry...")
                time.sleep(RETRY_DELAY_SECONDS)  # Wait on error

    print(f"\n{'=' * 60}")
    print(f">>> BOT STOPPED - Completed {cycle_count} cycles")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
