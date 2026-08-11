from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    SYSTEM_PERSONA,
)


@dataclass
class AiStatus:
    available: bool
    provider: str
    model: str


class AiClient:
    """AI backend: OpenAI-compatible API preferred, else local Ollama."""

    def __init__(self) -> None:
        self.timeout = 90.0

    async def status(self) -> AiStatus:
        if OPENAI_API_KEY:
            return AiStatus(True, "openai", OPENAI_MODEL)
        if await self._ollama_up():
            return AiStatus(True, "ollama", OLLAMA_MODEL)
        return AiStatus(False, "none", OLLAMA_MODEL)

    async def available(self) -> bool:
        return (await self.status()).available

    async def _ollama_up(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]] | None = None,
        memory_block: str = "",
        intent: str = "chat",
    ) -> tuple[str, str]:
        """Returns (reply, provider)."""
        status = await self.status()
        if not status.available:
            raise RuntimeError("AI backend unavailable")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PERSONA},
            {
                "role": "system",
                "content": (
                    f"Kullanıcı niyeti: {intent}. "
                    "Yanıtını Türkçe ver. Yatırım tavsiyesi verme."
                ),
            },
        ]
        if memory_block:
            messages.append({"role": "system", "content": memory_block})
        for item in history or []:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_message})

        if status.provider == "openai":
            content = await self._openai_chat(messages, status.model)
            return content, "openai"
        content = await self._ollama_chat(messages, status.model)
        return content, "ollama"

    async def _openai_chat(self, messages: list[dict[str, str]], model: str) -> str:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.5,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI boş cevap döndü.")
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("OpenAI boş cevap döndü.")
        return content

    async def _ollama_chat(self, messages: list[dict[str, str]], model: str) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.5},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = ((data.get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Ollama boş cevap döndü.")
        return content


# Backward-compatible name
OllamaClient = AiClient


def append_training_example(path, user: str, assistant: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
