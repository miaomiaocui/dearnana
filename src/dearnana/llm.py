"""LLM provider abstraction.

Two backends, selected via DEARNANA_LLM_PROVIDER:

- "anthropic" (default): the Anthropic API; requires ANTHROPIC_API_KEY.
- "ollama": a local Ollama server (https://ollama.com) via its native
  HTTP API — no API key, and the care-needs description never leaves
  the machine.

Both expose the same two operations and return None on any failure so
callers can fall back gracefully (keyword parsing / data-only report).
"""

import os
from typing import Protocol

import anthropic
import httpx
from pydantic import BaseModel, ValidationError

from dearnana.config import (
    CONDITION_PARSER_MODEL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_HOST,
)

PARSE_MAX_TOKENS = 500


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str | None:
        """Free-text completion (the recommendation report)."""

    def parse(self, prompt: str, schema: type[BaseModel]) -> BaseModel | None:
        """Schema-constrained completion (the needs profile)."""


class AnthropicProvider:
    """Anthropic API backend (default)."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str) -> str | None:
        try:
            message = self._client.messages.create(
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
        except (anthropic.APIError, anthropic.APIConnectionError):
            return None
        return next((b.text for b in message.content if b.type == "text"), "") or None

    def parse(self, prompt: str, schema: type[BaseModel]) -> BaseModel | None:
        if not hasattr(self._client.messages, "parse"):
            return None  # SDK too old for structured outputs
        try:
            response = self._client.messages.parse(
                model=CONDITION_PARSER_MODEL,
                max_tokens=PARSE_MAX_TOKENS,
                output_format=schema,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.parsed_output
        except (anthropic.APIError, anthropic.APIConnectionError, ValidationError):
            return None


class OllamaProvider:
    """Local Ollama backend via the native /api/chat endpoint.

    Structured parsing uses Ollama's `format` parameter (a JSON schema),
    available since Ollama 0.5.
    """

    # Local inference can be slow on modest hardware
    _TIMEOUT = httpx.Timeout(600, connect=10)

    def __init__(self, host: str | None = None):
        self._host = (host or OLLAMA_HOST).rstrip("/")
        self._model = os.environ.get("DEARNANA_LLM_MODEL") or OLLAMA_DEFAULT_MODEL
        self._parser_model = os.environ.get("DEARNANA_PARSER_MODEL") or self._model

    def _chat(self, prompt: str, model: str, fmt: dict | None = None) -> str | None:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": LLM_TEMPERATURE,
                "num_predict": LLM_MAX_TOKENS,
            },
        }
        if fmt is not None:
            payload["format"] = fmt
        try:
            resp = httpx.post(f"{self._host}/api/chat", json=payload, timeout=self._TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content") or None
        except (httpx.HTTPError, ValueError):
            return None

    def generate(self, prompt: str) -> str | None:
        return self._chat(prompt, self._model)

    def parse(self, prompt: str, schema: type[BaseModel]) -> BaseModel | None:
        content = self._chat(prompt, self._parser_model, fmt=schema.model_json_schema())
        if not content:
            return None
        try:
            return schema.model_validate_json(content)
        except ValidationError:
            return None


def get_provider() -> LLMProvider | None:
    """Build the configured provider, or None if no provider is usable.

    None means callers should use their non-AI fallbacks. The provider
    name is read from the environment at call time so library users can
    switch providers without re-importing.
    """
    name = os.environ.get("DEARNANA_LLM_PROVIDER", "anthropic").strip().lower()
    if name == "ollama":
        return OllamaProvider()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return AnthropicProvider(api_key)
    return None
