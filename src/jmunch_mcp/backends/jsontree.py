"""JSON-tree backend: deeply-nested or heterogeneous JSON payloads.

Sits alongside TabularBackend. Chosen when the sniffer decides the payload
is dict-shaped (with no obvious row array) or a heterogeneous list. The
backend keeps the parsed tree in memory and answers verbs:

- peek(n)        → top-level shape preview (first n keys/items, values truncated)
- slice(selector)→ JSONPath query (minimal subset, see jmunch_mcp.jsonpath)
- search(query)  → substring match on keys + string values, returns paths
- describe()     → max depth, node counts by type, top-level keys
- aggregate()    → NOT_APPLICABLE

`peek` accepts where="head"|"tail" but they're equivalent for dicts; for
list roots, tail walks from the end.
"""
from __future__ import annotations

import json
from typing import Any

from ..errors import INVALID_ARGS, NOT_APPLICABLE, make_error
from ..jsonpath import JSONPathError, _walk, query as jpath_query

# Max chars to keep when previewing a scalar inside peek output.
_PREVIEW_VALUE_MAX = 80
# Hard cap on slice result size, defensively (on top of user's max_rows).
_SLICE_HARD_CAP = 500
# Hard cap on search result size.
_SEARCH_HARD_CAP = 200


class JSONBackend:
    kind = "json"

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self._size_bytes = len(json.dumps(payload, default=str))
        self._node_count, self._max_depth, self._type_counts = _scan(payload)

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def summary(self) -> dict[str, Any]:
        s = {
            "root_type": _type_of(self._payload),
            "size_bytes": self._size_bytes,
            "node_count": self._node_count,
            "max_depth": self._max_depth,
        }
        if isinstance(self._payload, dict):
            s["top_level_keys"] = list(self._payload.keys())[:20]
            s["top_level_key_count"] = len(self._payload)
        elif isinstance(self._payload, list):
            s["length"] = len(self._payload)
        return s

    def describe(self) -> dict[str, Any]:
        return {
            "root_type": _type_of(self._payload),
            "size_bytes": self._size_bytes,
            "node_count": self._node_count,
            "max_depth": self._max_depth,
            "type_counts": dict(self._type_counts),
            "top_level": _top_level_schema(self._payload),
        }

    def peek(self, n: int, *, where: str = "head") -> Any:
        if n <= 0:
            return make_error(INVALID_ARGS, "'n' must be positive.")
        if isinstance(self._payload, dict):
            items = list(self._payload.items())
            items = items[-n:] if where == "tail" else items[:n]
            return {k: _preview(v) for k, v in items}
        if isinstance(self._payload, list):
            items = self._payload[-n:] if where == "tail" else self._payload[:n]
            return [_preview(v) for v in items]
        return _preview(self._payload)

    def slice(self, selector: str, *, max_rows: int = 100) -> Any:
        try:
            hits = jpath_query(self._payload, selector)
        except JSONPathError as e:
            return make_error(INVALID_ARGS, f"invalid JSONPath: {e}")
        cap = min(max_rows, _SLICE_HARD_CAP)
        truncated = len(hits) > cap
        return {
            "matches": [{"path": p, "value": v} for p, v in hits[:cap]],
            "count": len(hits),
            "truncated": truncated,
        }

    def search(self, query: str, *, max_results: int = 10) -> Any:
        if not query:
            return make_error(INVALID_ARGS, "'query' must be non-empty.")
        needle = query.lower()
        cap = min(max_results, _SEARCH_HARD_CAP)
        results: list[dict[str, Any]] = []
        for path, value in _walk("$", self._payload):
            if len(results) >= cap:
                break
            # Match against scalar values or the last path segment (the key).
            if isinstance(value, str) and needle in value.lower():
                results.append({"path": path, "match": "value", "value": _preview(value)})
            elif isinstance(value, (int, float, bool)) and needle in str(value).lower():
                results.append({"path": path, "match": "value", "value": value})
            else:
                # Key match: last dotted/bracketed segment of path
                seg = _last_segment(path)
                if seg and needle in seg.lower():
                    results.append({"path": path, "match": "key", "preview": _preview(value)})
        return {"results": results, "count": len(results), "hard_cap": cap}

    def aggregate(self, op: str, field: str | None = None, *, group_by: str | None = None) -> Any:
        return make_error(NOT_APPLICABLE, "'aggregate' is not supported on json handles.")

    def close(self) -> None:  # pragma: no cover - trivial
        self._payload = None


# ------------- helpers ------------------------------------------------------


def _type_of(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def _scan(payload: Any) -> tuple[int, int, dict[str, int]]:
    counts: dict[str, int] = {}
    max_depth = 0
    node_count = 0

    def go(v: Any, depth: int) -> None:
        nonlocal max_depth, node_count
        node_count += 1
        if depth > max_depth:
            max_depth = depth
        counts[_type_of(v)] = counts.get(_type_of(v), 0) + 1
        if isinstance(v, dict):
            for vv in v.values():
                go(vv, depth + 1)
        elif isinstance(v, list):
            for vv in v:
                go(vv, depth + 1)

    go(payload, 0)
    return node_count, max_depth, counts


def _top_level_schema(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _type_of(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_type_of(v) for v in payload[:10]]
    return _type_of(payload)


def _preview(v: Any) -> Any:
    """Short, JSON-safe preview for peek/search output."""
    if isinstance(v, str):
        return v if len(v) <= _PREVIEW_VALUE_MAX else v[:_PREVIEW_VALUE_MAX] + "…"
    if isinstance(v, dict):
        return {"<object>": f"{len(v)} keys"}
    if isinstance(v, list):
        return [f"<array:{len(v)}>"]
    return v


def _last_segment(path: str) -> str:
    # Strip trailing ']' groups to get at the leaf name/index
    if path.endswith("]"):
        lbr = path.rfind("[")
        if lbr >= 0:
            inner = path[lbr + 1:-1]
            # Strip quotes for bracket-quoted keys
            if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in ("'", '"'):
                return inner[1:-1]
            return inner
    dot = path.rfind(".")
    return path[dot + 1:] if dot >= 0 else ""
