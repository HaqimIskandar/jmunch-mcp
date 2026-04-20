"""Session-scoped telemetry for the --report flag.

PRD F-23: "prints a session summary on shutdown: total tokens saved,
handles created, backend distribution, handle reuse count."

Cumulative per-install totals live in SavingsTracker (persisted). This
module tracks *this session only* — the delta between startup and
shutdown is what the operator wants to see.
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class SessionStats:
    started_ns: int = field(default_factory=time.perf_counter_ns)
    tokens_saved_at_start: int = 0
    tokens_saved_at_end: int = 0

    handles_created: int = 0
    handles_by_kind: Counter = field(default_factory=Counter)
    handle_reuses: int = 0
    passthroughs: int = 0
    bypasses: int = 0  # reserved; F-22 deferred

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_handle_created(self, kind: str) -> None:
        with self._lock:
            self.handles_created += 1
            self.handles_by_kind[kind] += 1

    def record_reuse(self) -> None:
        with self._lock:
            self.handle_reuses += 1

    def record_passthrough(self) -> None:
        with self._lock:
            self.passthroughs += 1

    def finalize(self, tokens_saved_now: int) -> None:
        self.tokens_saved_at_end = tokens_saved_now

    @property
    def session_tokens_saved(self) -> int:
        return max(0, self.tokens_saved_at_end - self.tokens_saved_at_start)

    @property
    def elapsed_s(self) -> float:
        return (time.perf_counter_ns() - self.started_ns) / 1_000_000_000

    def render(self) -> str:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(self.handles_by_kind.items())) or "—"
        return (
            "─── jmunch-mcp session report ──────────────────────────────\n"
            f"  elapsed:               {self.elapsed_s:.1f}s\n"
            f"  session tokens saved:  {self.session_tokens_saved:,}\n"
            f"  handles created:       {self.handles_created}\n"
            f"  handle reuses:         {self.handle_reuses}\n"
            f"  passthroughs:          {self.passthroughs}\n"
            f"  backend distribution:  {kinds}\n"
            "─────────────────────────────────────────────────────────────"
        )
