from __future__ import annotations

import json
from typing import Any

import httpx

from .config import OLLAMA_BASE_URL, OLLAMA_MODEL, SYSTEM_PERSONA


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]] | None = None,
        memory_block: str = "",
    ) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PERSONA},
        ]
        if memory_block:
            messages.append({"role": "system", "content": memory_block})
        for item in history or []:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_message})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.6},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise RuntimeError("Ollama boş cevap döndü.")
        return content


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
