"""Content sniffer: classify an upstream payload so the dispatcher can route
it to the right backend. Heuristic, cheap, and deliberately conservative —
ambiguous shapes fall through to `UNKNOWN` (passthrough).

Inputs are already-parsed JSON values. We never re-parse the raw bytes here.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class Kind(str, Enum):
    TABULAR = "tabular"
    TEXT = "text"
    JSON = "json"
    UNKNOWN = "unknown"


# Minimum array length that qualifies as "tabular" (below this, it's just a
# small list and not worth handle-ifying).
_TABULAR_MIN_ROWS = 5

# Minimum text length (in characters) to classify as a text corpus; below this,
# strings pass through as normal.
_TEXT_MIN_CHARS = 1000


def classify(payload: Any) -> Kind:
    if isinstance(payload, list):
        if _is_tabular_array(payload):
            return Kind.TABULAR
        if len(payload) >= _TABULAR_MIN_ROWS:
            # Homogeneous scalar or mixed — treat as JSON tree.
            return Kind.JSON
        return Kind.UNKNOWN

    if isinstance(payload, dict):
        # Common MCP wrapper: {"items": [...]} or {"results": [...]} etc.
        inner = _unwrap_array(payload)
        if inner is not None and _is_tabular_array(inner):
            return Kind.TABULAR
        return Kind.JSON

    if isinstance(payload, str):
        return Kind.TEXT if len(payload) >= _TEXT_MIN_CHARS else Kind.UNKNOWN

    return Kind.UNKNOWN


def _is_tabular_array(arr: list[Any]) -> bool:
    if len(arr) < _TABULAR_MIN_ROWS:
        return False
    if not all(isinstance(row, dict) for row in arr):
        return False
    # Require at least some shared keys across rows (homogeneous-ish).
    first_keys = set(arr[0].keys())
    if not first_keys:
        return False
    shared = first_keys.copy()
    for row in arr[1:20]:  # sample
        shared &= set(row.keys())
        if not shared:
            return False
    return True


def _unwrap_array(obj: dict[str, Any]) -> list[Any] | None:
    """If a dict has exactly one array-valued field (or a conventional name),
    return it so we can test for tabularity."""
    for key in ("items", "results", "rows", "data", "records"):
        val = obj.get(key)
        if isinstance(val, list):
            return val
    array_fields = [v for v in obj.values() if isinstance(v, list)]
    if len(array_fields) == 1:
        return array_fields[0]
    return None


def extract_rows(payload: Any) -> list[dict[str, Any]] | None:
    """Return the row array for a payload classified as TABULAR, else None."""
    if isinstance(payload, list) and _is_tabular_array(payload):
        return payload
    if isinstance(payload, dict):
        arr = _unwrap_array(payload)
        if arr is not None and _is_tabular_array(arr):
            return arr
    return None
