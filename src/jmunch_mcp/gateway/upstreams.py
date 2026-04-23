"""Upstream HTTP adapters.

Each adapter forwards a parsed request dict to a real LLM provider and
returns the parsed response (non-streaming) or an async iterator of SSE
chunks (streaming — Phase 2).

Phase 1 ships `complete()` only. The `stream()` method is defined on the
protocol so Phase 2 can fill it in without touching call sites that don't
need streaming.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Protocol

from .config import UpstreamSpec

log = logging.getLogger("jmunch.gateway.upstream")


class UpstreamError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"upstream returned {status}: {body[:500]}")
        self.status = status
        self.body = body


class Upstream(Protocol):
    spec: UpstreamSpec

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]: ...

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[bytes]: ...  # Phase 2

    async def close(self) -> None: ...


class _BaseHTTPUpstream:
    """Shared aiohttp session management. aiohttp is imported lazily so the
    package still imports without the [gateway] extra installed."""

    def __init__(self, spec: UpstreamSpec) -> None:
        self.spec = spec
        self._session: Any = None  # aiohttp.ClientSession, lazy
        self._aiohttp: Any = None

    def _ensure_session(self) -> Any:
        if self._session is None:
            try:
                import aiohttp  # noqa
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "aiohttp is required for the gateway. "
                    "Install with: pip install 'jmunch-mcp[gateway]'"
                ) from e
            self._aiohttp = aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


class OpenAIUpstream(_BaseHTTPUpstream):
    """Speaks OpenAI's `/v1/chat/completions`. Works for the real OpenAI API,
    Ollama, OpenRouter, LM Studio, and anything else OpenAI-compatible."""

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        session = self._ensure_session()
        url = f"{self.spec.base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.spec.api_key:
            headers["Authorization"] = f"Bearer {self.spec.api_key}"

        # Always non-streaming in Phase 1 regardless of what the app requested.
        body = dict(request)
        body["stream"] = False

        async with session.post(url, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise UpstreamError(resp.status, text)
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise UpstreamError(resp.status, text) from e

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[bytes]:
        session = self._ensure_session()
        url = f"{self.spec.base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.spec.api_key:
            headers["Authorization"] = f"Bearer {self.spec.api_key}"
        body = dict(request)
        body["stream"] = True
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise UpstreamError(resp.status, text)
            async for piece in resp.content.iter_any():
                yield piece


class AnthropicUpstream(_BaseHTTPUpstream):
    """Speaks Anthropic's `/v1/messages`. Phase 3 wires this into the router."""

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        session = self._ensure_session()
        url = f"{self.spec.base_url}/v1/messages"
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.spec.api_key:
            headers["x-api-key"] = self.spec.api_key

        body = dict(request)
        body["stream"] = False

        async with session.post(url, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise UpstreamError(resp.status, text)
            return json.loads(text)

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[bytes]:
        session = self._ensure_session()
        url = f"{self.spec.base_url}/v1/messages"
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01",
                   "Accept": "text/event-stream"}
        if self.spec.api_key:
            headers["x-api-key"] = self.spec.api_key
        body = dict(request)
        body["stream"] = True
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise UpstreamError(resp.status, text)
            async for piece in resp.content.iter_any():
                yield piece


def build(spec: UpstreamSpec) -> Upstream:
    if spec.kind == "openai":
        return OpenAIUpstream(spec)
    if spec.kind == "anthropic":
        return AnthropicUpstream(spec)
    raise ValueError(f"unknown upstream kind: {spec.kind}")
