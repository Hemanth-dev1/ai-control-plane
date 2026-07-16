# Resona LangGraph Agent Integration

This document describes how a [LangGraph](https://langchain-ai.github.io/langgraph/) agent (the **Resona** project) connects to the AI Control Plane's tool gateway, instead of calling tool functions in-process.

## Why This Matters

The AI Control Plane governs **every tool call** made by an AI agent — policy enforcement (via OPA), audit logging (via Kafka), schema validation, and rate limiting. A LangGraph agent that calls tools through the gateway is provably governed, unlike one that calls tools directly in-process.

This integration proves the control plane governs a **real agent**, not just a synthetic `curl` demo.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Resona (LangGraph Agent)                      │
│                                                                      │
│   ┌──────────────┐    1. Get JWT       ┌──────────────────┐         │
│   │   Auth Node   │ ──────────────────▶│ /auth/token       │         │
│   └──────────────┘                     │ (control-plane)   │         │
│         │                              └──────────────────┘         │
│         ▼                                                            │
│   ┌────────────────┐   2. Check Policy  ┌──────────────────┐         │
│   │  Policy Node   │ ──────────────────▶│ /policy/check     │         │
│   └────────────────┘                    │ (control-plane)   │         │
│         │                               └──────────────────┘         │
│         ▼                                                            │
│   ┌────────────────┐   3. Call Tool     ┌──────────────────┐         │
│   │  Tool Node     │ ──────────────────▶│ /execute          │         │
│   └────────────────┘                    │ (tool-gateway)    │         │
│                                         └──────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
```

## What Changed on the Resona Side

A standard LangGraph agent defines tool-calling nodes that invoke Python functions directly:

```python
# ❌ Before: direct in-process tool call (ungoverned)
tools = [lookup_customer, create_ticket]
```

**Instead**, each tool-calling node in the Resona graph makes **three HTTP calls**:

1. **`POST /auth/token`** — obtain a JWT
2. **`POST /policy/check`** — verify the tool call is allowed
3. **`POST /execute`** — execute the tool through the gateway

### Node: `auth_node`

Authenticates the agent with the control plane and caches the JWT for the duration of the run. Returns the updated state so LangGraph can pass the token downstream.

```python
import httpx

async def auth_node(state: AgentState) -> AgentState:
    """Obtain a JWT token from the control plane."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://control-plane:8000/auth/token",
            data={
                "client_id": state["agent_name"],
                "client_secret": state["api_key"],
            },
        )
        resp.raise_for_status()
        token_data = resp.json()
    return {**state, "token": token_data["access_token"]}
```

### Node: `policy_node`

Checks whether a specific tool call is permitted before executing it. This is optional if you trust the agent — but recommended because it gives you an audit trail of *every* policy decision. Returns the full updated state with the policy decision attached.

```python
async def policy_node(state: AgentState, llm_tool_call: dict) -> AgentState:
    """Check policy before calling a tool."""
    tool_name = llm_tool_call["name"]
    tool_args = llm_tool_call.get("input", {})
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://control-plane:8000/policy/check",
            json={
                "agent_id": str(state["agent_id"]),
                "tool_name": tool_name,
                "arguments": tool_args,
                "request_id": state["run_id"],
            },
            headers={"Authorization": f"Bearer {state['token']}"},
        )
        resp.raise_for_status()
        decision = resp.json()
    return {
        **state,
        "current_tool": {"name": tool_name, "arguments": tool_args},
        "policy_allowed": decision["allowed"],
        "policy_reason": decision.get("reason", ""),
    }
```

### Node: `tool_node`

Calls the tool through the gateway instead of invoking a local function. Returns the updated state with the tool result.

```python
async def tool_node(state: AgentState) -> AgentState:
    """Execute a tool through the governed gateway."""
    tool_name = state["current_tool"]["name"]
    tool_args = state["current_tool"]["arguments"]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "http://tool-gateway:8002/execute",
            json={
                "tool_name": tool_name,
                "arguments": tool_args,
                "agent_id": str(state["agent_id"]),
                "run_id": state["run_id"],
            },
        )
        resp.raise_for_status()
        result = resp.json()
    return {**state, "tool_result": result}
```

## LangGraph Graph Definition

Here's how the Resona graph connects the nodes:

```python
from langgraph.graph import StateGraph, END

# Define the graph
graph = StateGraph(AgentState)

# Add nodes
graph.add_node("auth", auth_node)
graph.add_node("resolve_intent", llm_decide_node)   # LLM decides which tool to call
graph.add_node("check_policy", policy_check_node)    # Node that calls /policy/check
graph.add_node("execute_tool", gateway_tool_node)    # Node that calls /execute
graph.add_node("process_result", result_node)        # Process tool result

# Add edges
graph.set_entry_point("auth")
graph.add_edge("auth", "resolve_intent")
graph.add_conditional_edges(
    "resolve_intent",
    decide_next_step,  # Returns "call_tool" or "respond"
    {
        "call_tool": "check_policy",
        "respond": "process_result",
    },
)
graph.add_conditional_edges(
    "check_policy",
    policy_result_router,  # Reads state["policy_allowed"], returns "allowed" or "denied"
    {
        "allowed": "execute_tool",
        "denied": "resolve_intent",  # Let LLM try again or respond
    },
)
graph.add_edge("execute_tool", "resolve_intent")  # Loop back for next tool
graph.add_edge("process_result", END)
```

## Why Through the Gateway?

| Aspect | Direct Call | Gateway Call |
|--------|-----------|--------------|
| **Policy Enforcement** | None (manual) | OPA-powered, fail-closed |
| **Audit Trail** | None | Kafka `tool.invocations` topic |
| **Schema Validation** | Python assert | jsonschema, strict |
| **Rate Limiting** | None | Redis sliding window |
| **Discoverability** | Hard-coded | `GET /tools` returns all schemas |
| **MCP Compatibility** | No | Yes — `/mcp/sse` endpoint available |

## Verification

After integrating, verify the governed flow:

```bash
# 1. Register an agent
curl -s -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "resona-agent", "allowed_scopes": ["crm.lookup_customer", "ticketing.create_ticket"]}'

# 2. Run the Resona agent (pointed at this gateway)
# The agent should:
#   - Obtain a JWT from /auth/token
#   - Check policy via /policy/check
#   - Execute tools via /execute
#   - Produce audit events visible in Kafka

# 3. Verify audit log has policy decisions and tool invocations
# Check the audit consumer logs (reads from Kafka topics)
docker compose logs audit-consumer --tail 50 | grep '"topic":"tool.invocations"' || \
  echo "No tool invocations found yet — did the agent run?"
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `401` on `/auth/token` | Wrong `client_secret` | Re-register the agent to get a new API key |
| `403` on `/policy/check` | Tool not in `allowed_scopes` | Update agent registration with the required scope |
| `404` on `/execute` | Tool name doesn't match gateway schema | Run `curl localhost:8002/tools` to list valid names |
| Gateway returns `429` | Rate limit exceeded | Wait for the sliding window to reset (default: 100/hour) |

## Files Changed on the Resona Side

| File | Change |
|------|--------|
| `resona/graph/nodes/auth.py` | Added — HTTP call to `/auth/token` |
| `resona/graph/nodes/policy.py` | Added — HTTP call to `/policy/check` |
| `resona/graph/nodes/tools.py` | Changed — replaced `import lookup_customer` with `POST /execute` |
| `resona/graph/graph.py` | Changed — added `auth_node`, `policy_node` to the graph |
| `resona/.env` | Added — `CONTROL_PLANE_URL`, `TOOL_GATEWAY_URL`, `AGENT_API_KEY` |
