"""Lazy-initialized AsyncOpenAI client."""
import os
from openai import AsyncOpenAI
from src.utils.doppler import get_secret

_client = None


def get_client() -> AsyncOpenAI:
    """Get or create AsyncOpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY") or get_secret("OPENAI_API_KEY")
        _client = AsyncOpenAI(api_key=api_key)
    return _client
