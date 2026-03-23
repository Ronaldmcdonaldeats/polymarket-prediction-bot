# Polymarket Prediction Bot

An AI-powered trading bot that analyzes Polymarket prediction markets using multiple AI agents to identify profitable betting opportunities.

## How It Works

1. **Fetches** active markets from Polymarket
2. **Analyzes** using 4 specialized AI agents:
   - Quant agent (price action, volume)
   - Contrarian agent (overreaction detection)
   - Research agent (news analysis)
   - Risk manager (position sizing)
3. **Cross-checks** with Kalshi markets for arbitrage opportunities
4. **Tracks** whale activity and insider patterns
5. **Decides** final bets using a judge agent
6. **Calculates** optimal stake using Kelly Criterion
7. **Notifies** via Discord webhook

## Installation

```bash
# Clone and install
git clone https://github.com/Ronaldmcdonaldeats/polymarket-prediction-bot.git
cd polymarket-prediction-bot
pip install -r requirements.txt

# Add your API keys
cp .env.example .env
# Edit .env with your actual keys

# Run
python main.py
```

## Configuration

Create a `.env` file in the project root:

```env
WEBHOOK_URL=https://discord.com/api/webhooks/your/webhook
OPENROUTER_API_KEY=sk-or-v1-...
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
MISTRAL_API_KEY=...
GOOGLE_API_KEY=...
```

Required APIs: OpenRouter, Groq, Cerebras, Mistral, Google (Gemini).

## Requirements

- Python 3.8+
- Discord webhook URL
- API keys from: OpenRouter, Groq, Cerebras, Mistral, Google AI Studio

## Project Structure

- `main.py` - Main orchestrator
- `agents/` - AI agents and judge
- `data/` - Data fetchers (Polymarket, Kalshi, RSS)
- `alerts/` - Discord webhook and whale tracking
- `core/` - Kelly calculator, resolution, tuner
- `utils/` - Configuration, memory, model helpers
- `memory/` - Runtime data (auto-created)

## Security

- **Never commit `.env`** - it contains your API keys
- `.env` is in `.gitignore`
- Memory files contain trading history and are not committed
- See `CLAUDE.md` for detailed developer docs

## License

MIT - see LICENSE file.

## Disclaimer

For educational purposes only. Trading prediction markets involves risk. Use at your own discretion.
