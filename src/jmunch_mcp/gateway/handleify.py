"""Shared handle-ification helper for the gateway.

Takes a raw text payload (an OpenAI tool message `content`, or an Anthropic
`tool_result` block's content), classifies it via the sniffer, registers a
backend, and returns the jMRI envelope-wrapped replacement content.

Intentionally parallel to `proxy._maybe_handle_ify` — not DRY'd into a shared
helper with the MCP proxy per the refined plan (no churn in proxy.py). The
slice of logic is small and the two call sites have slightly different shapes.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..backends.jsontree import JSONBackend
from ..backends.tabular import TabularBackend
from ..backends.text import TextBackend
from ..meta import SavingsTracker, envelope, timer_ms
from ..registry import HandleRegistry
from ..sniffer import Kind, classify, extract_rows

log = logging.getLogger("jmunch.gateway.handleify")


def maybe_handleify(
    text: str,
    *,
    registry: HandleRegistry,
    tracker: SavingsTracker,
    threshold_tokens: int,
) -> tuple[str, str] | None:
    """If `text` is over threshold and classifiable, register a handle and
    return `(envelope_json, handle_id)`. Otherwise return None (passthrough).

    The 2-tuple shape is preserved for backward compat with existing tests.
    For exact-token accounting, callers can hold on to the original `text`
    and compare with the returned envelope via `TokenCounter`.
    """
    threshold_bytes = threshold_tokens * 4
    if len(text) < threshold_bytes:
        return None

    try:
        payload: Any = json.loads(text)
        kind = classify(payload)
    except json.JSONDecodeError:
        payload = text
        kind = Kind.TEXT

    started = time.perf_counter_ns()
    backend: Any
    summary_detail: dict[str, Any] = {}

    source: Any = None
    if kind is Kind.TEXT:
        text_payload = payload if isinstance(payload, str) else text
        try:
            backend = TextBackend(text_payload)
        except Exception as e:
            log.warning("text ingest failed, passthrough: %s", e)
            return None
        summary_detail = {"lines": len(backend._lines)}
        source = text_payload
    elif kind is Kind.TABULAR:
        rows = extract_rows(payload)
        if rows is None:
            return None
        try:
            backend = TabularBackend(rows)
        except Exception as e:
            log.warning("tabular ingest failed, passthrough: %s", e)
            return None
        summary_detail = {"rows": len(rows)}
        source = rows
    elif kind is Kind.JSON:
        try:
            backend = JSONBackend(payload)
        except Exception as e:
            log.warning("json ingest failed, passthrough: %s", e)
            return None
        summary_detail = {"nodes": backend._node_count}
        source = payload
    else:
        return None

    handle = registry.register(backend, backend.size_bytes, backend.kind, source=source)

    raw_bytes = len(text)
    handle_result = {
        "handle": handle.id,
        "kind": handle.kind,
        "summary": backend.summary(),
        "_hint": (
            "This payload was large and has been replaced with a handle. "
            "Use the jmunch_peek, jmunch_slice, jmunch_search, or jmunch_describe "
            "tools (aggregate for tabular only, summarize for text only) to drill in."
        ),
    }
    env = envelope(
        result=handle_result,
        raw_bytes=raw_bytes,
        response_bytes=0,
        tracker=tracker,
        timing_ms=timer_ms(started),
    )
    env_text = json.dumps(env, default=str)
    env["_meta"]["response_tokens"] = len(env_text) // 4
    env["_meta"]["tokens_saved"] = max(0, (raw_bytes - len(env_text)) // 4)
    env_text = json.dumps(env, default=str)

    log.info(
        "gateway handle-ified %s payload: raw=%d detail=%s handle=%s saved~%d tokens",
        backend.kind, raw_bytes, summary_detail, handle.id, env["_meta"]["tokens_saved"],
    )
    return env_text, handle.id
