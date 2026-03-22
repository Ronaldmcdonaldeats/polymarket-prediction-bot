#!/usr/bin/env python3
"""
Discord Webhook Module
Sends rich embeds to Discord with bet recommendations and stats.
"""

import os
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import requests
from dotenv import load_dotenv

from utils.memory_system import load_predictions, load_agent_scores, load_multipliers
from alerts.whale_tracker import enrich_wallet

load_dotenv()

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

from utils.conversions import smart_truncate


def create_bet_embed(market: Dict[str, Any], judge_decision: Dict[str, Any],
                     kelly_stake: Dict[str, Any], stake_usd: float) -> Dict[str, Any]:
    """
    Create Discord embed for bet recommendation.

    Args:
        market: Market data
        judge_decision: Judge decision
        kelly_stake: Kelly stake calculation
        stake_usd: Final stake amount

    Returns:
        Discord embed dict
    """
    decision = judge_decision.get("decision", "SKIP")
    color = 0x00FF00 if decision == "YES" else 0xFF0000 if decision == "NO" else 0x808080

    # Build sentiment label
    whale = market.get("whale_signal", "UNKNOWN")
    cross = market.get("cross_platform_signal", "WEAK")
    sentiment_parts = []
    if whale != "UNKNOWN":
        sentiment_parts.append(f"Whale: {whale}")
    if cross != "WEAK":
        sentiment_parts.append(f"Cross-platform: {cross}")
    sentiment_label = " | ".join(sentiment_parts) if sentiment_parts else "No signals"

    fields = [
        {"name": "Direction", "value": decision, "inline": True},
        {"name": "Stake", "value": f"${stake_usd:.2f}", "inline": True},
        {"name": "Market Price", "value": f"{market.get('yes_price', 50):.1f}%", "inline": True},
        {"name": "Our Estimate", "value": f"{judge_decision.get('estimated_probability', 50):.1f}%", "inline": True},
        {"name": "Edge", "value": f"{judge_decision.get('edge_percent', 0):.1f}%", "inline": True},
        {"name": "Confidence", "value": judge_decision.get("final_confidence", "low"), "inline": True},
        {"name": "Signals", "value": sentiment_label, "inline": True},
        {"name": "Why", "value": smart_truncate(judge_decision.get("one_sentence_summary", "No summary"), 200), "inline": False}
    ]

    return {
        "title": smart_truncate(market.get("title", "Unknown Market"), 250),
        "url": market.get("url", "https://polymarket.com"),
        "color": color,
        "fields": fields,
        "footer": {"text": "Polymarket Bot - 4-agent panel - Kelly Criterion"},
        "timestamp": judge_decision.get("timestamp", "")
    }


def create_stats_embed() -> Dict[str, Any]:
    """
    Create Discord embed for stats summary.

    Returns:
        Discord embed dict or None if not enough data
    """
    predictions = load_predictions()
    agent_scores = load_agent_scores()
    multipliers = load_multipliers()

    resolved = [p for p in predictions if p.get("resolved") and p.get("outcome")]
    total_resolved = len(resolved)

    if total_resolved < 10:
        return None

    wins = sum(1 for p in resolved if p["outcome"] == "WIN")
    losses = total_resolved - wins
    accuracy = (wins / total_resolved) * 100 if total_resolved > 0 else 0

    # Find best agent
    best_agent = ""
    best_rate = 0
    for agent, scores in agent_scores.items():
        total = scores.get("wins", 0) + scores.get("losses", 0)
        if total >= 3:  # Need at least 3 predictions
            rate = (scores.get("wins", 0) / total) * 100
            if rate > best_rate:
                best_rate = rate
                best_agent = agent

    # Calculate P&L (simplified - assumes $50 average stake)
    avg_stake = sum(p.get("stake", 50) for p in resolved) / len(resolved) if resolved else 50
    pnl = sum(avg_stake if p["outcome"] == "WIN" else -avg_stake for p in resolved)
    pnl_pct = (pnl / (avg_stake * total_resolved)) * 100 if total_resolved > 0 else 0

    # Current bankroll
    bankroll = multipliers.get("kelly", {}).get("bankroll", 500)

    # Skipped bets
    pending = [p for p in predictions if not p.get("resolved")]
    skipped = len([p for p in pending if p.get("decision") == "SKIP"])

    fields = [
        {"name": "Accuracy", "value": f"{accuracy:.1f}% ({wins}W/{losses}L)", "inline": True},
        {"name": "Best Agent", "value": f"{best_agent} ({best_rate:.0f}%)", "inline": True},
        {"name": "Sim P&L", "value": f"+${pnl:.0f} ({pnl_pct:+.1f}%)", "inline": True},
        {"name": "Bankroll", "value": f"${bankroll:.0f}", "inline": True},
        {"name": "Resolved", "value": str(total_resolved), "inline": True},
        {"name": "Skipped", "value": str(skipped), "inline": True}
    ]

    return {
        "title": "Bot Performance Stats",
        "color": 0x5865F2,
        "fields": fields,
        "footer": {"text": "Paper trading only - No real money placed"}
    }


