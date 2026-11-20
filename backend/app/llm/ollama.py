"""Thin async client for the Ollama HTTP API (chat, embeddings, model listing)."""

from __future__ import annotations

import json
from asyncio import gather
from collections.abc import AsyncIterator, Callable

import httpx


def model_tag(name: str) -> str:
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout: float = 300,
        context_size: int = 8192,
    ):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.context_size = context_size
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, trust_env=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def is_available(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get("/api/tags", timeout=5)
            r.raise_for_status()
            return [
                m["name"]
                for m in r.json().get("models", [])
                if not (m.get("remote_host") or m.get("remote_model"))
            ]
        except httpx.HTTPError:
            return []

    async def _supports_completion(self, name: str) -> bool:
        try:
            response = await self._client.post("/api/show", json={"model": name}, timeout=5)
            response.raise_for_status()
            return "completion" in response.json().get("capabilities", [])
        except httpx.HTTPError:
            return False

    async def list_chat_models(self) -> list[str]:
        models = sorted(await self.list_models())
        supported = await gather(*(self._supports_completion(name) for name in models))
        return [name for name, can_chat in zip(models, supported, strict=True) if can_chat]

    async def has_chat_model(self, name: str) -> bool:
        matching = next((tag for tag in await self.list_models() if model_tag(tag) == name), None)
        return matching is not None and await self._supports_completion(matching)

    async def running_models(self) -> list[dict]:
        try:
            response = await self._client.get("/api/ps", timeout=3)
            response.raise_for_status()
            return [
                {
                    "name": item["name"],
                    "size": item.get("size", 0),
                    "size_vram": item.get("size_vram", 0),
                }
                for item in response.json().get("models", [])
            ]
        except httpx.HTTPError:
            return []

    async def pull_model(self, name: str, progress: Callable[[float], None]) -> None:
        layers: dict[str, tuple[int, int]] = {}
        last = -1
        async with self._client.stream("POST", "/api/pull", json={"model": name}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                item = json.loads(line)
                if item.get("error"):
                    raise RuntimeError(str(item["error"]))
                if item.get("status") == "success":
                    return
                if item.get("digest") and item.get("total"):
                    layers[item["digest"]] = (item.get("completed", 0), item["total"])
                    total = sum(size for _, size in layers.values())
                    pct = min(99, int(100 * sum(done for done, _ in layers.values()) / total))
                    if pct > last:
                        progress(pct / 100)
                        last = pct
        raise RuntimeError("Ollama ended the download before confirming success.")

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict | None = None,
        *,
        think: bool | None = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": self.context_size, **(options or {})},
        }
        if think is not None:
            payload["think"] = think
        async with self._client.stream("POST", "/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise ValueError(str(data["error"]))
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    return
        raise ValueError("Ollama stopped before confirming the answer was complete.")

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        options: dict | None = None,
        *,
        think: bool | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        parts = [
            token
            async for token in self.chat_stream(messages, model=model, options=options, think=think)
        ]
        return "".join(parts).strip()

    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        r = await self._client.post(
            "/api/embed", json={"model": model or self.embed_model, "input": texts}
        )
        r.raise_for_status()
        return r.json()["embeddings"]
