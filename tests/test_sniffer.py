from jmunch_mcp.sniffer import Kind, classify, extract_rows


def test_tabular_array_of_dicts():
    rows = [{"id": i, "name": f"n{i}"} for i in range(10)]
    assert classify(rows) is Kind.TABULAR
    assert extract_rows(rows) == rows


def test_tabular_wrapped_in_items():
    payload = {"items": [{"a": 1, "b": 2} for _ in range(6)]}
    assert classify(payload) is Kind.TABULAR
    assert extract_rows(payload) is not None


def test_small_array_is_unknown():
    assert classify([{"a": 1}]) is Kind.UNKNOWN


def test_text_payload():
    assert classify("x" * 2000) is Kind.TEXT
    assert classify("short") is Kind.UNKNOWN


def test_json_tree():
    assert classify({"nested": {"key": [1, 2, 3]}}) is Kind.JSON


def test_heterogeneous_array_is_json():
    assert classify([{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}, {"e": 5}]) is Kind.JSON


def test_unknown_scalar():
    assert classify(42) is Kind.UNKNOWN
    assert classify(None) is Kind.UNKNOWN
