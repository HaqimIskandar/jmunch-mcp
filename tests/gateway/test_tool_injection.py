"""Tool injection converts MCP jmunch.* schemas into OpenAI / Anthropic shapes
and respects the auto / always / never policy. Pure unit tests — no network,
no aiohttp."""
from __future__ import annotations

from jmunch_mcp.gateway.tool_injection import (
    anthropic_tools,
    inject_into_anthropic_request,
    inject_into_openai_request,
    is_jmunch_gateway_tool,
    openai_tools,
    should_inject,
    to_mcp_name,
)
from jmunch_mcp.verbs import TOOL_SCHEMAS


def test_openai_tools_match_mcp_verb_set():
    names = {t["function"]["name"] for t in openai_tools()}
    expected = {s["name"].replace(".", "_") for s in TOOL_SCHEMAS}
    assert names == expected


def test_anthropic_tools_match_mcp_verb_set():
    names = {t["name"] for t in anthropic_tools()}
    expected = {s["name"].replace(".", "_") for s in TOOL_SCHEMAS}
    assert names == expected


def test_name_roundtrip():
    for s in TOOL_SCHEMAS:
        gw = s["name"].replace(".", "_")
        assert is_jmunch_gateway_tool(gw)
        assert to_mcp_name(gw) == s["name"]


def test_should_inject_policy():
    # auto: only when tools present
    assert should_inject([{"type": "function"}], "auto") is True
    assert should_inject([], "auto") is False
    assert should_inject(None, "auto") is False
    # always: always
    assert should_inject([], "always") is True
    assert should_inject(None, "always") is True
    # never: never
    assert should_inject([{"type": "function"}], "never") is False


def test_openai_injection_auto_no_existing_tools_skips():
    req = {"model": "gpt-4", "messages": []}
    out = inject_into_openai_request(req, mode="auto")
    assert "tools" not in out


def test_openai_injection_auto_appends():
    app_tool = {"type": "function", "function": {"name": "my_tool", "description": "x", "parameters": {}}}
    req = {"model": "gpt-4", "messages": [], "tools": [app_tool]}
    out = inject_into_openai_request(req, mode="auto")
    names = [t["function"]["name"] for t in out["tools"]]
    assert "my_tool" in names
    assert "jmunch_peek" in names
    assert len(out["tools"]) == 1 + len(TOOL_SCHEMAS)


def test_openai_injection_idempotent():
    req = {"model": "gpt-4", "messages": [], "tools": []}
    once = inject_into_openai_request(req, mode="always")
    twice = inject_into_openai_request(once, mode="always")
    assert len(once["tools"]) == len(twice["tools"])


def test_anthropic_injection_always():
    req = {"model": "claude-opus", "messages": []}
    out = inject_into_anthropic_request(req, mode="always")
    names = [t["name"] for t in out["tools"]]
    assert "jmunch_slice" in names


def test_openai_tool_name_shape_is_api_safe():
    # OpenAI allows ^[a-zA-Z0-9_-]{1,64}$ — no dots, no spaces.
    import re
    pat = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    for t in openai_tools():
        assert pat.match(t["function"]["name"]), t["function"]["name"]
