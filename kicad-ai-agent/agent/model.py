import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import httpx


@dataclass
class ModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 4096


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ModelClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self.conversation_history: list[dict[str, str]] = []

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Send messages to the model with optional tool definitions."""
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
