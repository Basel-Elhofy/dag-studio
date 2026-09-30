"""LLM provider abstraction.

The studio works out of the box with a deterministic mock provider that
plans and generates code locally. Set LLM_PROVIDER=openai (and OPENAI_API_KEY,
optionally OPENAI_BASE_URL / OPENAI_MODEL) to route through any
OpenAI-compatible chat-completions endpoint.
"""
from __future__ import annotations

import json
import os
import random
from typing import Any

from . import codegen

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class LLMProvider:
    name = "base"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str:
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Deterministic-ish local provider used for the zero-config demo."""

    name = "mock"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str:
        import asyncio

        await asyncio.sleep(random.uniform(0.15, 0.45))
        prompt = messages[-1]["content"] if messages else ""

        if json_mode:
            return json.dumps(codegen.plan_from_prompt(prompt), indent=2)
        return codegen.explain_task(prompt)


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible chat completions (works with OpenAI, Ollama, etc.)."""

    name = "openai"

    def __init__(self) -> None:
        import httpx  # local import: only needed for this provider

        self._httpx = httpx
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = DEFAULT_MODEL

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with self._httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]


def get_provider() -> LLMProvider:
    if os.environ.get("LLM_PROVIDER", "mock").lower() == "openai":
        return OpenAIProvider()
    return MockProvider()
