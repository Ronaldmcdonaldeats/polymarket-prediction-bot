#!/usr/bin/env python3
"""
Startup Checks Module
Handles all pre-flight checks before the bot runs.
"""

import os
import sys

import requests
from dotenv import load_dotenv

from utils.memory_system import ensure_memory_files

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

REQUIRED_ENV_VARS = [
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "WEBHOOK_URL"
]


def check_ollama() -> bool:
    """Verify Ollama is running at localhost:11434."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def check_env_vars() -> tuple:
    """
    Check required environment variables.

    Returns:
        Tuple of (all_present: bool, missing: list)
    """
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing.append(var)
    return (len(missing) == 0, missing)


def check_model_available(model_name: str = "qwen3.5") -> bool:
    """Check if qwen3.5 model is available in Ollama."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            for model in models:
                if model_name in model.get("name", ""):
                    return True
        return False
    except requests.RequestException:
        return False


def startup_checks() -> bool:
    """
    Run all startup checks.

    Returns:
        True if all checks passed, False otherwise
    """
    print("=" * 60)
    print("Polymarket Prediction Bot - Startup Checks")
    print("=" * 60)

    all_passed = True

    # Step 1: Check Ollama running and model available
    print("\n1. Checking Ollama...")
    if check_ollama():
        print("   [OK] Ollama is running")
        if check_model_available("qwen3.5"):
            print("   [OK] Model qwen3.5 is available")
        else:
            print("   [X] Model qwen3.5 not found. Run: ollama pull qwen3.5")
            all_passed = False
    else:
        print("   [X] Ollama not running at http://localhost:11434")
        print("     Start with: ollama serve")
        all_passed = False

    # Step 2: Check all API keys present
    print("\n2. Checking API keys...")
    env_ok, missing = check_env_vars()
    if env_ok:
        print("   [OK] All required API keys found")
    else:
        print(f"   [X] Missing: {', '.join(missing)}")
        all_passed = False

    # Step 3: Check webhook URL configured
    print("\n3. Checking Discord webhook...")
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if webhook_url and webhook_url.startswith("https://discord.com/api/webhooks/"):
        print("   [OK] Webhook URL configured")
    elif webhook_url:
        print("   [WARN] Webhook URL found but doesn't look like Discord webhook")
    else:
        print("   [X] WEBHOOK_URL not set - Discord notifications disabled")

    # Step 4: Check Kalshi connectivity
    print("\n4. Checking Kalshi API...")
    from data.kalshi_fetcher import test_kalshi_connectivity
    kalshi_ok, kalshi_msg = test_kalshi_connectivity()
    try:
        print(f"   {kalshi_msg}")
    except UnicodeEncodeError:
        # Fallback for Windows console encoding issues
        print(f"   {kalshi_msg.encode('ascii', 'ignore').decode('ascii')}")

    # Step 5: Ensure memory files exist
    print("\n5. Checking memory files...")
    ensure_memory_files()
    print("   [OK] Memory files ready")

    print("\n" + "=" * 60)
    if all_passed:
        print("[OK] All startup checks passed")
    else:
        print("[X] Some startup checks failed")
    print("=" * 60 + "\n")

    return all_passed


if __name__ == "__main__":
    success = startup_checks()
    sys.exit(0 if success else 1)
