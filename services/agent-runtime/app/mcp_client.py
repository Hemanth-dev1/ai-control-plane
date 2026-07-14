"""MCP client for the agent runtime — calls tools via the MCP protocol over SSE.

Connects to the tool gateway's MCP SSE endpoint (http://tool-gateway:8002/mcp/sse),
lists available tools, and calls them by name with typed arguments.
Uses the official `mcp` SDK's ClientSession with SSE transport.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from opentelemetry import trace

from app.config import settings

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MCPClient:
    """MCP client that connects to the tool gateway via MCP SSE protocol.

    Uses the MCP SDK's ClientSession over SSE transport (Server-Sent Events).
    Connects to the gateway's /mcp/sse endpoint where the FastMCP server is mounted.
    """

    def __init__(self, gateway_url: str | None = None):
        self.gateway_url = (gateway_url or settings.tool_gateway_url).rstrip("/")
        self._sse_url = f"{self.gateway_url}/mcp/sse"
        self._session: ClientSession | None = None
        self._tool_cache: list[dict[str, Any]] | None = None

    @asynccontextmanager
    async def _session_context(self) -> AsyncIterator[ClientSession]:
        """Create an MCP client session connected via SSE transport."""
        async with sse_client(url=self._sse_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools from the MCP server.

        Returns tool definitions compatible with ToolSchema format.
        Results are cached for the lifetime of this client instance.
        """
        if self._tool_cache is not None:
            return self._tool_cache

        try:
            async with self._session_context() as session:
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema or {},
                        "backend_service": tool.name.split(".")[0] + "-service"
                        if "." in tool.name else "unknown",
                    })
                self._tool_cache = tools
                return tools
        except Exception as e:
            logger.warning("mcp_list_tools_failed, falling back to REST", error=str(e))
            return await self._list_tools_rest()

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the MCP server via SSE.

        Args:
            tool_name: Fully-qualified tool name (e.g., crm.lookup_customer).
            arguments: Tool arguments as a dict.

        Returns:
            Result dict with keys: success (bool), data/error.
        """
        with tracer.start_as_current_span("mcp_call_tool") as span:
            span.set_attribute("tool_name", tool_name)

            try:
                async with self._session_context() as session:
                    result = await session.call_tool(tool_name, arguments)

                    # Extract text content from the MCP result
                    content_text = ""
                    if hasattr(result, "content") and result.content:
                        for item in result.content:
                            if hasattr(item, "text"):
                                content_text += item.text
                            elif isinstance(item, dict) and item.get("type") == "text":
                                content_text += item.get("text", "")

                    if content_text.startswith("Error:"):
                        return {"success": False, "error": content_text[7:].strip()}

                    # Try to parse result as JSON
                    try:
                        parsed = json.loads(content_text)
                        if isinstance(parsed, dict):
                            return {"success": True, "data": parsed}
                        return {"success": True, "data": {"result": parsed}}
                    except (json.JSONDecodeError, TypeError):
                        return {"success": True, "data": {"result": content_text}}

            except Exception as e:
                logger.warning("mcp_call_failed, falling back to REST", tool=tool_name, error=str(e))
                return await self._call_tool_rest(tool_name, arguments)

    async def _list_tools_rest(self) -> list[dict[str, Any]]:
        """Fallback: fetch tools via REST API."""
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.gateway_url}/tools")
            response.raise_for_status()
            return response.json()

    async def _call_tool_rest(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Fallback: call a tool via REST API."""
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.gateway_url}/execute",
                json={"tool_name": tool_name, "arguments": arguments},
            )
            if response.is_success:
                return response.json()
            return {
                "success": False,
                "error": f"Gateway returned {response.status_code}: {response.text}",
            }

    async def close(self) -> None:
        """Close and clear cache."""
        self._session = None
        self._tool_cache = None