def send_discord_notification(embeds: List[Dict[str, Any]]) -> bool:
    """
    Send embed(s) to Discord webhook.

    Args:
        embeds: List of Discord embed dicts

    Returns:
        True if sent successfully
    """
    if not WEBHOOK_URL or not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        print("  [X] Discord webhook not configured")
        return False

    if not isinstance(embeds, list):
        embeds = [embeds]
    if len(embeds) > 10:
        embeds = embeds[:10]  # Discord limit

    payload = {"embeds": embeds}

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 204:
            print("  [OK] Discord webhook sent")
            return True
        else:
            print(f"  [X] Discord failed: {response.status_code} {response.text[:100]}")
            return False

    except Exception as e:
        print(f"  [X] Discord error: {str(e)[:100]}")
        return False


def send_bet_notification(market: Dict[str, Any], judge_decision: Dict[str, Any],
                          kelly_stake: Dict[str, Any], stake_usd: float) -> bool:
    """
    Send complete bet notification to Discord.

    Args:
        market: Market data
        judge_decision: Judge decision
        kelly_stake: Kelly stake calculation
        stake_usd: Final stake amount

    Returns:
        True if sent successfully
    """
    bet_embed = create_bet_embed(market, judge_decision, kelly_stake, stake_usd)
    stats_embed = create_stats_embed()

    return send_discord_notification([bet_embed, stats_embed] if stats_embed else [bet_embed])


def send_bet_embed(bet: Dict[str, Any], agent_scores: Dict[str, Any] = None,
                   multipliers: Dict[str, Any] = None) -> bool:
    """
    Send bet embed to Discord (wrapper for main.py compatibility).

    Args:
        bet: Bet dict with market info, stake, probabilities
        agent_scores: Optional agent scores dict
        multipliers: Optional multipliers dict

    Returns:
        True if sent successfully
    """
    # Convert bet format to market/judge/kelly format
    # Build correct Polymarket URL with event_slug and market_slug
    event_slug = bet.get("event_slug", "")
    market_slug = bet.get("market_slug", "")
    if event_slug and market_slug:
        market_url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
    else:
        market_url = f"https://polymarket.com/market/{market_slug}"

    market = {
        "title": bet.get("market_title", "Unknown Market"),
        "slug": market_slug,
        "url": market_url,
        "yes_price": bet.get("market_probability", 0.5) * 100,  # Fixed: use market_probability (decimal)
        "whale_signal": bet.get("whale_signal", "UNKNOWN"),
        "cross_platform_signal": bet.get("consensus", {}).get("signal", "WEAK") if isinstance(bet.get("consensus"), dict) else "WEAK"
    }

    judge_decision = {
        "decision": bet.get("direction", "SKIP"),
        "final_confidence": bet.get("confidence", "low"),
        "estimated_probability": bet.get("our_probability", 0.5) * 100,
        "edge_percent": bet.get("edge", 0) * 100,
        "one_sentence_summary": smart_truncate(bet.get("reasoning", ""), 200),
        "timestamp": bet.get("timestamp", "")
    }

    kelly_stake = {
        "stake": bet.get("stake_usd", 10),
        "edge_percent": bet.get("edge", 0) * 100
    }

    stake_usd = bet.get("stake_usd", 10)

    return send_bet_notification(market, judge_decision, kelly_stake, stake_usd)


