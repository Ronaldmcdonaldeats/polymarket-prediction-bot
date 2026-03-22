# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python-based prediction market analysis system that scans Polymarket, aggregates signals from multiple sources (Kalshi, whale tracking, RSS feeds), and uses a 4-agent panel with a judge to identify betting opportunities. Notifications are sent to Discord.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment (copy and edit .env with your API keys)
# .env file must contain: WEBHOOK_URL, OPENROUTER_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY, GOOGLE_API_KEY

# Run the bot (continuous mode)
python main.py

# Run single cycle
python -c "from main import run_cycle; run_cycle()"
```

## Project Structure

```
polymarket-pred/
├── main.py              # Entry point, orchestrates the full pipeline
├── agents/              # LLM agent logic
│   ├── panel_agents.py  # 4 specialized voting agents (Quant, Contrarian, Research, Risk Manager)
│   ├── judge.py         # Meta-agent that evaluates votes and makes final decisions
│   └── gemini_synthesis.py  # Cross-market synthesis using Google Gemini
├── data/                # Data ingestion
│   ├── data_fetcher.py        # Polymarket Gamma API + CLOB fetching, filtering, scoring
│   ├── kalshi_fetcher.py      # Kalshi API fetching with entity-based matching
│   ├── research_fetcher.py    # RSS feed aggregation (14 sources)
│   └── cross_platform.py      # Web scraping for consensus data
├── alerts/              # Output & notifications
│   ├── discord_webhook.py     # Rich Discord embeds with smart truncation
│   └── whale_tracker.py       # Polymarket CLOB whale detection & profiling
├── core/                # Core business logic
│   ├── kelly_calculator.py    # Kelly Criterion stake sizing with multipliers
│   ├── resolution.py          # Bet outcome checking & P&L updates
│   ├── tuner.py               # Self-tuning of multipliers based on performance
│   └── startup.py             # Startup validation checks
├── utils/               # Utilities & configuration
│   ├── config.py              # All thresholds, limits, weights (centralized)
│   ├── conversions.py         # pct/decimal conversion + smart_truncate()
│   ├── memory_system.py       # JSON persistence layer
│   └── model_helpers.py       # Unified LLM provider interface with rate limiting
├── memory/              # JSON data files (auto-created)
│   ├── predictions.json        # Active and resolved bets
│   ├── multipliers.json        # Tuned confidence/panel/whale multipliers
│   ├── agent_scores.json       # Historical accuracy per agent
│   ├── keyword_performance.json # Dynamic keyword weights
│   ├── lessons.json            # Captured learnings
│   ├── recently_recommended.json # 3-hour exclusion cache
│   └── whale_alerts_sent.json  # Deduplication store
└── .claude/skills/      # Installed Claude Code skills
    └── ccpm/            # CCPM project management skill
