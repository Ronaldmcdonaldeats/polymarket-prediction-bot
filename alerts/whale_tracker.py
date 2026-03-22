#!/usr/bin/env python3
"""
Whale Tracker Module
Tracks large orders and whale positions on Polymarket
"""

import requests
from typing import Dict, List, Any, Optional

from utils.config import (
    WHALE_MIN_ORDER_SIZE,
    WHALE_WALLET_AGE_FRESH_HOURS,
    WHALE_WALLET_AGE_NEW_HOURS,
    WHALE_WIN_RATE_HIGH,
    WHALE_WIN_RATE_GOOD,
    WHALE_POSITION_CONCENTRATION_MAX,
    WHALE_CONCENTRATED_BET_VOLUME,
    WHALE_MIN_TRADES_FOR_VOLUME,
    WHALE_LARGE_BET_AVG_SIZE,
    WHALE_LARGE_BET_TOTAL_VOLUME,
    WHALE_KNOWN_INSIDER_BONUS,
    WHALE_INSIDER_SCORE_FILTER,
    WHALE_BULLISH_RATIO,
    WHALE_BEARISH_RATIO,
    WHALE_NEW_WALLET_VOLUME,
    INSIDER_STRONG_THRESHOLD,
    CONFIDENCE_PER_ORDER,
    CONFIDENCE_BONUS_LARGE_VOLUME,
    MAX_CONFIDENCE_SCORE,
    LARGE_VOLUME_THRESHOLD,
)


