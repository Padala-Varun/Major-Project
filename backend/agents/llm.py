"""
Shared LLM client
One factory for every agent's chat model, with client-side pacing and retries.
langchain-mistralai's sync client doesn't retry, and a multi-agent run makes
several calls back to back, so rate limits (429) are routine on smaller plans.
"""

import random
import threading
import time

import httpx
from langchain_mistralai import ChatMistralAI
from config import MISTRAL_API_KEY, LLM_MODEL, LLM_MAX_TOKENS

MIN_INTERVAL_SECONDS = 1.1   # stay under ~1 request/second across all agents
MAX_ATTEMPTS = 6             # backoff waits ≈ 2+4+8+16+30 s before giving up
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_pace_lock = threading.Lock()
_last_call = 0.0


def _pace():
    """Block until at least MIN_INTERVAL_SECONDS have passed since the last call."""
    global _last_call
    with _pace_lock:
        wait = _last_call + MIN_INTERVAL_SECONDS - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


class PacedLLM:
    """Wraps a chat model's invoke() with pacing and retry on transient errors."""

    def __init__(self, llm: ChatMistralAI):
        self.llm = llm

    def invoke(self, messages):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            _pace()
            try:
                return self.llm.invoke(messages)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                if status not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(min(30, 2 ** attempt) + random.random())


def make_llm(temperature: float) -> PacedLLM:
    return PacedLLM(ChatMistralAI(
        model=LLM_MODEL,
        api_key=MISTRAL_API_KEY,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    ))
