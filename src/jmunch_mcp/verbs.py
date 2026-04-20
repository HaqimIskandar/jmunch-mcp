"""jmunch.* tool schemas + local dispatch.

These are the MCP tools we add to the upstream's tool list on the way through.
They never reach the upstream — the proxy intercepts any call whose name
starts with `jmunch.` and routes here.

Each handler returns a *raw* result payload (or an error dict via make_error);
the proxy wraps it in the jMRI envelope before emitting.
"""
from __future__ import annotations

from typing import Any

from .errors import HANDLE_EXPIRED, INVALID_ARGS, NOT_APPLICABLE, make_error
from .registry import HandleRegistry
from .stats import SessionStats

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "jmunch.peek",
        "description": "Return the first or last N items of a handle-ified payload.",
        "inputSchema": {
            "type": "object",
            "required": ["handle"],
            "properties": {
                "handle": {"type": "string"},
                "n": {"type": "integer", "default": 10, "minimum": 1},
                "where": {"type": "string", "enum": ["head", "tail"], "default": "head"},
            },
        },
    },
    {
        "name": "jmunch.slice",
        "description": "Subset a handle by selector. Tabular: SQL WHERE. JSON: JSONPath. Text: regex/line range.",
        "inputSchema": {
            "type": "object",
            "required": ["handle", "selector"],
            "properties": {
                "handle": {"type": "string"},
                "selector": {"type": "string"},
                "max_rows": {"type": "integer", "default": 100, "minimum": 1},
            },
        },
    },
    {
        "name": "jmunch.search",
        "description": "Search within a handle. Backend-specific; tabular supports substring match across TEXT columns.",
        "inputSchema": {
            "type": "object",
            "required": ["handle", "query"],
            "properties": {
                "handle": {"type": "string"},
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 10, "minimum": 1},
            },
        },
    },
    {
        "name": "jmunch.aggregate",
        "description": "count/sum/avg/min/max on a tabular handle, optionally grouped.",
        "inputSchema": {
            "type": "object",
            "required": ["handle", "op"],
            "properties": {
                "handle": {"type": "string"},
                "op": {"type": "string", "enum": ["count", "sum", "avg", "min", "max"]},
                "field": {"type": "string"},
                "group_by": {"type": "string"},
            },
        },
    },
    {
        "name": "jmunch.summarize",
        "description": "Deterministic digest for text handles: head + middle samples + tail + top keywords. Text only.",
        "inputSchema": {
            "type": "object",
            "required": ["handle"],
            "properties": {
                "handle": {"type": "string"},
                "max_keywords": {"type": "integer", "default": 20, "minimum": 1},
            },
        },
    },
    {
        "name": "jmunch.describe",
        "description": "Full metadata for a handle: schema, row/field counts, per-column stats where applicable.",
        "inputSchema": {
            "type": "object",
            "required": ["handle"],
            "properties": {"handle": {"type": "string"}},
        },
    },
    {
        "name": "jmunch.list_handles",
        "description": "List currently live handles with their kind and size.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

TOOL_NAMES = {t["name"] for t in TOOL_SCHEMAS}


def is_jmunch_tool(name: str) -> bool:
    return name in TOOL_NAMES


class Dispatcher:
    def __init__(self, registry: HandleRegistry, stats: SessionStats | None = None) -> None:
        self._registry = registry
        self._stats = stats or SessionStats()

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handler = _HANDLERS.get(name)
        if handler is None:
            return make_error(INVALID_ARGS, f"Unknown jmunch tool '{name}'.")
        return handler(self, args)

    # --- handlers ---

    def _peek(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        return h.backend.peek(int(args.get("n", 10)), where=str(args.get("where", "head")))

    def _slice(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        selector = args.get("selector")
        if not isinstance(selector, str) or not selector:
            return make_error(INVALID_ARGS, "'selector' is required.")
        if not hasattr(h.backend, "slice"):
            return make_error(NOT_APPLICABLE, f"'slice' not supported for kind={h.kind}.")
        return h.backend.slice(selector, max_rows=int(args.get("max_rows", 100)))

    def _search(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        query = args.get("query")
        if not isinstance(query, str) or not query:
            return make_error(INVALID_ARGS, "'query' is required.")
        return h.backend.search(query, max_results=int(args.get("max_results", 10)))

    def _aggregate(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        if h.kind != "tabular":
            return make_error(NOT_APPLICABLE, f"'aggregate' requires a tabular handle; got {h.kind}.")
        op = args.get("op")
        if not isinstance(op, str):
            return make_error(INVALID_ARGS, "'op' is required.")
        return h.backend.aggregate(op, field=args.get("field"), group_by=args.get("group_by"))

    def _summarize(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        if not hasattr(h.backend, "summarize"):
            return make_error(NOT_APPLICABLE, f"'summarize' not supported for kind={h.kind}.")
        return h.backend.summarize(max_keywords=int(args.get("max_keywords", 20)))

    def _describe(self, args: dict[str, Any]) -> Any:
        h = self._require_handle(args)
        if isinstance(h, dict):
            return h
        return {
            "handle": h.id,
            "kind": h.kind,
            "size_bytes": h.size_bytes,
            **h.backend.describe(),
        }

    def _list_handles(self, _args: dict[str, Any]) -> Any:
        return [
            {"handle": h.id, "kind": h.kind, "size_bytes": h.size_bytes}
            for h in self._registry.list()
        ]

    def _require_handle(self, args: dict[str, Any]):
        hid = args.get("handle")
        if not isinstance(hid, str) or not hid:
            return make_error(INVALID_ARGS, "'handle' is required.")
        h = self._registry.get(hid)
        if h is None:
            return make_error(HANDLE_EXPIRED, f"Handle '{hid}' has expired or was never issued.", handle=hid)
        self._stats.record_reuse()
        return h


_HANDLERS = {
    "jmunch.peek": Dispatcher._peek,
    "jmunch.slice": Dispatcher._slice,
    "jmunch.search": Dispatcher._search,
    "jmunch.aggregate": Dispatcher._aggregate,
    "jmunch.summarize": Dispatcher._summarize,
    "jmunch.describe": Dispatcher._describe,
    "jmunch.list_handles": Dispatcher._list_handles,
}
