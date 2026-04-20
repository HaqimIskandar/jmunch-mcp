from jmunch_mcp.backends.tabular import TabularBackend


ROWS = [
    {"id": 1, "state": "open", "title": "auth bug", "upvotes": 3},
    {"id": 2, "state": "closed", "title": "typo in docs", "upvotes": 0},
    {"id": 3, "state": "open", "title": "auth crash", "upvotes": 7},
    {"id": 4, "state": "open", "title": "slow query", "upvotes": 1},
    {"id": 5, "state": "closed", "title": "fix build", "upvotes": 2},
]


def test_summary_and_describe():
    b = TabularBackend(ROWS)
    s = b.summary()
    assert s["row_count"] == 5
    assert s["column_count"] == 4
    d = b.describe()
    cols = {c["name"]: c for c in d["columns"]}
    assert cols["upvotes"]["type"] == "INTEGER"
    assert cols["upvotes"]["min"] == 0
    assert cols["upvotes"]["max"] == 7


def test_peek_head_and_tail():
    b = TabularBackend(ROWS)
    head = b.peek(2)
    assert [r["id"] for r in head] == [1, 2]
    tail = b.peek(2, where="tail")
    assert [r["id"] for r in tail] == [4, 5]


def test_slice_where_clause():
    b = TabularBackend(ROWS)
    open_rows = b.slice("state = 'open'")
    assert [r["id"] for r in open_rows] == [1, 3, 4]


def test_slice_rejects_injection():
    b = TabularBackend(ROWS)
    result = b.slice("1=1; DROP TABLE t")
    assert isinstance(result, dict) and result.get("code") == "INVALID_ARGS"


def test_aggregate_count_and_group():
    b = TabularBackend(ROWS)
    total = b.aggregate("count")
    assert total["value"] == 5
    by_state = b.aggregate("count", group_by="state")
    as_map = {g["group"]: g["value"] for g in by_state}
    assert as_map == {"open": 3, "closed": 2}


def test_aggregate_sum():
    b = TabularBackend(ROWS)
    result = b.aggregate("sum", field="upvotes")
    assert result["value"] == 13


def test_aggregate_rejects_unknown_field():
    b = TabularBackend(ROWS)
    result = b.aggregate("sum", field="nonexistent")
    assert result.get("code") == "INVALID_ARGS"


def test_search_substring():
    b = TabularBackend(ROWS)
    hits = b.search("auth")
    assert {r["id"] for r in hits} == {1, 3}
