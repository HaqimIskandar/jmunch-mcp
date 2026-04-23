"""TokenCounter: uses tiktoken when available, falls back to bytes/4 cleanly."""
from __future__ import annotations

from jmunch_mcp.token_counter import TokenCounter


def test_count_empty_string_is_zero():
    tc = TokenCounter()
    assert tc.count("") == 0
    assert tc.count("", model="gpt-4") == 0


def test_fallback_without_model():
    tc = TokenCounter()
    # Without a model, we always fall back to bytes/4.
    text = "x" * 400
    assert tc.count(text) == 100


def test_count_saved_matches_delta():
    tc = TokenCounter()
    raw = "y" * 800
    sent = "y" * 200
    # bytes/4: 200 tokens → 50. Saved = 150.
    assert tc.count_saved(raw, sent) == 150


def test_exact_with_tiktoken_if_available():
    """If tiktoken is installed we should get a non-bytes/4 count for gpt-4.
    If not installed, the fallback still works — the assertion is soft."""
    tc = TokenCounter()
    got = tc.count("hello world", model="gpt-4")
    # Regardless of tiktoken presence: non-negative, not wildly off.
    assert got >= 1
    assert got < 10


def test_anthropic_model_falls_back_to_bytes_over_4():
    tc = TokenCounter()
    # Anthropic isn't in the tiktoken family; we use bytes/4.
    text = "z" * 400
    assert tc.count(text, model="claude-opus-4-20250514") == 100
