"""LLM provider adapters for StateJar.

Only OpenRouter is implemented in Round 1; the other providers are
placeholders so the gateway's provider registry is already extensible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx


class LLMProvider(ABC):
    """A chat-completion capable provider."""

    name: str

    @abstractmethod
    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        """Return {"content": str, "model": str, "usage": dict, "raw": dict}."""


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_context},
                {"role": "user", "content": user_message},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        response = httpx.post(
            self.BASE_URL, json=payload, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        data = response.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", model),
            "usage": data.get("usage", {}),
            "raw": data,
        }


class DemoProvider(LLMProvider):
    """Scripted assistant for the playground's instant demo.

    Needs no API key and makes no network calls; replies are canned per
    demo step. The memory pipeline around it (ingest, retrieval, audit)
    still runs for real — only this reply is scripted.
    """

    name = "demo"

    _SCRIPT = [
        ("book", "Booking with your saved preferences — I'll email you the "
                 "confirmation and keep it under ₹2000. Only your delivery time "
                 "is pending: when should it arrive?"),
        ("budget is now", "Updated — your budget is now ₹2500. The earlier ₹2000 "
                          "isn't overwritten: it's preserved in your version history, "
                          "and this disclosure was logged in the audit trail."),
        ("name is", "Got it, Ayaan! I've noted your email preference and ₹2000 budget."),
    ]
    _FALLBACK = (
        "This is StateJar's scripted demo assistant — the memory state, handles, "
        "and audit entries in the side panel are real."
    )

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        lowered = user_message.lower()
        content = next(
            (reply for trigger, reply in self._SCRIPT if trigger in lowered),
            self._FALLBACK,
        )
        return {"content": content, "model": "scripted-demo", "usage": {}, "raw": {}}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def chat(self, api_key: str, model: str, system_context: str, user_message: str) -> dict[str, Any]:
        raise NotImplementedError("OpenAI provider is planned for a later round")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def chat(self, api_key: str, model: str, system_context: str, user_message: str) -> dict[str, Any]:
        raise NotImplementedError("Anthropic provider is planned for a later round")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def chat(self, api_key: str, model: str, system_context: str, user_message: str) -> dict[str, Any]:
        raise NotImplementedError("Gemini provider is planned for a later round")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def chat(self, api_key: str, model: str, system_context: str, user_message: str) -> dict[str, Any]:
        raise NotImplementedError("Ollama provider is planned for a later round")


PROVIDERS: dict[str, LLMProvider] = {
    p.name: p
    for p in (
        OpenRouterProvider(),
        DemoProvider(),
        OpenAIProvider(),
        AnthropicProvider(),
        GeminiProvider(),
        OllamaProvider(),
    )
}


def get_provider(name: str) -> LLMProvider:
    try:
        return PROVIDERS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown provider '{name}'") from None
