# nanobot × jmunch-mcp — the token-sipping demo

A 90-second, on-camera proof that jmunch-mcp cuts an agent's token spend by **95%+** on realistic tool-using tasks — with a **one-line config flip** as the only visible change.

> **Before:** nanobot fetches a Wikipedia page via its MCP. The full ~100KB of page markdown lands in Claude's context. The next turn burns ~25–30K input tokens to produce a one-paragraph answer.
>
> **After:** Same nanobot, same prompt, same final answer. A single jmunch config flag flips. The Wikipedia page becomes a 1KB handle; Claude drills in with `jmunch_peek`; the next turn burns ~800 input tokens.
>
> *"Same agent. Same task. Same answer. One flag. 96% fewer tokens."*

---

## The chain

```
nanobot ──OpenAI-compat──▶ jmunch gateway ──OpenAI-compat──▶ Anthropic  ──▶ Claude Opus 4.7
   (custom provider)            (phase 1/2 route,              (official OpenAI-SDK-
                                 our most-tested path)          compatible endpoint)
```

Why not nanobot's `anthropic` provider direct to the gateway's `/v1/messages`? Because nanobot's `anthropic` provider doesn't expose an `apiBase` override. Instead we use Anthropic's first-class [OpenAI SDK compatibility endpoint](https://platform.claude.com/docs/en/api/openai-sdk) at `https://api.anthropic.com/v1/`, which accepts the OpenAI chat-completions wire format and fully supports tool-calling. Everything rides the gateway's most-exercised code path.

---

## What this folder contains

```
bench/nanobot/
├── README.md              ← this file
├── gateway-off.toml       ← jmunch runs, but interception is disabled
├── gateway-on.toml        ← jmunch runs with interception (only diff: 2 lines)
├── nanobot.config.json    ← drop at ~/.nanobot/config.json
├── prompt.txt             ← the demo prompt
└── run.sh                 ← automated before/after, writes results.csv
```

The two `.toml` files are **byte-identical except the two `[interception]` lines**. That's the demo's whole trick — rules out "maybe the proxy is doing some other compression" as an alternative explanation.

---

## Pre-flight (do this at work, before recording)

### 1. Install everything

```bash
pip install 'jmunch-mcp[gateway,exact-tokens]'
pip install nanobot-ai
# MCP server for the fat payload — no API key needed:
#   uvx comes with `uv`; if you don't have it: pip install uv
uvx mcp-server-fetch --help    # ensures it downloads OK
```

### 2. Export your Anthropic key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

That's it — no second account, no OpenRouter, no extra credit. Total Claude spend for both demo runs: well under \$0.05.

### 3. Install the nanobot config

```bash
mkdir -p ~/.nanobot
cp bench/nanobot/nanobot.config.json ~/.nanobot/config.json
```

### 4. Smoke-test the plumbing (no LLM call)

```bash
# Terminal 1
jmunch-mcp gateway --config bench/nanobot/gateway-on.toml

# Terminal 2
curl http://127.0.0.1:7879/health
# → {"status":"ok","upstreams":["anthropic"],"tokens_saved_total":0}
```

If `curl` gets a response, jmunch is wired. Kill it (Ctrl-C) and move on.

### 5. Smoke-test nanobot → jmunch → Anthropic

```bash
# Terminal 1 still running gateway-on.toml:
# Terminal 2:
nanobot agent --message "say hi in five words" --no-logs
```

If Claude replies, the whole chain works. If you get a 401, your `ANTHROPIC_API_KEY` is bad — fix that before anything else.

---

## The demo recording (at home, ~90 seconds of video)

**Layout on screen:** two terminals side-by-side; a browser tab open to `http://127.0.0.1:7878` (the jmunch dashboard).

**Shot list:**

1. **Setup (10s, silent)** — show `gateway-off.toml` side-by-side with `gateway-on.toml`. Highlight that the only diff is two lines. *"Same proxy. Same plumbing. One flag."*

2. **Baseline (30s)** — run the demo script:

   ```bash
   ./bench/nanobot/run.sh
   ```

   It runs both configs back-to-back, writes `results.csv`, and prints the summary. Tab to the dashboard at `http://127.0.0.1:7878?surface=gateway` during each run.

   Or, for a more hand-operated feel, record it manually:

   ```bash
   # Terminal A
   jmunch-mcp dashboard --open              # opens browser tab

   # Terminal B
   jmunch-mcp gateway --config bench/nanobot/gateway-off.toml

   # Terminal C
   nanobot agent --message "$(cat bench/nanobot/prompt.txt)"
   # ... Claude produces the answer. Switch to dashboard tab.
   # Dashboard shows ~30K tokens went through, 0 saved.
   ```