def enrich_wallet(proxy_wallet: str) -> dict:
    """Fetch real wallet data from Polymarket Data API."""
    base = "https://data-api.polymarket.com"
    headers = {"User-Agent": "Mozilla/5.0"}
    result = {
        "proxy_wallet":    proxy_wallet,
        "name":            None,
        "pseudonym":       None,
        "open_positions":  0,
        "total_positions": 0,
        "realized_pnl":    0.0,
        "win_rate":        0.0,
        "total_trades":    0,
        "profile_url":     f"https://polymarket.com/profile/{proxy_wallet}",
    }

    # ── 1. TRADES — count total and calculate PnL ──
    try:
        r = requests.get(
            f"{base}/trades",
            params={"user": proxy_wallet, "limit": 50},
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            trades = r.json()
            if isinstance(trades, list):
                result["total_trades"] = len(trades)

                # Build positions from trades to calc PnL
                positions = {}
                total_invested = 0.0
                total_returned = 0.0

                for trade in trades:
                    token_id = trade.get("asset") or trade.get("asset_id")
                    side = trade.get("side", "BUY")
                    size = float(trade.get("size", 0))
                    price = float(trade.get("price", 0))
                    cost = size * price

                    if token_id not in positions:
                        positions[token_id] = {
                            "quantity": 0, "cost_basis": 0
                        }

                    if side == "BUY":
                        positions[token_id]["quantity"] += size
                        positions[token_id]["cost_basis"] += cost
                        total_invested += cost
                    else:
                        positions[token_id]["quantity"] -= size
                        total_returned += cost

                result["total_positions"] = len(positions)
                open_pos = sum(
                    1 for p in positions.values()
                    if p["quantity"] > 0.1
                )
                result["open_positions"] = open_pos
    except Exception as e:
        print(f"  [WARN] trades fetch failed: {e}")

    # ── 2. ACTIVITY — get redemptions for real PnL ──
    try:
        r = requests.get(
            f"{base}/activity",
            params={"user": proxy_wallet, "limit": 50},
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            activity = r.json()
            if isinstance(activity, list):
                total_returned = 0.0
                total_invested = 0.0
                wins = 0
                losses = 0

                for event in activity:
                    event_type = event.get("type", "")
                    if event_type == "TRADE":
                        side = event.get("side", "BUY")
                        size = float(event.get("size", 0))
                        price = float(event.get("price", 0))
                        cost = size * price
                        if side == "BUY":
                            total_invested += cost
                        else:
                            total_returned += cost
                    elif event_type == "REDEEM":
                        val = float(
                            event.get("value", 0) or
                            event.get("amount", 0)
                        )
                        total_returned += val
                        if val > 0:
                            wins += 1
                        else:
                            losses += 1

                result["realized_pnl"] = round(
                    total_returned - total_invested, 2
                )
                total_resolved = wins + losses
                if total_resolved > 0:
                    result["win_rate"] = round(
                        wins / total_resolved, 3
                    )
    except Exception as e:
        print(f"  [WARN] activity fetch failed: {e}")

    # ── 3. PROFILE — try Gamma API first, fallback to trades data ──
    # Try Gamma API (may not be available)
    try:
        r = requests.get(
            f"https://gamma-api.polymarket.com/profiles/{proxy_wallet}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            profile = r.json()
            result["name"] = (
                profile.get("name") or
                profile.get("pseudonym") or
                profile.get("displayName")
            )
            result["pseudonym"] = profile.get("pseudonym")
    except Exception as e:
        print(f"  [WARN] profile fetch failed: {e}")

    # Fallback: extract from trades if name not found
    if not result["name"]:
        try:
            r = requests.get(
                f"https://data-api.polymarket.com/trades?user={proxy_wallet}&limit=1",
                headers=headers, timeout=10
            )
            if r.status_code == 200:
                trades = r.json()
                if trades and isinstance(trades, list) and len(trades) > 0:
                    trade = trades[0]
                    result["name"] = trade.get("name") or trade.get("pseudonym")
                    result["pseudonym"] = trade.get("pseudonym")
        except Exception as e:
            print(f"  [WARN] trades profile fallback failed: {e}")

    return result


def fetch_large_orders(market_id: str, min_size: float = WHALE_MIN_ORDER_SIZE) -> List[Dict[str, Any]]:
    """
    Fetch and filter large orders from Polymarket CLOB API.

    Args:
        market_id: The conditionId/tokenId of the market
        min_size: Minimum order size in USD to consider (default $5000)

    Returns:
        List of large orders
    """
    url = f"https://clob.polymarket.com/book?token_id={market_id}"

    large_orders = []

    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return large_orders

        data = response.json()

        # Check both bids and asks for large orders
        for side in ["bids", "asks"]:
            orders = data.get(side, [])
            for order in orders:
                try:
                    size = float(order.get("size", 0))
                    price = float(order.get("price", 0))
                    usd_value = size * price

                    if usd_value >= min_size:
                        large_orders.append({
                            "side": "BUY" if side == "bids" else "SELL",
                            "size": size,
                            "price": price,
                            "usd_value": usd_value,
                            "market_id": market_id
                        })
                except (ValueError, TypeError):
                    continue

        return large_orders

    except Exception:
        return []


def analyze_whale_position(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze whale positions from large orders.

    Determines if whales are:
    - BULLISH: More large buy orders than sell
    - BEARISH: More large sell orders than buy
    - NEUTRAL: Roughly equal or no clear signal

    Args:
        orders: List of large orders from fetch_large_orders

    Returns:
        Dict with position, confidence, and statistics
    """
    if not orders:
        return {
            "position": "UNKNOWN",
            "confidence": 0,
            "buy_value": 0,
            "sell_value": 0,
            "ratio": 0
        }

    buy_value = sum(o["usd_value"] for o in orders if o["side"] == "BUY")
    sell_value = sum(o["usd_value"] for o in orders if o["side"] == "SELL")

    total_value = buy_value + sell_value

    if total_value == 0:
        return {
            "position": "UNKNOWN",
            "confidence": 0,
            "buy_value": 0,
            "sell_value": 0,
            "ratio": 0
        }

    # Calculate ratio and determine position
    if buy_value > sell_value * WHALE_BULLISH_RATIO:
        position = "BULLISH"
        ratio = buy_value / sell_value if sell_value > 0 else 999
    elif sell_value > buy_value * WHALE_BEARISH_RATIO:
        position = "BEARISH"
        ratio = sell_value / buy_value if buy_value > 0 else 999
    else:
        position = "NEUTRAL"
        ratio = max(buy_value, sell_value) / min(buy_value, sell_value) if min(buy_value, sell_value) > 0 else 1

    # Confidence based on number of orders and total value
    confidence = min(len(orders) * CONFIDENCE_PER_ORDER, MAX_CONFIDENCE_SCORE)
    if total_value > LARGE_VOLUME_THRESHOLD:  # Bonus for very large volume
        confidence = min(confidence + CONFIDENCE_BONUS_LARGE_VOLUME, MAX_CONFIDENCE_SCORE)

    return {
        "position": position,
        "confidence": confidence,
        "buy_value": round(buy_value, 2),
        "sell_value": round(sell_value, 2),
        "ratio": round(ratio, 2),
        "total_orders": len(orders)
    }


def get_whale_signal(market_id: str) -> Dict[str, Any]:
    """
    Main function to get whale signal for a market.

    Combines fetching large orders and analyzing positions.

    Args:
        market_id: The conditionId/tokenId of the market

    Returns:
        Dict with signal, position, confidence, and raw data
    """
    # Fetch large orders with default $5000 minimum
    orders = fetch_large_orders(market_id, min_size=5000)

    # Analyze the orders
    analysis = analyze_whale_position(orders)

    # Map position to signal format
    signal_map = {
        "BULLISH": "YES",
        "BEARISH": "NO",
        "NEUTRAL": "MIXED",
        "UNKNOWN": "UNKNOWN"
    }

    return {
        "signal": signal_map.get(analysis.get("position", "UNKNOWN"), "UNKNOWN"),
        "position": analysis.get("position", "UNKNOWN"),
        "confidence": analysis.get("confidence", 0),
        "buy_value": analysis.get("buy_value", 0),
        "sell_value": analysis.get("sell_value", 0),
        "ratio": analysis.get("ratio", 0),
        "order_count": analysis.get("total_orders", 0),
        "orders": orders[:5] if orders else []  # Include top 5 orders for reference
    }


def track_whales_for_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Track whale positions for multiple markets.

    Args:
        markets: List of market dictionaries with 'conditionId' key

    Returns:
        List of markets enriched with whale_signal data
    """
    enriched = []

    for market in markets:
        condition_id = market.get("conditionId", "")
        if condition_id:
            whale_data = get_whale_signal(condition_id)
            market["whale_signal"] = whale_data["signal"]
            market["whale_confidence"] = whale_data["confidence"]
            market["whale_analysis"] = whale_data
        else:
            market["whale_signal"] = "UNKNOWN"
            market["whale_confidence"] = 0
            market["whale_analysis"] = {}

        enriched.append(market)

    return enriched


def fetch_whale_activity_for_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fetch whale activity for markets.
    Alias for track_whales_for_markets.
    """
    return track_whales_for_markets(markets)


def calculate_insider_score(wallet: str, market: Dict[str, Any], whale_analysis: Dict[str, Any],
                           wallet_orders: List[Dict[str, Any]], wallet_info: Dict[str, Any]) -> dict:
    """
    Calculate insider suspicion score for a wallet's activity on a market.

    Args:
        wallet: Wallet address
        market: Market data dict
        whale_analysis: Full whale analysis containing orders list
        wallet_orders: List of orders from this specific wallet
        wallet_info: Enriched wallet data from enrich_wallet()

    Returns:
        Dict with score (0-100), patterns list, is_fresh_wallet, first_transaction
    """
    from datetime import datetime

    score = 0
    patterns = []

    # 1. WALLET AGE CHECK (30 points max)
    first_tx = wallet_info.get("first_transaction")
    is_fresh = False
    if first_tx:
        try:
            first_dt = datetime.fromisoformat(first_tx.replace("Z", "+00:00"))
            age_hours = (datetime.now(first_dt.tzinfo) - first_dt).total_seconds() / 3600
            is_fresh = age_hours < WHALE_WALLET_AGE_FRESH_HOURS
            if is_fresh:
                score += 30
                patterns.append("FRESH_WALLET")
            elif age_hours < WHALE_WALLET_AGE_NEW_HOURS:  # Less than 1 week
                score += 15
                patterns.append("NEW_WALLET")
        except:
            pass

    # 2. WIN RATE CHECK (30 points max)
    win_rate = wallet_info.get("win_rate", 0)
    if win_rate >= WHALE_WIN_RATE_HIGH:
        score += 30
        patterns.append("HIGH_WIN_RATE")
    elif win_rate >= WHALE_WIN_RATE_GOOD:
        score += 15
        patterns.append("GOOD_WIN_RATE")

    # 3. BET SIZE RELATIVE TO WALLET (30 points max)
    total_volume = sum(float(o.get("usd_value", 0)) for o in wallet_orders)
    total_trades = wallet_info.get("total_trades", 1)
    avg_order_size = total_volume / len(wallet_orders) if wallet_orders else 0

    # Large bet relative to typical activity
    if total_trades >= WHALE_MIN_TRADES_FOR_VOLUME:
        if avg_order_size >= WHALE_LARGE_BET_AVG_SIZE and total_volume >= WHALE_LARGE_BET_TOTAL_VOLUME:
            score += 20
            patterns.append("LARGE_BET")
    else:
        # For new wallets with few trades, any large bet is suspicious
        if total_volume >= WHALE_NEW_WALLET_VOLUME:
            score += 30
            patterns.append("CONCENTRATED_BET")

    # 4. CONCENTRATION CHECK (10 points max)
    open_positions = wallet_info.get("open_positions", 0)
    total_positions = wallet_info.get("total_positions", 0)
    if open_positions <= WHALE_POSITION_CONCENTRATION_MAX and total_volume >= WHALE_MIN_ORDER_SIZE:
        score += 10
        patterns.append("CONCENTRATED")

    # 5. CHECK IF KNOWN INSIDER (bonus points)
    known_insiders_path = "memory/insider_wallets.json"
    try:
        import json
        with open(known_insiders_path, "r") as f:
            known = json.load(f)
        if wallet in known:
            score += WHALE_KNOWN_INSIDER_BONUS
            patterns.append("KNOWN_INSIDER")
    except:
        pass

    # Cap score at 100
    score = min(score, 100)

    return {
        "score": score,
        "patterns": patterns,
        "is_fresh_wallet": is_fresh,
        "first_transaction": first_tx
    }


def detect_insider_with_follow(market: Dict[str, Any], whale_analysis: Dict[str, Any]) -> dict:
    """
    Detect insider activity for a single market based on whale orders.

    Args:
        market: Market data dict with title, slug, event_slug, conditionId, end_date, yes_price, no_price
        whale_analysis: Whale analysis dict from get_whale_signal() containing orders list

    Returns:
        Dict with 'profile_alert' and 'follow_alert' keys (values can be None)
    """
    from datetime import datetime

    profile_alert = None
    follow_alert = None

    orders = whale_analysis.get("orders", [])
    if not orders:
        return {"profile_alert": None, "follow_alert": None}

    # Group orders by wallet
    wallet_orders_map = {}
    for order in orders:
        maker = order.get("maker")
        if not maker:
            continue
        if maker not in wallet_orders_map:
            wallet_orders_map[maker] = []
        wallet_orders_map[maker].append(order)

    # Check each wallet
    for wallet, wallet_orders_list in wallet_orders_map.items():
        # Total volume for this wallet on this market
        total_volume = sum(float(o.get("usd_value", 0)) for o in wallet_orders_list)
        if total_volume < WHALE_MIN_ORDER_SIZE:  # Minimum threshold
            continue

        # Enrich wallet data
        wallet_info = enrich_wallet(wallet)

        # Calculate insider score with wallet_info
        result = calculate_insider_score(wallet, market, whale_analysis, wallet_orders_list, wallet_info)
        insider_score = result.get("score", 0)

        if insider_score < WHALE_INSIDER_SCORE_FILTER:
            continue

        direction = wallet_orders_list[0].get("side", "UNKNOWN")
        first_tx = result.get("first_transaction")
        wallet_age_hours = None
        if first_tx:
            try:
                first_dt = datetime.fromisoformat(first_tx.replace("Z", "+00:00"))
                wallet_age_hours = (datetime.now(first_dt.tzinfo) - first_dt).total_seconds() / 3600
            except:
                wallet_age_hours = None

        # Build profile alert (always send if score >= 40)
        profile_alert = {
            "alert_type": "INSIDER_PROFILE",
            "priority": "high" if insider_score >= 70 else "medium",
            "wallet": wallet,
            "market_title": market.get("title", ""),
            "market_slug": market.get("slug", ""),
            "event_slug": market.get("event_slug", ""),
            "conditionId": market.get("conditionId", ""),
            "amount": total_volume,
            "direction": direction,
            "insider_score": insider_score,
            "patterns": result.get("patterns", []),
            "is_fresh_wallet": result.get("is_fresh_wallet", False),
            "first_transaction": first_tx,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "reason": f"Insider wallet detected: {wallet[:12]}... Score: {insider_score}/100",
            # Enriched wallet data
            "wallet_name": wallet_info.get("name") or wallet_info.get("pseudonym"),
            "realized_pnl": wallet_info.get("realized_pnl", 0),
            "win_rate": wallet_info.get("win_rate", 0),
            "total_positions": wallet_info.get("total_positions", 0),
            "open_positions": wallet_info.get("open_positions", 0),
            "total_trades": wallet_info.get("total_trades", 0),
            "wallet_age_hours": wallet_age_hours,
            "profile_url": wallet_info.get("profile_url"),
            "order_count": len(wallet_orders_list)  # Number of orders from this wallet in this market
        }

        # FOLLOW ALERT: Only for active markets with score >= 70
        is_active = True
        end_date = market.get("end_date")
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                is_active = end_dt > datetime.now(end_dt.tzinfo)
            except:
                pass

        if is_active and insider_score >= INSIDER_STRONG_THRESHOLD:
            follow_alert = {
                "alert_type": "FOLLOW_INSIDER_BET",
                "priority": "high",
                "wallet": wallet,
                "market_title": market.get("title", ""),
                "market_slug": market.get("slug", ""),
                "event_slug": market.get("event_slug", ""),
                "conditionId": market.get("conditionId", ""),
                "amount": total_volume,
                "direction": direction,
                "insider_score": insider_score,
                "market_price": (market.get("market_probability", 0.5) * 100) if direction == "BUY" else ((1 - market.get("market_probability", 0.5)) * 100),
                "patterns": result.get("patterns", []),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "reason": f"Follow insider bet: {wallet[:12]}... betting {direction} ${total_volume:,.0f} (Score: {insider_score}/100)",
                "recommendation": f"Bet {direction} - Insider confidence: {insider_score}%",
                # Enriched wallet data
                "wallet_name": wallet_info.get("name") or wallet_info.get("pseudonym"),
                "realized_pnl": wallet_info.get("realized_pnl", 0),
                "win_rate": wallet_info.get("win_rate", 0),
                "total_positions": wallet_info.get("total_positions", 0),
                "open_positions": wallet_info.get("open_positions", 0),
                "total_trades": wallet_info.get("total_trades", 0),
                "wallet_age_hours": wallet_age_hours,
                "profile_url": wallet_info.get("profile_url"),
                "order_count": len(wallet_orders_list)  # Number of orders from this wallet in this market
            }

        # Only process first qualifying wallet per market (break after first)
        break

    return {"profile_alert": profile_alert, "follow_alert": follow_alert}


def check_whale_insider_for_markets(markets: List[Dict[str, Any]]) -> dict:
    """
    Check all markets for whale/insider activity.

    Args:
        markets: List of market data dicts (should have whale_analysis from fetch_whale_activity)

    Returns:
        Dict with 'profile_alerts' and 'follow_alerts' lists.
        Each list contains dicts with 'market' and 'alert' keys.
    """
    profile_alerts = []
    follow_alerts = []

    for market in markets:
        whale_analysis = market.get("whale_analysis", {})
        if not whale_analysis:
            continue

        detection = detect_insider_with_follow(market, whale_analysis)

        if detection.get("profile_alert"):
            profile_alerts.append({
                "market": market,
                "alert": detection["profile_alert"]
            })

        if detection.get("follow_alert"):
            follow_alerts.append({
                "market": market,
                "alert": detection["follow_alert"]
            })

    return {
        "profile_alerts": profile_alerts,
        "follow_alerts": follow_alerts
    }


def format_est_time() -> str:
    """Format current time in EST timezone for Discord messages."""
    from datetime import datetime, timezone, timedelta
    est_tz = timezone(timedelta(hours=-5))
    est_now = datetime.now(est_tz)
    return est_now.strftime("%Y-%m-%d %H:%M EST")


if __name__ == "__main__":
    # Test the module
    print("Testing Whale Tracker...")

    # Test with a sample market ID (replace with actual ID)
    test_market_id = "0x0000000000000000000000000000000000000000"  # Placeholder

    signal = get_whale_signal(test_market_id)
    print(f"Whale signal: {signal['signal']}")
    print(f"Position: {signal['position']}")
    print(f"Confidence: {signal['confidence']}")
    print(f"Buy value: ${signal['buy_value']}")
    print(f"Sell value: ${signal['sell_value']}")
