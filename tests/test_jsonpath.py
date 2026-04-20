import pytest

from jmunch_mcp.jsonpath import JSONPathError, compile_path, query


def test_root_only():
    data = {"a": 1}
    assert query(data, "$") == [("$", data)]


def test_dot_field():
    data = {"a": {"b": 42}}
    assert query(data, "$.a.b") == [("$.a.b", 42)]


def test_bracket_field_with_special_chars():
    data = {"foo-bar": {"baz": 7}}
    out = query(data, "$['foo-bar'].baz")
    assert out == [("$['foo-bar'].baz", 7)]


def test_index():
    data = {"items": ["x", "y", "z"]}
    assert query(data, "$.items[1]") == [("$.items[1]", "y")]


def test_wildcard_array():
    data = {"items": [{"n": 1}, {"n": 2}]}
    out = query(data, "$.items[*].n")
    assert out == [("$.items[0].n", 1), ("$.items[1].n", 2)]


def test_wildcard_object():
    data = {"a": 1, "b": 2}
    paths = {p for p, _ in query(data, "$[*]")}
    assert paths == {"$.a", "$.b"}


def test_recursive_descent_field():
    data = {"x": {"name": "A", "y": [{"name": "B"}, {"name": "C"}]}}
    names = sorted(v for _, v in query(data, "$..name"))
    assert names == ["A", "B", "C"]


def test_missing_field_returns_empty():
    assert query({"a": 1}, "$.missing") == []


def test_bad_expr_raises():
    with pytest.raises(JSONPathError):
        compile_path("no-leading-dollar")
    with pytest.raises(JSONPathError):
        compile_path("$.[")
