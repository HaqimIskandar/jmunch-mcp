from jmunch_mcp.backends.jsontree import JSONBackend


def _sample():
    return {
        "repository": {"name": "react", "stars": 200000},
        "issues": [
            {"id": 1, "title": "bug A", "labels": ["bug", "triage"]},
            {"id": 2, "title": "feat B", "labels": ["enhancement"]},
            {"id": 3, "title": "bug C", "labels": ["bug"]},
        ],
        "meta": {"fetched_at": "2026-04-20", "source": "github"},
    }


def test_kind_and_summary():
    b = JSONBackend(_sample())
    s = b.summary()
    assert b.kind == "json"
    assert s["root_type"] == "object"
    assert set(s["top_level_keys"]) == {"repository", "issues", "meta"}
    assert s["node_count"] > 0
    assert s["max_depth"] >= 2


def test_describe_includes_type_counts():
    b = JSONBackend(_sample())
    d = b.describe()
    assert d["type_counts"].get("string", 0) >= 3
    assert d["top_level"]["issues"] == "array"


def test_peek_dict_head():
    b = JSONBackend(_sample())
    out = b.peek(2)
    assert list(out.keys())[:2] == ["repository", "issues"]


def test_slice_jsonpath_wildcard():
    b = JSONBackend(_sample())
    out = b.slice("$.issues[*].title")
    titles = [m["value"] for m in out["matches"]]
    assert titles == ["bug A", "feat B", "bug C"]
    assert out["count"] == 3
    assert out["truncated"] is False


def test_slice_recursive_descent():
    b = JSONBackend(_sample())
    out = b.slice("$..title")
    assert out["count"] == 3


def test_slice_invalid_selector_returns_error():
    b = JSONBackend(_sample())
    out = b.slice("not-a-jsonpath")
    assert isinstance(out, dict) and "code" in out and "message" in out


def test_search_matches_values_and_keys():
    b = JSONBackend(_sample())
    out = b.search("bug")
    paths = [r["path"] for r in out["results"]]
    # "bug" appears in titles and in labels arrays
    assert any("title" in p for p in paths)
    assert any("labels" in p for p in paths)


def test_aggregate_not_applicable():
    b = JSONBackend(_sample())
    out = b.aggregate("count")
    assert "code" in out
