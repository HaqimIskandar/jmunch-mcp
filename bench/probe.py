"""Minimal handshake probe — spawns upstream, does initialize, prints response."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def main() -> int:
    env = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    proc = await asyncio.create_subprocess_exec(
        "npx.cmd",
        "-y",
        "@modelcontextprotocol/server-github",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr,
        env=env,
    )
    print(f"spawned pid={proc.pid}", file=sys.stderr, flush=True)

    frame = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "probe", "version": "0"}},
    }) + "\n"
    proc.stdin.write(frame.encode())
    await proc.stdin.drain()
    print("sent initialize", file=sys.stderr, flush=True)

    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        print(f"got line ({len(line)} bytes):", file=sys.stderr, flush=True)
        print(line.decode(errors="replace")[:500])
    except asyncio.TimeoutError:
        print("TIMEOUT waiting for initialize response", file=sys.stderr, flush=True)
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
