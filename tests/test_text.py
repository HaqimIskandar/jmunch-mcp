from jmunch_mcp.backends.text import TextBackend


def _sample(n_lines: int = 200) -> str:
    lines = []
    for i in range(n_lines):
        if i % 25 == 0:
            lines.append(f"line {i}: neural networks learn representations from data")
        elif i % 7 == 0:
            lines.append(f"line {i}: the quick brown fox jumps over the lazy dog")
        else:
            lines.append(f"line {i}: some ordinary filler content about topic {i}")
    return "\n".join(lines)


def test_kind_and_summary():
    b = TextBackend(_sample())
    s = b.summary()
    assert b.kind == "text"
    assert s["line_count"] == 200
    assert s["word_count"] > 0
    assert s["size_bytes"] > 0


def test_describe_has_longest_lines():
    b = TextBackend(_sample())
    d = b.describe()
    assert "longest_lines" in d
    assert len(d["longest_lines"]) <= 5


def test_peek_head_and_tail():
    b = TextBackend(_sample())
    head = b.peek(3, where="head")
    assert [r["line"] for r in head["lines"]] == [1, 2, 3]
    tail = b.peek(3, where="tail")
    assert [r["line"] for r in tail["lines"]] == [198, 199, 200]


def test_slice_line_range():
    b = TextBackend(_sample())
    r = b.slice("10-15")
    assert [row["line"] for row in r["lines"]] == [10, 11, 12, 13, 14, 15]
    r2 = b.slice("L5-L7")
    assert [row["line"] for row in r2["lines"]] == [5, 6, 7]


def test_slice_regex():
    b = TextBackend(_sample())
    r = b.slice("re:neural")
    assert r["count"] >= 1
    assert all("neural" in ln["text"].lower() for ln in r["lines"])


def test_slice_bad_selector_errors():
    b = TextBackend(_sample())
    err = b.slice("nonsense")
    assert err["code"] == "INVALID_ARGS"


def test_search_substring():
    b = TextBackend(_sample())
    r = b.search("brown fox")
    assert r["count"] >= 1
    for hit in r["results"]:
        assert "line" in hit and "col" in hit and "preview" in hit


def test_search_regex():
    b = TextBackend(_sample())
    r = b.search("re:line \\d+:")
    assert r["count"] == 10  # default max_results


def test_summarize_has_sections():
    b = TextBackend(_sample())
    s = b.summarize()
    assert s["line_count"] == 200
    assert len(s["head"]) == 10
    assert len(s["tail"]) == 10
    assert len(s["middle"]) > 0
    # keywords filter out stopwords and short tokens
    tokens = {kw["token"] for kw in s["keywords"]}
    assert "the" not in tokens
    assert all(len(t) >= 4 for t in tokens)


def test_aggregate_not_applicable():
    b = TextBackend(_sample())
    err = b.aggregate("count")
    assert err["code"] == "NOT_APPLICABLE"
