# jmunch-mcp benchmarks

Reproduce the headline numbers from the top-level README. Each suite fires a fixed script of `tools/call` frames at an upstream MCP server twice — once direct, once through `jmunch-mcp` — with three follow-up `jmunch.*` verb calls on the proxied side to model an agent drilling into a large result.

## Run

```bash
python -m bench.run_bench --config bench/github.toml    --suite github
python -m bench.run_bench --config bench/firecrawl.toml --suite firecrawl
```

Requires `GITHUB_PERSONAL_ACCESS_TOKEN` and `FIRECRAWL_API_KEY` in your environment, respectively. Write the markdown output to a file with `--out <path>`.

## Files

- `run_bench.py` — minimal stdio MCP client + direct/proxied runner + markdown renderer.
- `scripts.py` — the call sequences (`GITHUB_CALLS`, `FIRECRAWL_CALLS`) and the follow-up verbs (`JMUNCH_FOLLOWUPS`, `JMUNCH_FOLLOWUPS_JSON`).
- `github.toml`, `firecrawl.toml` — upstream configs reused by both the direct baseline and the proxied run, so there's no drift between the two legs.
- `RESULTS_github.md`, `RESULTS_firecrawl.md` — the exact reports rendered from the last run.

## Methodology

- **Token accounting:** raw JSON-RPC response bytes divided by 4 (jMRI convention). No LLM in the loop.
- **Wall-clock:** `time.perf_counter()` around each `asyncio.run()` leg.
- **No caching:** the proxy starts fresh per run; no disk-backed handle persistence is in play.
- **Fair baseline:** the direct leg uses the *same* upstream config the proxy wraps, so the upstream launch path is identical.
