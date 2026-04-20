"""Probe a single tools/call to GitHub MCP."""
from __future__ import annotations

import asyncio
import json
import os
import sys


async def main() -> int:
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    proc = await asyncio.create_subprocess_exec(
        "npx.cmd", "-y", "@modelcontextprotocol/server-github",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr, env=env,
    )

    async def send(msg):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()

    async def recv(want_id):
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=45)
            if not line:
                raise RuntimeError("EOF")
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("id") == want_id:
                return line, m

    await send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "p", "version": "0"}}})
    await recv(1)
    await send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "list_issues", "arguments": {"owner": "facebook", "repo": "react", "state": "all", "perPage": 100}}}
    await send(call)
    print("sent list_issues, waiting...", file=sys.stderr, flush=True)
    line, msg = await recv(2)
    print(f"got {len(line)} bytes", file=sys.stderr, flush=True)
    # Print first 400 chars of text content
    try:
        txt = msg["result"]["content"][0]["text"]
        print(f"text len={len(txt)}")
        print(txt[:300])
    except Exception as e:
        print(f"unexpected shape: {e}")
        print(json.dumps(msg)[:500])

    proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
