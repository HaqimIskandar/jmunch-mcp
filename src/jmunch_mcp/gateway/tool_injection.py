"""Convert jmunch MCP tool schemas into the OpenAI / Anthropic request shapes.

MCP names contain dots (`jmunch.peek`) but OpenAI/Anthropic function names
must match `^[a-zA-Z0-9_-]{1,64}$` — so we map `jmunch.peek` ↔ `jmunch_peek`.
The reverse map lets us dispatch tool_calls back through the MCP-shaped
Dispatcher unchanged (jMRI: single verb set, single dispatcher).
"""
from __future__ import annotations

import copy
from typing import Any

from ..verbs import TOOL_SCHEMAS


def _gateway_name(mcp_name: str) -> str:
    return mcp_name.replace(".", "_")


_GATEWAY_TO_MCP: dict[str, str] = {_gateway_name(s["name"]): s["name"] for s in TOOL_SCHEMAS}
_GATEWAY_TOOL_NAMES = frozenset(_GATEWAY_TO_MCP.keys())


def is_jmunch_gateway_tool(name: str) -> bool:
    return name in _GATEWAY_TOOL_NAMES


def to_mcp_name(gateway_name: str) -> str | None:
    return _GATEWAY_TO_MCP.get(gateway_name)


def openai_tools() -> list[dict[str, Any]]:
    """jmunch verb schemas in OpenAI's `{type:"function", function:{...}}` shape."""
    out: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        out.append({
            "type": "function",
            "function": {
                "name": _gateway_name(schema["name"]),
                "description": schema["description"],
                "parameters": copy.deepcopy(schema["inputSchema"]),
            },
        })
    return out


def anthropic_tools() -> list[dict[str, Any]]:
    """jmunch verb schemas in Anthropic's flat `{name, description, input_schema}` shape."""
    out: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        out.append({
            "name": _gateway_name(schema["name"]),
            "description": schema["description"],
            "input_schema": copy.deepcopy(schema["inputSchema"]),
        })
    return out


def should_inject(request_tools: list[Any] | None, mode: str) -> bool:
    """Policy: 'always' always injects, 'never' never, 'auto' only when the
    request already declares a non-empty tools array (the app is doing
    tool-calling — safe to add more)."""
    if mode == "never":
        return False
    if mode == "always":
        return True
    # auto
    return bool(request_tools)


def inject_into_openai_request(req: dict[str, Any], *, mode: str = "auto") -> dict[str, Any]:
    """Return a shallow copy of the request with jmunch tools appended to `tools`.

    Idempotent: a tool whose name already exists in the request is not duplicated.
    """
    existing = req.get("tools")
    if not should_inject(existing if isinstance(existing, list) else None, mode):
        return req

    merged = list(existing) if isinstance(existing, list) else []
    have_names = {
        t.get("function", {}).get("name") for t in merged if isinstance(t, dict)
    }
    for jt in openai_tools():
        if jt["function"]["name"] not in have_names:
            merged.append(jt)

    out = dict(req)
    out["tools"] = merged
    return out


def inject_into_anthropic_request(req: dict[str, Any], *, mode: str = "auto") -> dict[str, Any]:
    existing = req.get("tools")
    if not should_inject(existing if isinstance(existing, list) else None, mode):
        return req

    merged = list(existing) if isinstance(existing, list) else []
    have_names = {t.get("name") for t in merged if isinstance(t, dict)}
    for jt in anthropic_tools():
        if jt["name"] not in have_names:
            merged.append(jt)

    out = dict(req)
    out["tools"] = merged
    return out
