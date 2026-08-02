"""LLM provider adapters for StateJar.

Every provider implements the same two calls:

    chat(api_key, model, system_context, user_message)
        -> {text, tokens_in, tokens_out, latency_ms, ...}
    list_models(api_key)
        -> [{id, name, context_length, is_free}]

`api_key` stays the leading argument rather than constructor state because
the registry below is a set of singletons and the key belongs to the request,
not the process. Chat results carry `text`/`tokens_in`/`tokens_out`/
`latency_ms` plus the older `content`/`model`/`usage`/`raw` keys, so existing
callers and the audit log keep working unchanged.

Errors are normalised: a failing call raises ProviderError with a message
written for the end user, and the key is scrubbed from it before it can reach
a response body or a log line.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import get_settings

_TIMEOUT = 60.0
_CATALOG_TIMEOUT = 20.0


class ProviderError(RuntimeError):
    """A provider call failed. The message is user-facing and key-free."""


class ProviderUnavailableError(ProviderError):
    """Provider endpoint could not be reached at all (wrong host, daemon down)."""


# --- error normalisation ------------------------------------------------------


def _redact(text: str, api_key: str | None) -> str:
    """Never let a credential ride out on an error message."""
    if not api_key:
        return text
    out = text.replace(api_key, "***")
    if len(api_key) > 8:  # partial echoes (e.g. a truncated key in a message)
        out = out.replace(api_key[:8], "***")
    return out


def _provider_message(response: httpx.Response) -> str:
    """Best-effort human message out of whatever shape the provider returned."""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 — html/plain error pages
        return response.text[:200].strip()
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, str):
            return err[:300]
        if isinstance(err, dict):
            for key in ("message", "detail", "description"):
                if isinstance(err.get(key), str):
                    return err[key][:300]
        if isinstance(body.get("message"), str):
            return body["message"][:300]
    return str(body)[:200]


def _check(response: httpx.Response, provider: str, model: str, api_key: str | None) -> None:
    """Raise a user-safe ProviderError for any non-2xx response."""
    if response.is_success:
        return
    detail = _redact(_provider_message(response), api_key)
    status = response.status_code

    if status in (401, 403):
        raise ProviderError(
            f"{provider} rejected the API key — check the key saved on the "
            f"API Keys page. ({detail})"
        )
    if status == 429:
        raise ProviderError(
            f"{provider} rate limit reached — wait a moment and try again. ({detail})"
        )
    if status in (400, 404) and re.search(r"model|not.?found|does not exist", detail, re.I):
        raise ProviderError(f"{provider} does not recognise the model '{model}'. ({detail})")
    raise ProviderError(f"{provider} error (HTTP {status}): {detail}")


def _request(
    method: str, url: str, provider: str, model: str, api_key: str | None, **kwargs: Any
) -> httpx.Response:
    try:
        response = httpx.request(method, url, **kwargs)
    except httpx.ConnectError as exc:
        raise ProviderUnavailableError(
            f"Could not reach {provider} at {httpx.URL(url).host} — check your connection."
        ) from exc
    except httpx.TimeoutException as exc:
        raise ProviderUnavailableError(f"{provider} timed out — try again.") from exc
    _check(response, provider, model, api_key)
    return response


def _result(
    text: str, model: str, tokens_in: int, tokens_out: int,
    latency_ms: int, raw: Any,
) -> dict[str, Any]:
    """The shared chat shape (new fields plus the legacy ones)."""
    return {
        "content": text,
        "text": text,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "usage": {
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
        "raw": raw,
    }


class LLMProvider(ABC):
    """A chat-completion capable provider."""

    name: str
    label: str

    @abstractmethod
    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        """Send one turn and return the shared result shape."""

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        """Live catalog: [{id, name, context_length, is_free}]."""
        return []


# --- OpenRouter ---------------------------------------------------------------


class OpenRouterProvider(LLMProvider):
    name = "openrouter"
    label = "OpenRouter"

    # Curated paid options shown next to the live free list, unchanged from
    # when OpenRouter was the only provider.
    CURATED_PAID = [
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o mini"},
        {"id": "anthropic/claude-sonnet-4.6", "name": "Claude Sonnet 4.6"},
        {"id": "anthropic/claude-haiku-4.5", "name": "Claude Haiku 4.5"},
        {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
    ]

    # The default endpoint, as a plain class attribute so it stays readable
    # off the class itself; `base_url` below is what requests actually use and
    # honours OPENROUTER_BASE_URL.
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, timeout: float = _TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return get_settings().openrouter_base_url.rstrip("/")

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
        started = time.perf_counter()
        response = _request(
            "POST", f"{self.base_url}/chat/completions", self.label, model, api_key,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=self._timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        usage = data.get("usage") or {}
        return _result(
            data["choices"][0]["message"]["content"],
            data.get("model", model),
            usage.get("prompt_tokens") or 0,
            usage.get("completion_tokens") or 0,
            latency_ms,
            data,
        )

    @staticmethod
    def _is_free_chat_model(m: dict[str, Any]) -> bool:
        pricing = m.get("pricing") or {}
        if pricing.get("prompt") != "0" or pricing.get("completion") != "0":
            return False
        # only text-out chat models: zero-priced media previews (music/image,
        # e.g. text+image->text+audio) would fail a chat completion call
        arch = m.get("architecture") or {}
        out = arch.get("output_modalities") or []
        modality = arch.get("modality") or ""
        return set(out) == {"text"} if out else modality.endswith("->text")

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        response = _request(
            "GET", f"{self.base_url}/models", self.label, "", api_key,
            headers={"Authorization": f"Bearer {api_key}"}, timeout=_CATALOG_TIMEOUT,
        )
        models = response.json().get("data") or []
        free = [m for m in models if self._is_free_chat_model(m)]
        free.sort(key=lambda m: m.get("context_length") or 0, reverse=True)
        out = [
            {
                "id": m["id"],
                "name": m.get("name") or m["id"],
                "context_length": m.get("context_length"),
                "is_free": True,
            }
            for m in free[:6]
        ]
        out.extend(
            {"id": p["id"], "name": p["name"], "context_length": None, "is_free": False}
            for p in self.CURATED_PAID
        )
        return out


# --- OpenAI -------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    name = "openai"
    label = "OpenAI"

    # /v1/models lists embeddings, audio, image and moderation models too;
    # only chat-completion ids belong in the picker.
    _CHAT_ID = re.compile(r"^(gpt-|o\d|chatgpt-)", re.IGNORECASE)
    _NOT_CHAT = re.compile(
        r"(embedding|whisper|tts|audio|realtime|image|dall-e|moderation|transcribe|search)",
        re.IGNORECASE,
    )

    def __init__(self, timeout: float = _TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return get_settings().openai_base_url.rstrip("/")

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
        started = time.perf_counter()
        response = _request(
            "POST", f"{self.base_url}/chat/completions", self.label, model, api_key,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=self._timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        usage = data.get("usage") or {}
        return _result(
            data["choices"][0]["message"]["content"],
            data.get("model", model),
            usage.get("prompt_tokens") or 0,
            usage.get("completion_tokens") or 0,
            latency_ms,
            data,
        )

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        response = _request(
            "GET", f"{self.base_url}/models", self.label, "", api_key,
            headers={"Authorization": f"Bearer {api_key}"}, timeout=_CATALOG_TIMEOUT,
        )
        ids = [m.get("id", "") for m in (response.json().get("data") or [])]
        chat_ids = sorted(
            i for i in ids if self._CHAT_ID.match(i) and not self._NOT_CHAT.search(i)
        )
        # OpenAI has no free tier, and /v1/models reports no context window
        return [
            {"id": i, "name": i, "context_length": None, "is_free": False}
            for i in chat_ids
        ]


# --- Anthropic ----------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    label = "Anthropic"

    API_VERSION = "2023-06-01"
    MAX_TOKENS = 1024  # required by the Messages API

    def __init__(self, timeout: float = _TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return get_settings().anthropic_base_url.rstrip("/")

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        # the system prompt is a top-level field here, not a message role
        payload = {
            "model": model,
            "max_tokens": self.MAX_TOKENS,
            "system": system_context,
            "messages": [{"role": "user", "content": user_message}],
        }
        started = time.perf_counter()
        response = _request(
            "POST", f"{self.base_url}/messages", self.label, model, api_key,
            json=payload, headers=self._headers(api_key), timeout=self._timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in (data.get("content") or [])
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return _result(
            text,
            data.get("model", model),
            usage.get("input_tokens") or 0,
            usage.get("output_tokens") or 0,
            latency_ms,
            data,
        )

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        response = _request(
            "GET", f"{self.base_url}/models", self.label, "", api_key,
            headers=self._headers(api_key), timeout=_CATALOG_TIMEOUT,
        )
        return [
            {
                "id": m["id"],
                "name": m.get("display_name") or m["id"],
                "context_length": m.get("context_window"),
                "is_free": False,
            }
            for m in (response.json().get("data") or [])
            if m.get("id")
        ]


# --- Gemini -------------------------------------------------------------------


class GeminiProvider(LLMProvider):
    name = "gemini"
    label = "Gemini"

    def __init__(self, timeout: float = _TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return get_settings().gemini_base_url.rstrip("/")

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        # header rather than ?key=… so the credential never lands in a URL,
        # an access log, or an error message built from one
        return {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        bare = model.removeprefix("models/")
        payload = {
            "system_instruction": {"parts": [{"text": system_context}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        }
        started = time.perf_counter()
        response = _request(
            "POST", f"{self.base_url}/models/{bare}:generateContent",
            self.label, model, api_key,
            json=payload, headers=self._headers(api_key), timeout=self._timeout,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") if candidates else []
        text = "".join(p.get("text", "") for p in (parts or []))
        usage = data.get("usageMetadata") or {}
        return _result(
            text,
            data.get("modelVersion") or bare,
            usage.get("promptTokenCount") or 0,
            usage.get("candidatesTokenCount") or 0,
            latency_ms,
            data,
        )

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        response = _request(
            "GET", f"{self.base_url}/models", self.label, "", api_key,
            headers=self._headers(api_key), timeout=_CATALOG_TIMEOUT,
        )
        out = []
        for m in response.json().get("models") or []:
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            bare = str(m.get("name", "")).removeprefix("models/")
            if not bare:
                continue
            out.append({
                "id": bare,
                "name": m.get("displayName") or bare,
                "context_length": m.get("inputTokenLimit"),
                "is_free": False,
            })
        return out


# --- Ollama -------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """A locally running Ollama daemon — no API key, no network egress.

    Keeps the shared signature, but the leading argument is read as an
    optional base-URL override rather than a credential: the API Keys page
    lets a user point StateJar at their own daemon, and that value is stored
    in the same per-provider row everything else uses.
    """

    name = "ollama"
    label = "Ollama (local)"

    def __init__(self, timeout: float = _TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        # read per call so a redeploy / test can repoint the daemon
        return get_settings().ollama_base_url.rstrip("/")

    @staticmethod
    def parse_config(stored: str | None) -> tuple[str, str]:
        """(base_url_override, api_key) from whatever is saved for this user.

        Ollama needs two values where every other provider needs one, so the
        row holds a small JSON document. A bare string is still accepted and
        read as a base URL, which is what earlier versions stored.
        """
        raw = (stored or "").strip()
        if not raw:
            return "", ""
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return "", ""
            if isinstance(parsed, dict):
                return (
                    str(parsed.get("base_url") or "").strip(),
                    str(parsed.get("api_key") or "").strip(),
                )
            return "", ""
        return raw, ""

    def _resolve_base(self, override: str | None) -> str:
        candidate, _ = self.parse_config(override)
        candidate = candidate.rstrip("/")
        return candidate if candidate.startswith(("http://", "https://")) else self.base_url

    def _headers(self, stored: str | None) -> dict[str, str]:
        """A remote/cloud Ollama can require a bearer token; a local one never does."""
        _, api_key = self.parse_config(stored)
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def chat(
        self, api_key: str, model: str, system_context: str, user_message: str
    ) -> dict[str, Any]:
        base_url = self._resolve_base(api_key)
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
                f"{base_url}/api/chat", json=payload,
                headers=self._headers(api_key), timeout=self._timeout,
            )
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                f"Ollama not reachable at {base_url} — is `ollama serve` running?"
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        _check(response, self.label, model, None)
        data = response.json()

        text = (data.get("message") or {}).get("content", "")
        return _result(
            text,
            data.get("model") or model,
            data.get("prompt_eval_count") or 0,
            data.get("eval_count") or 0,
            latency_ms,
            data,
        )

    def list_models(self, api_key: str) -> list[dict[str, Any]]:
        base_url = self._resolve_base(api_key)
        try:
            response = httpx.get(
                f"{base_url}/api/tags", headers=self._headers(api_key),
                timeout=_CATALOG_TIMEOUT,
            )
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                f"Ollama not reachable at {base_url} — is `ollama serve` running?"
            ) from exc
        _check(response, self.label, "", None)
        return [
            {
                "id": m["name"],
                "name": m["name"],
                "context_length": None,
                "is_free": True,  # local inference costs nothing
            }
            for m in (response.json().get("models") or [])
            if m.get("name")
        ]


# --- demo ---------------------------------------------------------------------


class DemoProvider(LLMProvider):
    """Scripted assistant for the playground's instant demo.

    Needs no API key and makes no network calls; replies are canned per
    demo step. The memory pipeline around it (ingest, retrieval, audit)
    still runs for real — only this reply is scripted.
    """

    name = "demo"
    label = "Demo"

    _SCRIPT = [
        ("pricing section", "Pricing section added — same React + Tailwind, dark, "
                            "#E07856, no external UI libraries."),
        ("brand color", "Updated. The previous value is preserved in history, "
                        "not overwritten."),
        ("shadcn", "Noted — that contradicts your earlier 'no external UI libraries' "
                   "constraint. I've kept both, flagged as a conflict."),
        ("stack", "Landing page scaffolded — React + Tailwind, dark theme, "
                  "#E07856 accents."),
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

# Providers a user can save a key for (demo is internal).
KEYED_PROVIDERS: tuple[str, ...] = ("openrouter", "openai", "anthropic", "gemini", "ollama")

# Providers reachable without a credential.
KEYLESS_PROVIDERS: frozenset[str] = frozenset({"ollama", "demo"})


def get_provider(name: str) -> LLMProvider:
    try:
        return PROVIDERS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown provider '{name}'") from None


def provider_label(name: str) -> str:
    provider = PROVIDERS.get(name.lower())
    return provider.label if provider else name
