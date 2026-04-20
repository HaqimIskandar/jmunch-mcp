"""List tools from GitHub MCP to confirm names."""
from __future__ import annotations

import asyncio
import json
import os
import sys


async def main() -> int:
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    proc = await asyncio.create_subprocess_exec(
        "npx.cmd", "-y", "@modelcontextprotocol/server-github",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr,
        env=env,
    )

    async def send(msg):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()

    async def recv(want_id):
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
            if not line:
                raise RuntimeError("EOF")
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("id") == want_id:
                return m

    await send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "p", "version": "0"}}})
    await recv(1)
    await send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    resp = await recv(2)
    tools = resp.get("result", {}).get("tools", [])
    print(f"{len(tools)} tools:")
    for t in tools[:50]:
        print(f"  {t['name']}")

    proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