3. **The flip (5s)** — kill the gateway (Ctrl-C). Change one command:

   ```bash
   jmunch-mcp gateway --config bench/nanobot/gateway-on.toml
   #                                       ^^^^^^^^^^^^^^^
   ```

4. **After (30s)** — rerun nanobot with the exact same prompt:

   ```bash
   nanobot agent --message "$(cat bench/nanobot/prompt.txt)"
   ```

   Claude produces the same answer. Switch to the dashboard tab. Now it shows ~30K raw, ~1K sent, **~96% saved**. Money shot.

5. **Outro (15s)** — flash `results.csv` on screen or the `run.sh` summary line:
   > `saved: 96.5%`

   Call out: *"One flag. Works with any agent framework that speaks OpenAI-compat. Next video: same demo with LangChain, Aider, Continue."*

---

## How the auth flow works (in case a viewer asks)

nanobot sends `Authorization: Bearer sk-dummy-jmunch-injects-the-real-key` to jmunch (the value of `apiKey` in its config — a placeholder). The jmunch gateway's `OpenAIUpstream` ignores that header entirely and builds its own `Authorization: Bearer $ANTHROPIC_API_KEY` when forwarding to Anthropic. The dummy key never leaves your machine; the real one never touches nanobot's config file.

---

## Troubleshooting

**`uvx mcp-server-fetch` fails / times out**

  - Install uv: `pip install uv`. The fetch MCP is also available as `pip install mcp-server-fetch`; then change `nanobot.config.json` to `"command": "mcp-server-fetch"` with empty args.

**nanobot error: "provider custom not recognized"**

  - Some nanobot versions insist on a specific provider name. Try renaming `"custom"` → `"openai"` in `nanobot.config.json` and keeping `apiBase` under that key. nanobot uses the provider name only as a config key; the wire protocol is inferred from `apiBase`.

**nanobot hangs or fails with 401 on the first run**

  - Check the gateway terminal's stderr for the real response body. If it says "invalid x-api-key" or similar, Anthropic rejected jmunch's key — verify `ANTHROPIC_API_KEY` is exported in the **terminal that started jmunch**, not the one running nanobot.

**Claude produces a great answer from the summary alone (never calls `jmunch_peek`)**

  - The demo still works — tokens still dropped — but the "drilled in with real dates" proof is softer. Tighten the `_hint` string in `src/jmunch_mcp/gateway/handleify.py` to explicitly demand a `jmunch_peek` call before answering, and rerun. Two other options: raise `threshold_tokens` so only *really* fat payloads trip (more realistic "must drill in" pressure), or pick a prompt that demands specific extractable facts rather than a summary (the current prompt already does — "three specific dates" forces extraction).

**"saved: 0%"**

  - The Wikipedia page came back smaller than 1500 tokens (~6KB). Unusual for the SQLite article, but possible. Pick a longer page — swap the URL to `https://en.wikipedia.org/wiki/History_of_Linux` in `prompt.txt`.

**The run.sh script freezes waiting for `nanobot agent`**

  - Confirm `--message` is one-shot on your nanobot version: `nanobot agent --help | grep -A2 message`. If the version ignores it, wrap the call in a timeout inside `run.sh` or use an older/newer nanobot.

**"model 'claude-opus-4-7' not found"**

  - Anthropic's model slugs evolve. Check [the models index](https://docs.anthropic.com/en/about-claude/models/overview) for current names. Common options: `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-opus-4-6`. Update the `model` field in `nanobot.config.json`.

**Anthropic returns a tool-calling feature-support error**

  - The OpenAI-compat layer supports `tools` / `tool_calls` fully, per their docs, but `strict: true` on function schemas is ignored. jmunch doesn't set `strict`, so this shouldn't bite — but if a future nanobot version does, the fix is to scrub `strict` in the gateway's tool injection layer.

---

## The one-paragraph pitch (for the video description)

> jmunch-mcp is a transparent token-saving proxy for AI applications. Point any OpenAI- or Anthropic-compatible app at it and watch fat tool-call payloads get replaced with opaque handles + tiny summaries. The model transparently drills in with `jmunch_peek` / `slice` / `search` / `aggregate`. Same answers, **88–99% fewer tokens**, one config line to opt in. This video: nanobot + a Wikipedia scrape + Claude Opus 4.7, **96% saved**. See jgravelle/jmunch-mcp.
