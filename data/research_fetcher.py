#!/usr/bin/env python3
"""
Research Fetcher Module
Fetches news from RSS feeds and searches for relevant articles.
"""

import re
from typing import Dict, List, Any, Optional

import feedparser
import requests

# RSS Feed URLs
RSS_FEEDS = {
    "reuters": "https://feeds.reuters.com/reuters/topNews",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "bbc": "http://feeds.bbci.co.uk/news/rss.xml",
    "politico": "https://rss.politico.com/politics.xml",
    "wsj": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "ft": "https://www.ft.com/rss/home/uk",
    "sky": "http://feeds.skynews.com/feeds/rss/world.xml",
    # Crypto
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    # Finance/Markets
    "bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
    "marketwatch": "https://www.marketwatch.com/rss/topstories",
    # Politics
    "axios": "https://www.axios.com/rss.xml",
    "thehill": "https://thehill.com/rss.xml",
    # Tech
    "techcrunch": "https://techcrunch.com/feed/"
}


def fetch_rss_feeds() -> Dict[str, List[Dict[str, str]]]:
    """
    Fetch and parse all RSS feeds.

    Returns:
        Dict mapping feed name to list of articles
    """
    results = {}

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            articles = []

            for entry in feed.entries[:10]:  # Get top 10 from each feed
                articles.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:500],
                    "link": entry.get("link", ""),
                    "published": entry.get("published", "")
                })

            results[name] = articles
        except Exception:
            results[name] = []

    return results


def extract_keywords(market_title: str) -> List[str]:
    """
    Extract keywords from market title for searching.

    Args:
        market_title: The market title

    Returns:
        List of keywords
    """
    # Remove common words
    stop_words = {"will", "the", "a", "an", "in", "on", "at", "to", "for",
                    "of", "with", "by", "from", "as", "is", "be", "this", "that",
                    "it", "and", "or", "but", "if", "then", "than", "when", "where"}

    # Clean and split
    words = re.findall(r'\b[a-zA-Z]{3,}\b', market_title.lower())
    keywords = [w for w in words if w not in stop_words]

    return keywords[:5]  # Return top 5 keywords


def search_articles(keywords: List[str], articles: Dict[str, List[Dict]], max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search articles for relevance to keywords.

    Args:
        keywords: List of keywords to search for
        articles: Dict of RSS feed results
        max_results: Maximum results to return

    Returns:
        List of relevant articles with relevance scores
    """
    scored = []

    for feed_name, feed_articles in articles.items():
        for article in feed_articles:
            score = 0
            title_lower = article["title"].lower()
            summary_lower = article.get("summary", "").lower()

            for keyword in keywords:
                if keyword in title_lower:
                    score += 3  # Higher score for title match
                if keyword in summary_lower:
                    score += 1

            if score > 0:
                scored.append({
                    **article,
                    "source": feed_name,
                    "relevance_score": score
                })

    # Sort by relevance and return top results
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:max_results]


def get_market_research(market_title: str, market_description: str = "") -> Dict[str, Any]:
    """
    Get research for a specific market.

    Args:
        market_title: The market title
        market_description: Optional market description

    Returns:
        Dict with research findings
    """
    # Fetch all RSS feeds
    all_articles = fetch_rss_feeds()

    # Extract keywords from title and description
    keywords = extract_keywords(market_title)
    if market_description:
        keywords.extend(extract_keywords(market_description))
        keywords = list(set(keywords))  # Remove duplicates

    # Search for relevant articles
    relevant = search_articles(keywords, all_articles)

    # Calculate confidence based on coverage
    if len(relevant) >= 3:
        confidence = "high"
    elif len(relevant) >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "keywords": keywords,
        "articles_found": len(relevant),
        "articles": relevant,
        "confidence": confidence,
        "sources": list(set(a["source"] for a in relevant))
    }


def enrich_markets_with_research(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich markets with research data.

    Args:
        markets: List of market dictionaries

    Returns:
        Markets with added research field
    """
    # Fetch RSS feeds once
    all_articles = fetch_rss_feeds()

    enriched = []
    for market in markets:
        keywords = extract_keywords(market.get("title", ""))
        if market.get("description"):
            desc_keywords = extract_keywords(market["description"])
            keywords = list(set(keywords + desc_keywords))

        relevant = search_articles(keywords, all_articles)

        if len(relevant) >= 3:
            confidence = "high"
        elif len(relevant) >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        market["research"] = {
            "keywords": keywords,
            "articles_found": len(relevant),
            "articles": relevant,
            "confidence": confidence
        }

        enriched.append(market)

    return enriched


def fetch_research_for_markets(markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fetch research for markets.
    Alias for enrich_markets_with_research.
    """
    return enrich_markets_with_research(markets)


if __name__ == "__main__":
    # Test the module
    print("Testing Research Fetcher...")

    test_title = "Will Donald Trump win the 2024 US Presidential Election?"
    result = get_market_research(test_title)

    print(f"Keywords: {result['keywords']}")
    print(f"Articles found: {result['articles_found']}")
    print(f"Confidence: {result['confidence']}")
    print("\nTop articles:")
    for article in result['articles'][:3]:
        print(f"  - [{article['source']}] {article['title'][:60]}... (score: {article['relevance_score']})")
