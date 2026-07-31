"""LLM provider adapters for StateJar.

OpenRouter (hosted, BYOK) and Ollama (local, keyless) are implemented; the
remaining providers are placeholders so the gateway's registry stays
extensible.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import get_settings


class ProviderUnavailableError(RuntimeError):
    """Provider endpoint could not be reached.

    The message is written for the end user and is surfaced verbatim by the
    /chat route, so it must stay actionable.
    """


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
    """A locally running Ollama daemon — no API key, no network egress.

    Keeps the shared provider signature (the leading `api_key` is accepted
    and ignored) so the gateway registry needs no special-casing. The
    returned dict is a superset of the shared shape: `content`/`model`/
    `usage`/`raw` for existing callers, plus the `text`/`tokens_in`/
    `tokens_out`/`latency_ms` fields.
    """

    name = "ollama"

    def __init__(self, timeout: float = 60.0) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        # read per call so a redeploy / test can repoint the daemon
        return get_settings().ollama_base_url.rstrip("/")

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        base_url = self.base_url
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_context},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{base_url}/api/chat", json=payload, timeout=self._timeout
            )
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                f"Ollama not reachable at {base_url} — is `ollama serve` running?"
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        data = response.json()

        text = (data.get("message") or {}).get("content", "")
        tokens_in = data.get("prompt_eval_count") or 0
        tokens_out = data.get("eval_count") or 0
        return {
            "content": text,
            "text": text,
            "model": data.get("model") or model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "usage": {
                "prompt_tokens": tokens_in,
                "completion_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
            },
            "raw": data,
        }


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
