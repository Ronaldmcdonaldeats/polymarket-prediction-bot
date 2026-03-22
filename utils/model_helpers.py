#!/usr/bin/env python3
"""
Model Helpers Module
Unified interface for calling multiple LLM providers.
"""

import json
import os
import time
import threading
from types import MappingProxyType
from typing import Any, Dict, Optional
from concurrent.futures import ThreadPoolExecutor

import requests
from dotenv import load_dotenv

load_dotenv()

# API Endpoints
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Default Models
GROQ_MODEL = "llama-3.3-70b-versatile"
CEREBRAS_MODEL = "llama3.1-8b"
MISTRAL_MODEL = "mistral-large-latest"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct"
GEMINI_MODEL = "gemini-2.0-flash"
OLLAMA_MODEL = "qwen3.5"

# Rate limiting for all providers - shared across threads
_rate_lock = threading.Lock()
_rate_last_request_times = {
    "groq": 0,
    "cerebras": 0,
    "mistral": 0,
    "openrouter": 0,
    "gemini": 0
}

# Minimum delays between requests for each provider (seconds)
# Made immutable with MappingProxyType to prevent accidental modification
RATE_LIMIT_DELAYS = MappingProxyType({
    "groq": 2.0,        # Groq free tier limits
    "cerebras": 2.0,    # Cerebras limits
    "mistral": 2.0,     # Mistral limits
    "openrouter": 5.0,  # OpenRouter (most restrictive)
    "gemini": 2.0       # Gemini limits
})

# Global semaphore to limit total concurrent LLM API calls
# Prevents overwhelming system and respects overall API quotas
_llm_concurrency_semaphore = threading.Semaphore(6)  # Allow up to 6 concurrent LLM calls


def _wait_for_provider(provider: str):
    """
    Apply per-provider rate limiting delay.
    No-op if provider not in RATE_LIMIT_DELAYS (e.g., ollama).
    """
    if provider not in RATE_LIMIT_DELAYS:
        return

    with _rate_lock:
        last_time = _rate_last_request_times.get(provider, 0)
        elapsed = time.time() - last_time
        delay = RATE_LIMIT_DELAYS[provider]
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _rate_last_request_times[provider] = time.time()


def _add_json_instruction(prompt: str) -> str:
    """Append JSON instruction to prompt."""
    return f"{prompt}\n\nReturn ONLY valid JSON, no markdown, no code blocks, no explanation."


def _retry_with_backoff(max_retries: int = 3, base_delay: int = 2, rate_limit_delay: int = 10):
    """Decorator for retry logic with exponential backoff and special 429 handling.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        rate_limit_delay: Additional delay in seconds for 429 rate limit errors
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.HTTPError as e:
                    # Check for 429 rate limit error
                    if e.response is not None and e.response.status_code == 429:
                        delay = rate_limit_delay * attempt  # Longer backoff for rate limits
                        print(f"  Rate limited (429) on attempt {attempt}/{max_retries}, waiting {delay}s...")
                        time.sleep(delay)
                        if attempt == max_retries:
                            print(f"  Failed after {max_retries} attempts (rate limit)")
                            raise
                    else:
                        if attempt < max_retries:
                            delay = base_delay * (2 ** (attempt - 1))
                            print(f"  Retry {attempt}/{max_retries}: {e}, waiting {delay}s...")
                            time.sleep(delay)
                        else:
                            print(f"  Failed after {max_retries} attempts")
                            raise
                except (requests.RequestException, json.JSONDecodeError) as e:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** (attempt - 1))
                        print(f"  Retry {attempt}/{max_retries}: {e}, waiting {delay}s...")
                        time.sleep(delay)
                    else:
                        print(f"  Failed after {max_retries} attempts")
                        raise
            return None
        return wrapper
    return decorator


@_retry_with_backoff(max_retries=3, base_delay=2)
def call_ollama(system: str, user: str, json_mode: bool = True, model: str = OLLAMA_MODEL) -> Any:
    """
    Call Ollama API (local inference).

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict
        model: Model name (default: qwen3.5)

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    # Local inference, no per-provider rate limiting, but respect global concurrency
    with _llm_concurrency_semaphore:
        if json_mode:
            user = _add_json_instruction(user)

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json" if json_mode else None,
                "options": {"num_ctx": 65536, "temperature": 0.3},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            },
            timeout=120
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]

        if json_mode:
            return json.loads(content)
        return content