```

## Architecture: Multi-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         main.py (run_cycle)                             │
├──────────┬──────────┬──────────┬─────────────┬────────────┬───────────┤
│  Fetch   │ Enrich   │ Analyze  │   Synthesize │   Vote    │  Judge    │
│  (Data)  │ (Whales, │ (Agents) │   (Gemini)   │ (Panel)   │  (Final)  │
│          │  Research│          │              │           │           │
├──────────┴──────────┴──────────┴──────────────┴───────────┴───────────┤
│  1. Fetch Polymarket markets (200 limit, liquidity filter)              │
│  2. Fetch Kalshi markets (all available, matches computed later)       │
│  3. Gather RSS research for each Polymarket                           │
│  4. Fetch cross-platform consensus                                    │
│  5. Track whale activity & insider patterns                          │
│  6. Gemini cross-market synthesis                                     │
│  7. Panel agents vote (Quant, Contrarian, Research, Risk Manager)     │
│  8. Judge decides final bet direction (YES/NO/SKIP)                   │
│  9. Kelly calculator determines stake size                            │
│ 10. Discord notification sent                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Components

#### Data Ingestion Layer
- **data_fetcher.py**: Fetches from Polymarket Gamma API, applies filters (volume, liquidity, category, time, sports blacklist). Scores markets by news-predictability keywords.
- **kalshi_fetcher.py**: Fetches CFTC-regulated markets. Uses entity/event/keyword matching with weighted scoring to find cross-market arbitrage opportunities.
- **research_fetcher.py**: Aggregates 14 RSS feeds (Reuters, Bloomberg, CoinDesk, etc.) for market-specific research.
- **cross_platform.py**: Scrapes additional sources for consensus signals.
- **whale_tracker.py**: Tracks large trader activity via Polymarket CLOB, calculates insider scores, patterns (accumulation/distribution), and wallet history.

#### Analysis Layer
- **gemini_synthesis.py**: Uses Google Gemini to synthesize cross-market insights and produce a narrative summary.
- **panel_agents.py**: 4 specialized agents run in parallel:
  - **Quant (Groq)**: Price action, volume, Kalshi arbitrage signals
  - **Contrarian (Cerebras)**: Overreaction detection, sentiment extremes
  - **Research (Mistral)**: News narrative analysis, keyword relevance
  - **Risk Manager (OpenRouter)**: Position sizing, bankroll protection, Kelly adjustments
- **judge.py**: Meta-agent (Cerebras) evaluates panel votes, confidence, signals, and multipliers to output final decision with reasoning.

#### Execution Layer
- **kelly_calculator.py**: Kelly Criterion with dynamic multipliers (confidence, panel agreement, whale signal, cross-platform signal, category bonus, Kalshi gap).
- **discord_webhook.py**: Sends rich Discord embeds with smart text truncation (`smart_truncate` from `utils/conversions.py`).
- **resolution.py**: Hourly checks for settled markets, updates win/loss, recalculates agent scores.
- **tuner.py**: Every 3 resolved bets, adjusts multipliers based on actual performance trends.

#### Infrastructure Layer
- **memory_system.py**: JSON-based persistence (no database). Handles atomic reads/writes, file locking.
- **model_helpers.py**: Unified wrapper for Groq, Cerebras, Mistral, OpenRouter, Gemini, Ollama. Thread-safe rate limiting with `ThreadPoolExecutor`, exponential backoff.
- **startup.py**: Validates Ollama, API keys, Discord webhook, memory directory.

## Critical Implementation Details

### Probability Units (Important!)
- **External APIs** return percentages (0-100): Polymarket Gamma, Kalshi
- **Internal calculations** use decimals (0-1): Kelly, edge calculations
- **LLM prompts** expect percentages (0-100): Panel agents, judge
- **Display** uses percentages: Discord embeds, console output
- **Edge calculation**: `edge = abs(estimated_probability - market_price)` — computed in code, not LLM.

### Smart Truncation
Use `utils.conversions.smart_truncate(text, max_length)` for all user-facing text displays. It truncates at word boundaries and adds `...`. Never use hardcoded slicing like `text[:100]` on display fields.

### Kalshi Matching Algorithm (data/kalshi_fetcher.py)

**Goal**: Find Kalshi market that corresponds to a Polymarket market for arbitrage detection.

**Process**:
1. `extract_market_tags()`: Extracts entities, event types, keywords, category from Polymarket title/description.
2. `match_kalshi()`: Scores all Kalshi markets using:
   - **Entity matches**: Direct word-boundary matches on entity names or aliases. Score = entity weight (12 for Trump/Biden, 10 for election, 9 for president/vote, 8 for Fed/inflation/etc.)
   - **Partial entity matches**: If entity appears in text without word boundary, half weight (min 1).
   - **Event type matches**: +5 if Polymarket event type keywords appear in Kalshi title.
   - **Keyword matches**: +2 for each significant keyword (len > 4) found in Kalshi title.
   - **Category bonus**: +category_weight if Polymarket category matches Kalshi category and is in allowed set (politics, economics, finance, crypto, weather, events).

3. Requires minimum score `KALSHI_MIN_MATCH_SCORE = 6` (prevents false positives from sports markets).
4. Signal strength based on price gap: STRONG (≥15%), MODERATE (8-15%), ALIGNED (<8%).

**Note**: `KALSHI_ENTITY_WEIGHTS` in `config.py` is currently unused. The actual weights are the `NAMED_ENTITIES` dict in `kalshi_fetcher.py`.

**Current Kalshi API state**: The public `api.elections.kalshi.com` endpoint primarily returns esports markets. Political/election markets may be seasonally unavailable. The matching code is optimized for when such markets appear; currently most cycles produce `NO MATCH`.

### Multiplier System (tuner.py)

Tuner adjusts these based on resolved bet performance:
- `confidence_mult`: high=1.0, medium=0.6, low=0.3
- `panel_mult`: strong=1.0, moderate=0.7, weak=0.4
- `whale_mult`: agrees=1.15, disagrees_or_unknown=0.85
- `cross_platform_mult`: STRONG=1.0, MODERATE=0.95, WEAK=0.90
- `category_bonus`: economics=20, politics=10, sports=-100 (blocked), crypto=-100 (high risk)
- `kalshi_mult`: strong=1.15, moderate=1.05 (applied to arb signal)

### Memory System

All files in `memory/` are JSON. Key files:
- `predictions.json`: Each entry: `{market_id, title, direction, stake_usd, outcome, profit_loss, timestamps, ...}`
- `recently_recommended.json`: `{recommendations: [{market_id, timestamp}]}` used to avoid duplicate bet suggestions within 3 hours.
- `multipliers.json`: Current multiplier values (confidence, panel, whale, cross_platform, category_bonus, kalshi_mult).
- `keyword_performance.json`: Tracks win rates per keyword; used to adjust `BASE_KEYWORD_WEIGHTS`.
- `agent_scores.json`: `{agent_name: {correct, total, accuracy}}`
- `lessons.json`: Free-form lessons extracted from resolved bets.
- `insider_wallets.json`: Known insider wallet addresses that trigger alerts.
- `whale_alerts_sent.json`: `{market_id: {wallet: alert_type}}` for deduplication.
- `tuning_log.json`: History of multiplier adjustments for debugging.

### Rate Limiting

Per-provider minimum delays enforced in `model_helpers.py`:
- Groq: 2s
- Cerebras: 2s
- Mistral: 2s
- OpenRouter: 5s (higher due to stricter limits)
- Gemini: 2s
- Ollama: no limit (local)

Panel agents use `ThreadPoolExecutor` with random staggering (1-3s) to spread load and avoid burst limits.

## Common Development Commands

```bash
# Test individual modules
python -c "from data.data_fetcher import fetch_filtered_markets; print(len(fetch_filtered_markets(20)))"
python -c "from data.kalshi_fetcher import fetch_kalshi_markets, match_kalshi; print(fetch_kalshi_markets()[:2])"
python -c "from agents.panel_agents import run_panel_vote; print(run_panel_vote({'title': 'Test', 'yes_price': 50}, {}))"

