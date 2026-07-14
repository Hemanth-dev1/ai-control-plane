"""The agent execution loop — orchestrates LLM calls, policy checks, and tool invocations."""

from __future__ import annotations

import time
import uuid
from typing import Any
from uuid import UUID, uuid4

import structlog
from opentelemetry import trace

from app.control_plane_client import ControlPlaneClient
from app.llm_client import LLMClient
from app.mcp_client import MCPClient
from shared_schemas.events import ExecutionEvent, ExecutionStep
from shared_schemas.policy import PolicyRequest
from shared_schemas.tool import ToolSchema

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# System prompt for the agent
SYSTEM_PROMPT = """You are an enterprise AI assistant with access to various backend systems.
You have tools available to help you complete tasks. For each task:
1. Use the appropriate tool when needed
2. Always verify customer information before taking actions
3. Report results clearly to the user

If a tool call is denied, explain to the user what happened and why."""


class AgentLoop:
    """Orchestrates the agent execution loop."""

    def __init__(
        self,
        agent_id: UUID,
        llm_client: LLMClient,
        control_plane: ControlPlaneClient,
        tool_gateway_url: str,
    ):
        self.agent_id = agent_id
        self.llm = llm_client
        self.control_plane = control_plane
        self.tool_gateway_url = tool_gateway_url.rstrip("/")
        self.run_id = uuid4()
        self.steps: list[ExecutionStep] = []
        self.start_time = time.time()

    async def run(self, prompt: str, max_iterations: int = 10) -> dict[str, Any]:
        """Execute the full agent loop for a given prompt."""
        with tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("run_id", str(self.run_id))
            span.set_attribute("agent_id", str(self.agent_id))
            span.set_attribute("prompt", prompt[:200])

            messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
            step_num = 0

            # Fetch available tools
            tool_schemas = await self._fetch_tools()
            anthropic_tools = [
                LLMClient.convert_tool_schema_to_anthropic(t.model_dump())
                for t in tool_schemas
            ]

            logger.info(
                "run_started",
                run_id=str(self.run_id),
                agent_id=str(self.agent_id),
                num_tools=len(tool_schemas),
            )

            self._add_step("llm_call", step_number=step_num, tokens_used=0)

            for iteration in range(max_iterations):
                step_num += 1

                # Call LLM
                step_start = time.time()
                response = await self.llm.send_message(
                    messages=messages,
                    tools=anthropic_tools,
                    system_prompt=SYSTEM_PROMPT,
                )
                llm_duration = (time.time() - step_start) * 1000

                tokens_used = response["usage"]["input_tokens"] + response["usage"]["output_tokens"]
                self._update_step(
                    step_number=step_num,
                    duration_ms=llm_duration,
                    tokens_used=tokens_used,
                    llm_response=response.get("content", [{}])[0].get("text", "")
                    if response.get("content")
                    else "",
                )

                # Add assistant response to messages
                messages.append({
                    "role": "assistant",
                    "content": response["content"],
                })

                # Check if model wants to use tools
                tool_blocks = [
                    block for block in response.get("content", [])
                    if block["type"] == "tool_use"
                ]

                if not tool_blocks:
                    # Model returned final text — done
                    self._add_step("llm_call", step_number=step_num + 1)
                    total_duration = (time.time() - self.start_time) * 1000
                    total_tokens = sum(
                        s.tokens_used or 0 for s in self.steps
                    )

                    logger.info(
                        "run_completed",
                        run_id=str(self.run_id),
                        total_steps=len(self.steps),
                        total_duration_ms=total_duration,
                    )

                    return {
                        "run_id": str(self.run_id),
                        "status": "completed",
                        "response": response["content"],
                        "steps": [s.model_dump() for s in self.steps],
                        "total_duration_ms": total_duration,
                        "total_tokens_used": total_tokens,
                    }

                # Process each tool call
                for tool_block in tool_blocks:
                    tool_name = tool_block["name"]
                    tool_args = tool_block.get("input", {})

                    # Step 1: Check policy
                    self._add_step(
                        "policy_check",
                        step_number=step_num,
                        tool_name=tool_name,
                        tool_arguments=tool_args,
                    )

                    policy_result = await self.control_plane.check_policy(
                        PolicyRequest(
                            agent_id=self.agent_id,
                            tool_name=tool_name,
                            arguments=tool_args,
                            request_id=str(self.run_id),
                        )
                    )

                    self._update_step(
                        step_number=step_num,
                        policy_allowed=policy_result.allowed,
                    )

                    if not policy_result.allowed:
                        logger.warning(
                            "tool_denied",
                            run_id=str(self.run_id),
                            tool_name=tool_name,
                            reason=policy_result.reason,
                        )
                        # Return denial to model
                        messages.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_block["id"],
                                    "content": f"Tool '{tool_name}' was denied: {policy_result.reason}",
                                }
                            ],
                        })

                        self._add_step(
                            "tool_result",
                            step_number=step_num,
                            tool_name=tool_name,
                            tool_result={"error": policy_result.reason, "denied": True},
                        )
                        continue

                    # Step 2: Execute tool
                    self._add_step(
                        "tool_call",
                        step_number=step_num,
                        tool_name=tool_name,
                        tool_arguments=tool_args,
                    )

                    tool_start = time.time()
                    tool_result = await self._execute_tool(tool_name, tool_args)
                    tool_duration = (time.time() - tool_start) * 1000

                    self._update_step(
                        step_number=step_num,
                        duration_ms=tool_duration,
                        tool_result=tool_result,
                    )

                    # Feed result back to model
                    if tool_result.get("success"):
                        content = str(tool_result.get("data", ""))
                    else:
                        content = f"Error: {tool_result.get('error', 'Unknown error')}"

                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_block["id"],
                                "content": content,
                            }
                        ],
                    })

            # If we exceed max_iterations
            total_duration = (time.time() - self.start_time) * 1000
            return {
                "run_id": str(self.run_id),
                "status": "max_iterations_reached",
                "response": "Maximum iterations reached without completion.",
                "steps": [s.model_dump() for s in self.steps],
                "total_duration_ms": total_duration,
                "total_tokens_used": sum(s.tokens_used or 0 for s in self.steps),
            }

    async def _fetch_tools(self) -> list[ToolSchema]:
        """Fetch available tools via MCP client."""
        mcp_client = MCPClient(gateway_url=self.tool_gateway_url)
        try:
            raw_tools = await mcp_client.list_tools()
            return [ToolSchema(**t) for t in raw_tools]
        finally:
            await mcp_client.close()

    async def _execute_tool(self, tool_name: str, arguments: dict) -> dict[str, Any]:
        """Execute a tool via the MCP client."""
        mcp_client = MCPClient(gateway_url=self.tool_gateway_url)
        try:
            return await mcp_client.call_tool(tool_name, arguments)
        finally:
            await mcp_client.close()

    def _add_step(
        self,
        step_type: str,
        step_number: int,
        tool_name: str | None = None,
        tool_arguments: dict | None = None,
        tool_result: dict | None = None,
        policy_allowed: bool | None = None,
    ):
        step = ExecutionStep(
            step_number=step_number,
            step_type=step_type,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            tool_result=tool_result,
            policy_allowed=policy_allowed,
        )
        self.steps.append(step)

    def _update_step(
        self,
        step_number: int,
        duration_ms: float | None = None,
        tokens_used: int | None = None,
        tool_name: str | None = None,
        tool_arguments: dict | None = None,
        tool_result: dict | None = None,
        policy_allowed: bool | None = None,
        llm_response: str | None = None,
        error: str | None = None,
    ):
        for step in self.steps:
            if step.step_number == step_number:
                if duration_ms is not None:
                    step.duration_ms = duration_ms
                if tokens_used is not None:
                    step.tokens_used = tokens_used
                if tool_name is not None:
                    step.tool_name = tool_name
                if tool_arguments is not None:
                    step.tool_arguments = tool_arguments
                if tool_result is not None:
                    step.tool_result = tool_result
                if policy_allowed is not None:
                    step.policy_allowed = policy_allowed
                if llm_response is not None:
                    step.llm_response = llm_response
                if error is not None:
                    step.error = error
                break
