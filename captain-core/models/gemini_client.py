"""
Google Gemini client using the OpenAI-compatible REST endpoint.

No new SDK needed — Gemini exposes:
  POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions

Message format is identical to OpenAI / the format Ollama already uses,
so _llm_tool_loop can call either backend transparently.
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from config import settings

log = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"

# Prefer the fastest capable model; user can override via GEMINI_MODEL env var
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiClient:

    def _api_key(self) -> str:
        """Keychain (set via Accounts & Connections) takes priority over .env."""
        try:
            from security.keychain import keychain
            kc = keychain.retrieve("gemini_api_key")
            if kc:
                return kc
        except Exception:
            pass
        return settings.gemini_api_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    async def is_configured(self) -> bool:
        return bool(self._api_key())

    async def chat_complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Non-streaming chat completion with automatic 429 retry.
        Returns an Ollama-compatible response dict:
          {"message": {"role": "assistant", "content": "...", "tool_calls": [...]}}
        """
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "required"  # force the model to call a tool

        last_err = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(
                        f"{GEMINI_BASE}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                if r.status_code == 429:
                    wait = 5 * (attempt + 1)
                    log.warning(f"Gemini 429 rate limit — waiting {wait}s (attempt {attempt+1}/3)")
                    await asyncio.sleep(wait)
                    last_err = httpx.HTTPStatusError("429", request=r.request, response=r)
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 5 * (attempt + 1)
                    log.warning(f"Gemini 429 — waiting {wait}s (attempt {attempt+1}/3)")
                    await asyncio.sleep(wait)
                    last_err = e
                    continue
                raise
        else:
            raise last_err

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        # Normalise tool_calls to Ollama format
        raw_tool_calls = msg.get("tool_calls") or []
        ollama_tool_calls = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            ollama_tool_calls.append({
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": args,
                }
            })

        return {
            "message": {
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": ollama_tool_calls,
            }
        }

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat — yields text tokens."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{GEMINI_BASE}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload_str = line[6:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload_str)
                        delta = chunk["choices"][0]["delta"]
                        text = delta.get("content") or ""
                        if text:
                            yield text
                    except Exception:
                        continue

    async def list_models(self) -> list[str]:
        """Return available Gemini model IDs."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{GEMINI_BASE}/models",
                headers=self._headers(),
            )
            if r.status_code != 200:
                return [DEFAULT_MODEL]
            data = r.json()
            return [m["id"] for m in data.get("data", [])]


gemini_client = GeminiClient()
