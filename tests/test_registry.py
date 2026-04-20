from jmunch_mcp.registry import HandleRegistry


class _StubBackend:
    kind = "tabular"
    closed = False

    def close(self) -> None:
        self.closed = True


def test_register_and_get():
    r = HandleRegistry()
    b = _StubBackend()
    h = r.register(b, size_bytes=1000, kind="tabular")
    assert r.get(h.id) is h
    assert len(r) == 1
    assert r.total_bytes == 1000


def test_lru_evicts_oldest_over_count_cap():
    r = HandleRegistry(max_handles=2, max_bytes=10**9)
    b1, b2, b3 = _StubBackend(), _StubBackend(), _StubBackend()
    h1 = r.register(b1, 10, "tabular")
    h2 = r.register(b2, 10, "tabular")
    h3 = r.register(b3, 10, "tabular")
    assert r.get(h1.id) is None  # evicted
    assert r.get(h2.id) is not None
    assert r.get(h3.id) is not None
    assert b1.closed is True


def test_lru_evicts_over_byte_cap():
    r = HandleRegistry(max_handles=1000, max_bytes=50)
    b1, b2 = _StubBackend(), _StubBackend()
    r.register(b1, 30, "tabular")
    r.register(b2, 30, "tabular")  # 60 > 50, b1 must be evicted
    assert b1.closed is True


def test_get_promotes_to_most_recent():
    r = HandleRegistry(max_handles=2, max_bytes=10**9)
    b1, b2, b3 = _StubBackend(), _StubBackend(), _StubBackend()
    h1 = r.register(b1, 10, "tabular")
    h2 = r.register(b2, 10, "tabular")
    r.get(h1.id)  # promote h1
    r.register(b3, 10, "tabular")  # should evict h2, not h1
    assert r.get(h1.id) is not None
    assert r.get(h2.id) is None


def test_drop_removes_and_closes():
    r = HandleRegistry()
    b = _StubBackend()
    h = r.register(b, 100, "tabular")
    assert r.drop(h.id) is True
    assert r.get(h.id) is None
    assert b.closed is True
    assert r.drop(h.id) is False
