"""Benchmark scripts: sequences of MCP tools/call frames to fire at an upstream.

Each script is a list of (label, tool_name, arguments) triples. Label is
printed in the report; tool_name/arguments are forwarded to the upstream.

The jmunch follow-up script is fired only in the proxied run, after handles
have been created. It references handle IDs symbolically via the sentinel
"$LAST_HANDLE" which the runner replaces with the most recently minted
handle id.
"""
from __future__ import annotations

# --- GitHub MCP ---------------------------------------------------------------
# Upstream: `npx -y @modelcontextprotocol/server-github`
# Requires GITHUB_PERSONAL_ACCESS_TOKEN in env.

GITHUB_CALLS: list[tuple[str, str, dict]] = [
    (
        "list_issues(facebook/react, state=all, per_page=100)",
        "list_issues",
        {"owner": "facebook", "repo": "react", "state": "all", "perPage": 100},
    ),
    (
        "list_pull_requests(facebook/react, state=all, per_page=100)",
        "list_pull_requests",
        {"owner": "facebook", "repo": "react", "state": "all", "perPage": 100},
    ),
    (
        "list_commits(facebook/react, per_page=100)",
        "list_commits",
        {"owner": "facebook", "repo": "react", "perPage": 100},
    ),
    (
        "search_issues(language:python label:bug, per_page=100)",
        "search_issues",
        {"q": "language:python label:bug", "perPage": 100},
    ),
]

# Follow-up calls against the most recent handle — models a realistic agent
# that drills into a large result instead of slurping the whole thing.
JMUNCH_FOLLOWUPS: list[tuple[str, str, dict]] = [
    ("jmunch_describe($LAST_HANDLE)", "jmunch_describe", {"handle": "$LAST_HANDLE"}),
    ("jmunch_peek($LAST_HANDLE, n=5)", "jmunch_peek", {"handle": "$LAST_HANDLE", "n": 5}),
    (
        "jmunch_slice($LAST_HANDLE, state='open', max_rows=10)",
        "jmunch_slice",
        {"handle": "$LAST_HANDLE", "selector": "state = 'open'", "max_rows": 10},
    ),
]


# --- Firecrawl MCP ------------------------------------------------------------
# Upstream: `npx -y firecrawl-mcp`
# Requires FIRECRAWL_API_KEY in env.

FIRECRAWL_CALLS: list[tuple[str, str, dict]] = [
    (
        "scrape(en.wikipedia.org/wiki/Artificial_intelligence)",
        "firecrawl_scrape",
        {"url": "https://en.wikipedia.org/wiki/Artificial_intelligence", "formats": ["markdown"]},
    ),
    (
        "scrape(en.wikipedia.org/wiki/Machine_learning)",
        "firecrawl_scrape",
        {"url": "https://en.wikipedia.org/wiki/Machine_learning", "formats": ["markdown"]},
    ),
    (
        "map(docs.python.org)",
        "firecrawl_map",
        {"url": "https://docs.python.org/3/"},
    ),
    (
        "search(large language models, limit=10)",
        "firecrawl_search",
        {"query": "large language models", "limit": 10},
    ),
]

# JSON-backend verb drills (replace tabular-specific ones).
JMUNCH_FOLLOWUPS_JSON: list[tuple[str, str, dict]] = [
    ("jmunch_describe($LAST_HANDLE)", "jmunch_describe", {"handle": "$LAST_HANDLE"}),
    ("jmunch_peek($LAST_HANDLE, n=5)", "jmunch_peek", {"handle": "$LAST_HANDLE", "n": 5}),
    (
        "jmunch_search($LAST_HANDLE, 'neural')",
        "jmunch_search",
        {"handle": "$LAST_HANDLE", "query": "neural", "max_results": 5},
    ),
]

