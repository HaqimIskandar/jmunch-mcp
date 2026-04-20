"""Text backend: opaque string corpora (logs, docs, prose, source files).

Chosen when the sniffer classifies a payload as TEXT (≥ _TEXT_MIN_CHARS) or
when upstream emits a large non-JSON text blob that we can't parse as JSON.

Verbs:
- peek(n, where)    → first/last N lines with line numbers
- slice(selector)   → `L10-L50` / `10-50` line range, or `re:<pattern>`
- search(query)     → substring (default, case-insensitive) or `re:<pattern>`;
                      returns line numbers + short previews
- describe()        → char/line/word counts + small sample of longest lines
- summarize()       → deterministic digest: head + tail + evenly-spaced
                      middle samples + top-k keyword tokens. No LLM.
- aggregate()       → NOT_APPLICABLE

Line numbers are 1-based. The full text is retained in memory; for large
inputs the line index (offsets + lengths) is all we need to answer any verb
without re-scanning.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..errors import INVALID_ARGS, NOT_APPLICABLE, make_error

_PREVIEW_MAX = 200
_SEARCH_HARD_CAP = 200
_SLICE_HARD_CAP = 2000
_SUMMARY_HEAD = 10
_SUMMARY_TAIL = 10
_SUMMARY_MIDDLE = 10
_KEYWORD_TOP_K = 20
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_']{2,}")

# Minimal English stopword list — enough to make keyword output useful without
# pulling in a dependency.
_STOPWORDS = frozenset("""
the and for that with this from have has had not but are was were will would
could should they them their there then than when what where which who whom
why how all any some one two into onto out off over under above below about
you your yours ours mine his her its hers him she them our your you're i'm
been being being more most other such only also very can just get got don't
""".split())


class TextBackend:
    kind = "text"

    def __init__(self, text: str) -> None:
        self._text = text
        self._lines = text.splitlines()
        self._size_bytes = len(text.encode("utf-8"))
        self._word_count = sum(1 for _ in _WORD_RE.finditer(text))

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def summary(self) -> dict[str, Any]:
        return {
            "char_count": len(self._text),
            "line_count": len(self._lines),
            "word_count": self._word_count,
            "size_bytes": self._size_bytes,
        }

    def describe(self) -> dict[str, Any]:
        sample = sorted(
            ((i + 1, ln) for i, ln in enumerate(self._lines) if ln),
            key=lambda t: len(t[1]),
            reverse=True,
        )[:5]
        return {
            "char_count": len(self._text),
            "line_count": len(self._lines),
            "word_count": self._word_count,
            "size_bytes": self._size_bytes,
            "longest_lines": [
                {"line": ln_no, "length": len(ln), "preview": _preview(ln)}
                for ln_no, ln in sample
            ],
        }

    def peek(self, n: int, *, where: str = "head") -> Any:
        if n <= 0:
            return make_error(INVALID_ARGS, "'n' must be positive.")
        if where == "tail":
            start = max(0, len(self._lines) - n)
            sel = list(enumerate(self._lines[start:], start=start + 1))
        else:
            sel = list(enumerate(self._lines[:n], start=1))
        return {
            "lines": [{"line": ln_no, "text": ln} for ln_no, ln in sel],
            "total_lines": len(self._lines),
        }

    def slice(self, selector: str, *, max_rows: int = 100) -> Any:
        selector = selector.strip()
        if not selector:
            return make_error(INVALID_ARGS, "'selector' is required.")
        cap = min(max_rows, _SLICE_HARD_CAP)

        if selector.startswith("re:"):
            pattern = selector[3:]
            try:
                rx = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return make_error(INVALID_ARGS, f"invalid regex: {e}")
            hits = []
            for i, ln in enumerate(self._lines, start=1):
                if rx.search(ln):
                    hits.append({"line": i, "text": ln})
                    if len(hits) >= cap:
                        break
            return {"lines": hits, "count": len(hits), "truncated": len(hits) >= cap}

        m = re.fullmatch(r"L?(\d+)\s*-\s*L?(\d+)", selector)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo < 1 or hi < lo:
                return make_error(INVALID_ARGS, f"invalid line range: {selector}")
            lo0 = lo - 1
            hi0 = min(hi, len(self._lines))
            window = self._lines[lo0:hi0]
            truncated = len(window) > cap
            window = window[:cap]
            return {
                "lines": [
                    {"line": lo + i, "text": ln} for i, ln in enumerate(window)
                ],
                "count": len(window),
                "truncated": truncated,
            }

        return make_error(
            INVALID_ARGS,
            "selector must be a line range like '10-50' or 'L10-L50', "
            "or a regex prefixed with 're:'.",
        )

    def search(self, query: str, *, max_results: int = 10) -> Any:
        if not query:
            return make_error(INVALID_ARGS, "'query' must be non-empty.")
        cap = min(max_results, _SEARCH_HARD_CAP)

        if query.startswith("re:"):
            try:
                rx = re.compile(query[3:], re.IGNORECASE)
            except re.error as e:
                return make_error(INVALID_ARGS, f"invalid regex: {e}")
            def find_col(s: str) -> int | None:
                m = rx.search(s)
                return m.start() if m else None
        else:
            needle = query.lower()
            def find_col(s: str) -> int | None:
                idx = s.lower().find(needle)
                return idx if idx >= 0 else None

        results: list[dict[str, Any]] = []
        for i, ln in enumerate(self._lines, start=1):
            idx = find_col(ln)
            if idx is None:
                continue
            results.append({"line": i, "col": idx + 1, "preview": _preview(ln)})
            if len(results) >= cap:
                break
        return {"results": results, "count": len(results), "hard_cap": cap}

    def summarize(self, *, max_keywords: int = _KEYWORD_TOP_K) -> Any:
        """Deterministic digest — no LLM. Head, tail, evenly-spaced middle
        samples, plus top-k content tokens (stopwords filtered)."""
        n = len(self._lines)
        head = [
            {"line": i + 1, "text": ln}
            for i, ln in enumerate(self._lines[:_SUMMARY_HEAD])
        ]
        tail_start = max(_SUMMARY_HEAD, n - _SUMMARY_TAIL)
        tail = [
            {"line": i + 1, "text": ln}
            for i, ln in enumerate(self._lines[tail_start:], start=tail_start)
        ]

        middle: list[dict[str, Any]] = []
        middle_lo = _SUMMARY_HEAD
        middle_hi = tail_start
        if middle_hi > middle_lo and _SUMMARY_MIDDLE > 0:
            span = middle_hi - middle_lo
            step = max(1, span // _SUMMARY_MIDDLE)
            for i in range(middle_lo, middle_hi, step):
                middle.append({"line": i + 1, "text": self._lines[i]})
                if len(middle) >= _SUMMARY_MIDDLE:
                    break

        counter: Counter[str] = Counter()
        for tok in _WORD_RE.findall(self._text):
            low = tok.lower()
            if low in _STOPWORDS or len(low) < 4:
                continue
            counter[low] += 1
        top = [
            {"token": tok, "count": c}
            for tok, c in counter.most_common(max_keywords)
        ]

        return {
            "line_count": n,
            "word_count": self._word_count,
            "head": head,
            "middle": middle,
            "tail": tail,
            "keywords": top,
        }

    def aggregate(self, op: str, field: str | None = None, *, group_by: str | None = None) -> Any:
        return make_error(NOT_APPLICABLE, "'aggregate' is not supported on text handles.")

    def close(self) -> None:  # pragma: no cover - trivial
        self._text = ""
        self._lines = []


def _preview(s: str) -> str:
    if len(s) <= _PREVIEW_MAX:
        return s
    return s[:_PREVIEW_MAX] + "…"
