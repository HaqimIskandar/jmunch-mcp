"""Metrics read-side filters by `surface`, and exact tokens flow through
when the gateway writes them."""
from __future__ import annotations

from jmunch_mcp import metrics


def test_surface_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("JMUNCH_METRICS_DB", str(tmp_path / "m.db"))
    db = metrics.MetricsDB()

    db.record(upstream="github", tool="mcp_list", raw_bytes=10000,
              response_bytes=500, saved_bytes=9500, surface="mcp",
              tokens_saved_exact=0)
    db.record(upstream="openai", tool="chat.completions", raw_bytes=20000,
              response_bytes=1000, saved_bytes=19000, surface="gateway",
              tokens_saved_exact=4500)

    path = metrics.default_db_path()

    all_totals = metrics.totals(path)
    assert all_totals["calls"] == 2
    assert all_totals["saved_bytes"] == 9500 + 19000
    assert all_totals["tokens_saved_exact"] == 4500

    mcp_totals = metrics.totals(path, surface="mcp")
    assert mcp_totals["calls"] == 1
    assert mcp_totals["saved_bytes"] == 9500
    assert mcp_totals["tokens_saved_exact"] == 0

    gw_totals = metrics.totals(path, surface="gateway")
    assert gw_totals["calls"] == 1
    assert gw_totals["saved_bytes"] == 19000
    assert gw_totals["tokens_saved_exact"] == 4500

    # per_upstream groups by (upstream, surface).
    rows = metrics.per_upstream(path)
    assert any(r["upstream"] == "openai" and r["surface"] == "gateway"
               and r["tokens_saved_exact"] == 4500 for r in rows)

    # recent_calls exposes the surface column.
    calls = metrics.recent_calls(limit=10, path=path, surface="gateway")
    assert len(calls) == 1 and calls[0]["surface"] == "gateway"

    db.close()


def test_legacy_rows_default_to_mcp_surface(tmp_path, monkeypatch):
    """Rows written before the surface column existed should show up as 'mcp'
    after the automatic migration."""
    monkeypatch.setenv("JMUNCH_METRICS_DB", str(tmp_path / "m.db"))
    db = metrics.MetricsDB()
    db.record(upstream="firecrawl", tool="mcp_scrape",
              raw_bytes=5000, response_bytes=200, saved_bytes=4800)
    # Default surface=mcp.
    rows = metrics.per_upstream(metrics.default_db_path(), surface="mcp")
    assert any(r["upstream"] == "firecrawl" for r in rows)
    db.close()