def send_error_embed(title: str, description: str) -> bool:
    """
    Send error embed to Discord.

    Args:
        title: Error title
        description: Error description

    Returns:
        True if sent successfully
    """
    if not WEBHOOK_URL or not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        print(f"  Discord webhook not configured - Error: {title}")
        return False

    # Get current time in EST (UTC-5)
    est_tz = timezone(timedelta(hours=-5))
    est_now = datetime.now(est_tz)

    embed = {
        "title": title[:256],
        "description": description[:4096],
        "color": 0xFF0000,  # Red color for errors
        "footer": {"text": "Polymarket Bot - Error"},
        "timestamp": est_now.isoformat()
    }

    payload = {"embeds": [embed]}

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 204:
            print("  Error notification sent to Discord")
            return True
        else:
            print(f"  Discord error send failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"  Discord error send failed: {str(e)[:100]}")
        return False


def send_batch_bet_embeds(bets: List[Dict[str, Any]], agent_scores: Dict[str, Any] = None,
                         multipliers: Dict[str, Any] = None) -> bool:
    """
    Send multiple bet embeds to Discord in a single batch.

    Args:
        bets: List of bet dicts
        agent_scores: Optional agent scores dict
        multipliers: Optional multipliers dict

    Returns:
        True if sent successfully
    """
    if not bets:
        print("  No bets to send")
        return False

    embeds = []

    # Header embed with EST timestamp
    est_tz = timezone(timedelta(hours=-5))
    est_now = datetime.now(est_tz)
    header_embed = {
        "title": f"🎯 Top {len(bets)} Bet Recommendations",
        "description": f"Found {len(bets)} high-confidence opportunities this cycle",
        "color": 0x5865F2,
        "timestamp": est_now.isoformat()
    }
    embeds.append(header_embed)

    # Bet embeds (max 9 more to stay under Discord's 10 embed limit)
    for bet in bets[:9]:
        event_slug = bet.get("event_slug", "")
        market_slug = bet.get("market_slug", "")
        if event_slug and market_slug:
            market_url = f"https://polymarket.com/event/{event_slug}/{market_slug}"
        else:
            market_url = f"https://polymarket.com/market/{market_slug}"

        direction = bet.get("direction", "SKIP")
        color = 0x00FF00 if direction == "YES" else 0xFF0000 if direction == "NO" else 0x808080

        # Get reasoning and truncate cleanly
        reasoning = bet.get("reasoning", "No reasoning provided")
        reasoning = smart_truncate(reasoning, 250)

        # Get risk level
        risk = bet.get("risk_level", "UNKNOWN")
        risk_emoji = "🟢" if risk == "LOW" else "🔴" if risk == "HIGH" else "⚪"

        # Get Kalshi data
        kalshi_signal = bet.get("kalshi_signal", "UNAVAILABLE")
        kalshi_gap = bet.get("kalshi_gap")
        arb_flag = bet.get("arb_flag", False)

        # Set color to gold if arbitrage flag
        if arb_flag:
            color = 0xFFD700  # Gold

        # Build fields
        fields = [
            {"name": "Direction", "value": direction, "inline": True},
            {"name": "Risk Level", "value": f"{risk_emoji} {risk}", "inline": True},
            {"name": "Stake", "value": f"${bet.get('stake_usd', 10):.2f}", "inline": True},
            {"name": "Edge", "value": f"{bet.get('edge', 0):.1f}%", "inline": True},
            {"name": "Confidence", "value": bet.get("confidence", "low"), "inline": True},
            {"name": "Our Prob", "value": f"{bet.get('our_probability', 0.5):.1%}", "inline": True},
            {"name": "Market", "value": f"{bet.get('market_probability', 0.5):.1%}", "inline": True},  # Fixed: use market_probability
        ]

        # Add Kalshi field if available
        if kalshi_signal not in ["UNAVAILABLE", "NO MATCH"]:
            kalshi_price = bet.get("kalshi_yes_price")
            if kalshi_price is not None:
                kalshi_text = f"Kalshi: {kalshi_price}%"
                if kalshi_gap is not None:
                    kalshi_text += f" (gap: {kalshi_gap}%)"
                fields.append({"name": "Kalshi Signal", "value": kalshi_text, "inline": True})

        # Add arbitrage alert if flagged
        if arb_flag:
            arb_note = bet.get("arb_note", "")
            fields.append({"name": "⚡ ARBITRAGE ALERT", "value": smart_truncate(arb_note, 200) if arb_note else "Large gap detected vs Kalshi", "inline": False})

        fields.append({"name": "Why", "value": reasoning, "inline": False})

        embed = {
            "title": smart_truncate(bet.get("market_title", "Unknown Market"), 250),
            "url": market_url,
            "color": color,
            "fields": fields
        }
        embeds.append(embed)

    return send_discord_notification(embeds)


def send_whale_alert_embed(market: Dict[str, Any], whale_data: Dict[str, Any], alert_type: str) -> bool:
    """
    Send a whale or insider activity alert to Discord.

    Args:
        market: Market data dict with title, slug, event_slug
        whale_data: Whale/insider data with wallet, amount, direction, timestamp,
                    insider_score, wallet_age_hours, pattern_indicators
        alert_type: "WHALE", "INSIDER", "SUSPECTED_INSIDER", or "HIGH_PROBABILITY_INSIDER"

    Returns:
        True if sent successfully
    """
    if not WEBHOOK_URL or not WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        print(f"  Discord webhook not configured - skipping {alert_type} alert")
        return False

    # Build market URL - use direct market link (more reliable)
    market_slug = market.get("slug", "")
    if market_slug:
        market_url = f"https://polymarket.com/market/{market_slug}"
    else:
        # Fallback to event link if no slug
        event_slug = market.get("event_slug", "")
        if event_slug:
            market_url = f"https://polymarket.com/event/{event_slug}"
        else:
            market_url = "https://polymarket.com"

    # Build profile link (if wallet address is valid Ethereum address)
    wallet = whale_data.get("wallet", "unknown")
    profile_url = None
    if wallet and wallet.startswith("0x") and len(wallet) == 42:
        profile_url = f"https://polymarket.com/profile/{wallet}"

    # Determine main URL based on alert type
    # For ALL alert types, link to MARKET (not profile)
    main_url = market_url

    # Set color, emoji, and title based on alert type
    if alert_type == "WHALE":
        color = 0x3498db  # Blue for whale
        emoji = "🐋"
        title = f"{emoji} WHALE ALERT"
    elif alert_type == "INSIDER":
        color = 0x9b59b6  # Purple for insider
        emoji = "🚨"
        title = f"{emoji} INSIDER ACTIVITY DETECTED"
    elif alert_type == "SUSPECTED_INSIDER":
        color = 0xFF0000  # Red for suspected insider
        emoji = "⚠️"
        title = f"{emoji} SUSPECTED INSIDER ACTIVITY"
    elif alert_type == "HIGH_PROBABILITY_INSIDER":
        color = 0xFF0000  # Red for high probability insider
        emoji = "🚨"
        title = f"{emoji} HIGH PROBABILITY INSIDER DETECTED"
    else:
        # Fallback for unknown alert types
        color = 0x808080  # Gray
        emoji = "❓"
        title = f"{emoji} UNKNOWN ALERT TYPE"

    # Format amount
    amount = whale_data.get("amount", 0)
    amount_str = f"${amount:,.0f}"

    # Get direction
    direction = whale_data.get("direction", "UNKNOWN")
    if direction == "BUY":
        direction_str = "YES"
    elif direction == "SELL":
        direction_str = "NO"
    else:
        direction_str = direction

    # Get timestamp and convert to EST (UTC-5)
    timestamp = whale_data.get("timestamp", "")
    time_str = "Just now"
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            # Convert to EST (UTC-5)
            est_tz = timezone(timedelta(hours=-5))
            dt_est = dt.astimezone(est_tz)
            time_str = dt_est.strftime("%Y-%m-%d %H:%M EST")
        except:
            time_str = str(timestamp)

    # Build wallet field - show profile link only if wallet has a name (not anonymous)
    wallet_name = whale_data.get("wallet_name")
    if wallet_name and profile_url:
        # Show clickable wallet address with profile link
        wallet_field = f"[`{wallet}`]({profile_url})"
    else:
        # No profile available, just show truncated address
        wallet_short = wallet[:10] + "..." + wallet[-4:] if len(wallet) > 14 else wallet
        wallet_field = f"`{wallet_short}`"

    # Build fields
    fields = [
        {"name": "Market", "value": smart_truncate(market.get("title", "Unknown Market"), 200), "inline": False},
        {"name": "Wallet", "value": wallet_field, "inline": True},
        {"name": "Amount", "value": amount_str, "inline": True},
        {"name": "Direction", "value": direction_str, "inline": True},
        {"name": "Time", "value": time_str, "inline": True},
    ]

    # Add insider_score field if present
    insider_score = whale_data.get("insider_score")
    if insider_score is not None:
        fields.append({"name": "Insider Score", "value": f"{insider_score:.2f}", "inline": True})

    # Add wallet age field if available
    wallet_age_hours = whale_data.get("wallet_age_hours")
    if wallet_age_hours is not None:
        if wallet_age_hours < 24:
            wallet_age_str = "🆕 Fresh (< 24h)"
        else:
            days = int(wallet_age_hours // 24)
            remaining_hours = int(wallet_age_hours % 24)
            if days > 0:
                wallet_age_str = f"{days}d {remaining_hours}h"
            else:
                wallet_age_str = f"{remaining_hours}h"
        fields.append({"name": "Wallet Age", "value": wallet_age_str, "inline": True})

    # Add enriched wallet stats if available
    realized_pnl = whale_data.get("realized_pnl")
    if realized_pnl is not None and realized_pnl != 0:
        pnl_str = f"${realized_pnl:,.2f}"
        fields.append({"name": "Realized P&L", "value": pnl_str, "inline": True})

    win_rate = whale_data.get("win_rate")
    if win_rate is not None and win_rate > 0:
        wr_str = f"{win_rate*100:.0f}%"
        fields.append({"name": "Win Rate", "value": wr_str, "inline": True})

    total_positions = whale_data.get("total_positions")
    if total_positions and total_positions > 0:
        pos_str = f"{total_positions} total"
        open_pos = whale_data.get("open_positions")
        if open_pos and open_pos > 0:
            pos_str += f" ({open_pos} open)"
        fields.append({"name": "Positions", "value": pos_str, "inline": True})

    total_trades = whale_data.get("total_trades")
    if total_trades and total_trades > 0:
        fields.append({"name": "Total Trades", "value": str(total_trades), "inline": True})

    # Add wallet name if available (separate from wallet address field)
    wallet_name = whale_data.get("wallet_name")
    if wallet_name:
        fields.append({"name": "Trader Name", "value": wallet_name, "inline": True})

    # Add pattern indicators field if available
    pattern_indicators = whale_data.get("pattern_indicators", [])
    if pattern_indicators:
        if isinstance(pattern_indicators, list):
            # Convert underscores to spaces and title case each pattern
            formatted_patterns = []
            for pattern in pattern_indicators:
                formatted = pattern.replace('_', ' ').title()
                formatted_patterns.append(formatted)
            indicators_str = ", ".join(formatted_patterns)
        else:
            indicators_str = str(pattern_indicators).replace('_', ' ').title()
        fields.append({"name": "Pattern Indicators", "value": indicators_str[:200], "inline": False})

    # Add concentration info for insider alerts (legacy support)
    if alert_type in ["INSIDER", "SUSPECTED_INSIDER", "HIGH_PROBABILITY_INSIDER"]:
        concentration = whale_data.get("concentration")
        order_count = whale_data.get("order_count")
        gov_level = whale_data.get("government_level", "")
        if concentration:
            fields.append({"name": "Concentration", "value": str(concentration), "inline": True})
        if order_count:
            fields.append({"name": "Orders", "value": str(order_count), "inline": True})
        if gov_level:
            fields.append({"name": "Government Level", "value": gov_level, "inline": True})

    # Add reason/description
    reason = whale_data.get("reason", "")
    if reason:
        fields.append({"name": "Detection Reason", "value": reason[:200], "inline": False})

    # Build embed with EST timestamp
    est_tz = timezone(timedelta(hours=-5))
    est_now = datetime.now(est_tz)
    embed = {
        "title": title,
        "url": main_url,  # Links to PROFILE for insider alerts, market for whale
        "color": color,
        "fields": fields,
        "footer": {"text": "Polymarket Bot - Whale/Insider Detection"},
        "timestamp": est_now.isoformat()
    }

    # Send the alert
    try:
        payload = {"embeds": [embed]}
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 204:
            print(f"  [OK] {alert_type} alert sent to Discord")
            return True
        else:
            print(f"  [X] {alert_type} alert failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"  [X] {alert_type} alert error: {str(e)[:100]}")
        return False


if __name__ == "__main__":
    # Test the module
    print("Testing Discord Webhook...")

    test_market = {
        "title": "Test Market for Discord",
        "url": "https://polymarket.com/event/test",
        "yes_price": 45.0,
        "whale_signal": "YES",
        "cross_platform_signal": "MODERATE"
    }

    test_decision = {
        "decision": "YES",
        "final_confidence": "high",
        "estimated_probability": 65.0,
        "edge_percent": 20.0,
        "one_sentence_summary": "Strong contrarian opportunity with whale support"
    }

    test_kelly = {
        "stake": 45.50,
        "edge_percent": 20.0
    }

    # This will only work if WEBHOOK_URL is set
    if WEBHOOK_URL:
        result = send_bet_notification(test_market, test_decision, test_kelly, 45.50)
        print(f"Notification sent: {result}")
    else:
        print("WEBHOOK_URL not set - skipping actual send")
        embed = create_bet_embed(test_market, test_decision, test_kelly, 45.50)
        print(f"Embed created: {embed['title']}")