@_retry_with_backoff(max_retries=3, base_delay=2)
def call_groq(system: str, user: str, json_mode: bool = True) -> Any:
    """
    Call Groq API.
    Model: llama-3.3-70b

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    with _llm_concurrency_semaphore:
        _wait_for_provider("groq")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment")

        if json_mode:
            user = _add_json_instruction(user)

        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"} if json_mode else None
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if json_mode:
            return json.loads(content)
        return content


@_retry_with_backoff(max_retries=3, base_delay=2)
def call_cerebras(system: str, user: str, json_mode: bool = True) -> Any:
    """
    Call Cerebras API.
    Model: llama-3.3-70b

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    with _llm_concurrency_semaphore:
        _wait_for_provider("cerebras")

        api_key = os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            raise ValueError("CEREBRAS_API_KEY not found in environment")

        if json_mode:
            user = _add_json_instruction(user)

        response = requests.post(
            CEREBRAS_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": CEREBRAS_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.3
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if json_mode:
            return json.loads(content)
        return content


@_retry_with_backoff(max_retries=3, base_delay=2)
def call_mistral(system: str, user: str, json_mode: bool = True) -> Any:
    """
    Call Mistral API.
    Model: mistral-large

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    with _llm_concurrency_semaphore:
        _wait_for_provider("mistral")

        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY not found in environment")

        if json_mode:
            user = _add_json_instruction(user)

        response = requests.post(
            MISTRAL_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"} if json_mode else None
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if json_mode:
            return json.loads(content)
        return content


@_retry_with_backoff(max_retries=3, base_delay=2, rate_limit_delay=15)
def call_openrouter(system: str, user: str, json_mode: bool = True) -> Any:
    """
    Call OpenRouter API.
    Model: llama-3.3-70b

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    with _llm_concurrency_semaphore:
        _wait_for_provider("openrouter")

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment")

        if json_mode:
            user = _add_json_instruction(user)

        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://polymarket-bot.local",
                "X-Title": "Polymarket Research Bot",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.3
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        if json_mode:
            return json.loads(content)
        return content


@_retry_with_backoff(max_retries=3, base_delay=2)
def call_gemini(system: str, user: str, json_mode: bool = True) -> Any:
    """
    Call Google Gemini API.
    Model: gemini-2.0-flash

    Args:
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed JSON dict if json_mode=True, else string
    """
    with _llm_concurrency_semaphore:
        _wait_for_provider("gemini")

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")

        if json_mode:
            user = _add_json_instruction(user)

        # Combine system and user for Gemini
        full_prompt = f"{system}\n\n{user}"

        response = requests.post(
            f"{GEMINI_API_URL}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": full_prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.3
                }
            },
            timeout=60
        )
        response.raise_for_status()
        content = response.json()["candidates"][0]["content"]["parts"][0]["text"]

        if json_mode:
            return json.loads(content)
        return content


# Convenience function to call the right provider based on agent role
def call_model(provider: str, system: str, user: str, json_mode: bool = True) -> Any:
    """
    Generic caller that routes to the appropriate provider.

    Args:
        provider: One of: ollama, groq, cerebras, mistral, openrouter, gemini
        system: System prompt
        user: User prompt
        json_mode: If True, returns parsed JSON dict

    Returns:
        Parsed response from the selected provider
    """
    providers = {
        "ollama": call_ollama,
        "groq": call_groq,
        "cerebras": call_cerebras,
        "mistral": call_mistral,
        "openrouter": call_openrouter,
        "gemini": call_gemini
    }

    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(providers.keys())}")

    return providers[provider](system, user, json_mode)