# Check memory files
ls memory/
cat memory/predictions.json | python -m json.tool | head -50
cat memory/multipliers.json | python -m json.tool

# Clear recommendation cache to force new bets
echo '{"recommendations": []}' > memory/recently_recommended.json

# Run specific step only (debug)
python -c "
from data.data_fetcher import fetch_filtered_markets
from agents.panel_agents import run_panel_voting
from agents.judge import judge_decision
markets = fetch_filtered_markets(10)
results = run_panel_voting(markets)
for m in results:
    print(m['title'][:50], m.get('panel_vote', {}).get('consensus_direction'))
"

# Test Discord webhook
python -c "from alerts.discord_webhook import send_error_embed; send_error_embed('Test', 'Debug message')"

# Run full pipeline (single cycle)
python -c "from main import run_cycle; run_cycle()"
```

## Environment Variables

Required in `.env`:
```
WEBHOOK_URL=https://discord.com/api/webhooks/...
OPENROUTER_API_KEY=sk-or-v1-...
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
MISTRAL_API_KEY=...
GOOGLE_API_KEY=...
OLLAMA_URL=http://localhost:11434  # optional, defaults to localhost:11434
```

## Testing & Debugging

- Full cycle test: `python -c "from main import run_cycle; run_cycle()"`
- Kalshi connectivity: `python -c "from data.kalshi_fetcher import fetch_kalshi_markets; print(len(fetch_kalshi_markets()))"`
- Panel logic: `python -c "from agents.panel_agents import run_panel_vote; print(run_panel_vote({'title': '...', 'yes_price': 50}, {}))"`
- Review recent predictions: `cat memory/predictions.json | tail -20`
- Check memory files for corruption: `python -m json.tool memory/predictions.json > /dev/null && echo OK || echo ERROR`

## Important Notes

1. **Never hardcode truncation**: Use `smart_truncate()` from `utils/conversions.py` for any user-facing text. Avoid `text[:N]` slicing.
2. **All thresholds in config.py**: Do not scatter magic numbers. Add new configs to `utils/config.py`.
3. **Probability units**: Stay consistent. External APIs: 0-100. Internal: 0-1. LLM prompts: 0-100.
4. **Edge calculation**: Always compute as `abs(estimated_probability - market_price)` in code; don't ask LLM to do math.
5. **Kalshi matching**: Currently `api.elections.kalshi.com` returns mostly esports. Political markets may appear seasonally. The matching logic is ready.
6. **Panel agent optimization**: Risk Manager only runs if Quant OR Contrarian signals potential (`YES`/`NO`). Saves ~50% OpenRouter costs.
7. **Memory integrity**: All writes are atomic (write to temp then rename). Never edit JSON files manually while bot is running.

## Skills

Installed skills in `.claude/skills/`:
- **ccpm**: CCPM project management skill for spec-driven development.

Invoke via `/ccpm` slash command or `Skill` tool.

## Recent Changes (for context)

- 2026-03-22: Implemented `smart_truncate` for all display text (moved to `utils/conversions.py`).
- 2026-03-22: Improved Kalshi matching: removed broken relevance filter, increased entity weights (Trump/Biden=12, Fed=11, election=10), raised threshold to 6, boosted event/keyword bonuses.
- 2026-03-22: Installed CCPM skill for project management.
