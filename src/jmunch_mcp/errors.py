"""jMRI-shaped structured errors.

jMRI spec codes plus jmunch-mcp extensions:
    HANDLE_EXPIRED  — LRU-evicted; agent should re-fetch from upstream
    NOT_APPLICABLE  — verb called on a backend that doesn't support it
    UPSTREAM_ERROR  — upstream MCP returned an error we're surfacing
"""
from __future__ import annotations

from typing import Any


# Spec codes
NOT_FOUND = "NOT_FOUND"
NOT_INDEXED = "NOT_INDEXED"
STALE_ID = "STALE_ID"
INVALID_ID = "INVALID_ID"
INVALID_REPO = "INVALID_REPO"
INDEX_ERROR = "INDEX_ERROR"

# jmunch extensions
HANDLE_EXPIRED = "HANDLE_EXPIRED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UPSTREAM_ERROR = "UPSTREAM_ERROR"
INVALID_ARGS = "INVALID_ARGS"


def make_error(code: str, message: str, **detail: Any) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if detail:
        err["detail"] = detail
    return err
