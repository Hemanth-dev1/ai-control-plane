"""LLM client wrapping the Anthropic Messages API."""

from __future__ import annotations

from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from app.config import settings


class LLMClient:
    """Client for the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None):
        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise ValueError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable."
            )
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = settings.llm_model

    async def send_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to the LLM and return the response."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = tools

        response = await self.client.messages.create(**kwargs)

        return self._format_response(response)

    def _format_response(self, response) -> dict[str, Any]:
        """Format the Anthropic response into a standard dict."""
        result = {
            "id": response.id,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "content": [],
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        }

        for block in response.content:
            if block.type == "text":
                result["content"].append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                result["content"].append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return result

    @staticmethod
    def convert_tool_schema_to_anthropic(tool_schema: dict[str, Any]) -> dict[str, Any]:
        """Convert a tool schema to Anthropic's tool format."""
        return {
            "name": tool_schema["name"],
            "description": tool_schema.get("description", ""),
            "input_schema": tool_schema.get("input_schema", {"type": "object", "properties": {}}),
        }
