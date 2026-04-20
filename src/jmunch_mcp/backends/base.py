"""Backend protocol.

Each backend owns storage for a handle-ified payload and answers the subset
of jmunch verbs that make sense for its content kind. Verbs that don't apply
return a NOT_APPLICABLE error via the dispatcher, not by raising.

This interface is deliberately narrow so Phase 2 (plugin backends) has a
stable contract to bless.
"""
from __future__ import annotations

from typing import Any, Protocol


class Backend(Protocol):
    kind: str  # sniffer.Kind value

    def summary(self) -> dict[str, Any]:
        """Initial summary returned alongside the handle on ingest."""
        ...

    def describe(self) -> dict[str, Any]:
        """Full metadata for jmunch.describe — schema, row/field counts, etc."""
        ...

    def peek(self, n: int, *, where: str = "head") -> Any: ...

    def slice(self, selector: str, *, max_rows: int = 100) -> Any: ...

    def search(self, query: str, *, max_results: int = 10) -> Any: ...

    def aggregate(self, op: str, field: str | None = None, *, group_by: str | None = None) -> Any: ...

    def close(self) -> None: ...
