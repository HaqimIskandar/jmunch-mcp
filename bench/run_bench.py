"""Run a benchmark script against an MCP upstream, twice:

  1. Directly, to establish a baseline (raw response bytes).
  2. Through jmunch-mcp, to measure savings (handle-ified responses + a
     few realistic follow-up verb calls).

Prints a markdown table sized in bytes and tokens (bytes/4 per jMRI).

Usage:
    python -m bench.run_bench --config bench/github.toml

The config is the same format jmunch-mcp consumes. We reuse the upstream
block to drive the direct-call baseline so there's no drift between runs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Allow `python bench/run_bench.py` without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jmunch_mcp.config import load as load_config  # noqa: E402

from .scripts import (  # noqa: E402
    FIRECRAWL_CALLS,
    GITHUB_CALLS,
    JMUNCH_FOLLOWUPS,
    JMUNCH_FOLLOWUPS_JSON,
)

SUITES = {
    "github": (GITHUB_CALLS, JMUNCH_FOLLOWUPS),
    "firecrawl": (FIRECRAWL_CALLS, JMUNCH_FOLLOWUPS_JSON),
}


BYTES_PER_TOKEN = 4


@dataclass
class CallResult:
    label: str
    response_bytes: int
    ok: bool
    note: str = ""


@dataclass
class RunTotals:
    name: str
    calls: list[CallResult] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(c.response_bytes for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return self.total_bytes // BYTES_PER_TOKEN


class MCPClient:
    """Minimal MCP stdio client: initialize handshake + request/response by id."""

    def __init__(self, command: str, args: list[str], env: dict[str, str]) -> None:
        self.command = command
        self.args = args
        self.env = env
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def start(self) -> None:
        merged_env = {k: v for k, v in {**os.environ, **self.env}.items() if isinstance(v, str)}
        # Windows: npx/npm are .cmd shims that CreateProcess can't exec directly.
        cmd, args = self.command, list(self.args)
        if sys.platform == "win32" and cmd.lower() in ("npx", "npm", "node"):
            cmd = cmd + ".cmd" if not cmd.endswith(".cmd") else cmd
        self.proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=merged_env,
            limit=16 * 1024 * 1024,
        )
        await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jmunch-bench", "version": "0.0.1"},
        })
        await self._notify("notifications/initialized", {})

    async def stop(self) -> None:
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()

    async def tools_call(self, name: str, arguments: dict) -> tuple[bytes, dict]:
        """Return (raw response line bytes, parsed message)."""
        return await self._request_raw("tools/call", {"name": name, "arguments": arguments})

    async def _notify(self, method: str, params: dict) -> None:
        frame = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        self.proc.stdin.write(frame.encode("utf-8"))
        await self.proc.stdin.drain()

    async def _request(self, method: str, params: dict) -> dict:
        _, msg = await self._request_raw(method, params)
        return msg

    async def _request_raw(self, method: str, params: dict) -> tuple[bytes, dict]:
        msg_id = self._next_id
        self._next_id += 1
        frame = json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}) + "\n"
        self.proc.stdin.write(frame.encode("utf-8"))
        await self.proc.stdin.drain()
        # Read lines until we see our id. Some servers emit log/notifications first.
        while True:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=60)
            if not line:
                raise RuntimeError(f"upstream EOF waiting for id={msg_id}")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == msg_id:
                return line, msg


def extract_handle_id(msg: dict) -> str | None:
    """If this response is a jmunch handle-ified payload, return its id."""
    try:
        text = msg["result"]["content"][0]["text"]
        inner = json.loads(text)
        result = inner.get("result") or {}
        h = result.get("handle")
        return h if isinstance(h, str) else None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


async def run_direct(config_path: str, calls) -> RunTotals:
    cfg = load_config(config_path)
    client = MCPClient(cfg.upstream.command, list(cfg.upstream.args), dict(cfg.upstream.env))
    totals = RunTotals(name="direct (no proxy)")
    await client.start()
    try:
        for label, tool, args in calls:
            try:
                raw, _ = await client.tools_call(tool, args)
                totals.calls.append(CallResult(label, len(raw), True))
            except Exception as e:
                totals.calls.append(CallResult(label, 0, False, note=str(e)[:80]))
    finally:
        await client.stop()
    return totals


async def run_proxied(config_path: str, calls, followups) -> RunTotals:
    totals = RunTotals(name="through jmunch-mcp")
    client = MCPClient(
        sys.executable,
        ["-m", "jmunch_mcp", "--config", config_path],
        {"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
    )
    await client.start()
    last_handle: str | None = None
    try:
        for label, tool, args in calls:
            try:
                raw, msg = await client.tools_call(tool, args)
                totals.calls.append(CallResult(label, len(raw), True))
                hid = extract_handle_id(msg)
                if hid:
                    last_handle = hid
            except Exception as e:
                totals.calls.append(CallResult(label, 0, False, note=str(e)[:80]))

        if last_handle is None:
            totals.calls.append(CallResult(
                "(no handles created — all responses below threshold)", 0, False,
            ))
        else:
            for label, tool, args in followups:
                resolved = {k: (last_handle if v == "$LAST_HANDLE" else v) for k, v in args.items()}
                try:
                    raw, _ = await client.tools_call(tool, resolved)
                    totals.calls.append(CallResult(label, len(raw), True))
                except Exception as e:
                    totals.calls.append(CallResult(label, 0, False, note=str(e)[:80]))
    finally:
        await client.stop()
    return totals


def render_report(direct: RunTotals, proxied: RunTotals) -> str:
    lines = []
    lines.append("# jmunch-mcp benchmark\n")
    for run in (direct, proxied):
        lines.append(f"## {run.name}\n")
        lines.append("| call | response bytes | ~tokens |")
        lines.append("|---|---:|---:|")
        for c in run.calls:
            tok = c.response_bytes // BYTES_PER_TOKEN
            status = "" if c.ok else f" ❌ {c.note}"
            lines.append(f"| {c.label}{status} | {c.response_bytes:,} | {tok:,} |")
        lines.append(f"| **total** | **{run.total_bytes:,}** | **{run.total_tokens:,}** |\n")

    saved_bytes = direct.total_bytes - proxied.total_bytes
    saved_tokens = saved_bytes // BYTES_PER_TOKEN
    pct = (saved_bytes / direct.total_bytes * 100) if direct.total_bytes else 0.0
    lines.append("## delta\n")
    lines.append(f"- bytes saved: **{saved_bytes:,}** ({pct:.1f}%)")
    lines.append(f"- tokens saved: **~{saved_tokens:,}** (bytes / 4)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="jmunch-bench")
    parser.add_argument("--config", required=True)
    parser.add_argument("--suite", default="github", choices=sorted(SUITES))
    parser.add_argument("--out", default=None, help="Write markdown report to this path")
    args = parser.parse_args()

    calls, followups = SUITES[args.suite]

    t0 = time.perf_counter()
    direct = asyncio.run(run_direct(args.config, calls))
    t1 = time.perf_counter()
    proxied = asyncio.run(run_proxied(args.config, calls, followups))
    t2 = time.perf_counter()

    report = render_report(direct, proxied)
    report += f"\n\n_timings: direct={t1-t0:.1f}s, proxied={t2-t1:.1f}s_\n"

    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
