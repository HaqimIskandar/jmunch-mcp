"""Per-provider tokenizer adapter.

Ships as additive jMRI metadata: existing `_meta.tokens_saved` (bytes/4)
stays the canonical field; exact counts are published as
`_meta.tokens_saved_exact` when available.

Accuracy sources:
  * OpenAI / Ollama: `tiktoken` encoding for the model family.
  * Anthropic: no zero-RTT tokenizer — we stick with bytes/4 per the plan
    (the API's `count_tokens` endpoint is a network round-trip, which would
    blow up per-response metering).
"""
from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger("jmunch.tokens")


class TokenCounter:
    """Counts tokens for a (text, model) pair. Lazy-loads tiktoken and
    caches encodings per model."""

    def __init__(self) -> None:
        self._tiktoken = None
        self._tried_tiktoken = False

    def _load_tiktoken(self):
        if self._tried_tiktoken:
            return self._tiktoken
        self._tried_tiktoken = True
        try:
            import tiktoken  # type: ignore
            self._tiktoken = tiktoken
        except ImportError:
            self._tiktoken = None
        return self._tiktoken

    def count(self, text: str, *, model: str | None = None) -> int:
        if not isinstance(text, str) or not text:
            return 0
        tk = self._load_tiktoken()
        if tk is not None and model and _is_openai_family(model):
            enc = self._encoding_for(tk, model)
            if enc is not None:
                try:
                    return len(enc.encode(text))
                except Exception:  # pragma: no cover
                    pass
        return max(0, len(text.encode("utf-8")) // 4)

    def count_saved(self, raw: str, sent: str, *, model: str | None = None) -> int:
        return max(0, self.count(raw, model=model) - self.count(sent, model=model))

    @staticmethod
    @lru_cache(maxsize=32)
    def _encoding_for(tk, model: str):
        try:
            return tk.encoding_for_model(model)
        except Exception:
            try:
                return tk.get_encoding("cl100k_base")
            except Exception:  # pragma: no cover
                return None


def _is_openai_family(model: str) -> bool:
    m = model.lower()
    return (
        m.startswith("gpt") or m.startswith("o1") or m.startswith("o3")
        or "llama" in m or "qwen" in m or "mistral" in m  # Ollama-hosted etc.
    )
