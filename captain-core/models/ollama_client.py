import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from config import settings

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def is_running(self) -> bool:
        try:
            r = await self._http.get("/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    async def list_local(self) -> list[dict]:
        r = await self._http.get("/api/tags")
        r.raise_for_status()
        return r.json().get("models", [])

    async def pull(self, model_name: str) -> AsyncGenerator[dict, None]:
        """Stream download progress. Yields dicts: {status, completed, total}."""
        async with self._http.stream(
            "POST", "/api/pull", json={"name": model_name}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    yield json.loads(line)

    async def delete(self, model_name: str) -> None:
        r = await self._http.delete("/api/delete", json={"name": model_name})
        r.raise_for_status()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion. Yields text tokens."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools

        async with self._http.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                if chunk.get("done"):
                    return
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

    async def chat_complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Non-streaming completion, returns full response dict."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools
        r = await self._http.post("/api/chat", json=payload, timeout=60.0)
        r.raise_for_status()
        return r.json()

    async def embed(self, model: str, text: str) -> list[float]:
        """Generate text embedding vector."""
        r = await self._http.post(
            "/api/embeddings", json={"model": model, "prompt": text}, timeout=30.0
        )
        r.raise_for_status()
        return r.json()["embedding"]

    async def ensure_model_loaded(self, model_name: str) -> bool:
        """Pull model if not present locally."""
        local = await self.list_local()
        local_names = [m["name"] for m in local]
        if model_name in local_names:
            return True
        log.info(f"Model {model_name} not found locally — pulling...")
        async for chunk in self.pull(model_name):
            pass  # caller should stream progress separately
        return True

    async def benchmark(self, model_name: str) -> float:
        """Returns tokens/second for the model."""
        prompt = "Explain the concept of recursion in programming in one paragraph."
        start = time.time()
        tokens = 0
        messages = [{"role": "user", "content": prompt}]
        async for _ in self.chat(model_name, messages, max_tokens=100):
            tokens += 1
        elapsed = time.time() - start
        return round(tokens / elapsed, 1) if elapsed > 0 else 0.0

    async def close(self) -> None:
        await self._http.aclose()
