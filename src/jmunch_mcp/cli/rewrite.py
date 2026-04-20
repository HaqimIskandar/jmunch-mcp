"""Rewrite an MCP client config so a given `mcpServers` entry launches
jmunch-mcp instead of the upstream directly.

Scope: the common `mcpServers` JSON schema shared by Claude Desktop,
Claude Code, Cursor, and Windsurf. Continue uses a different schema and
is deliberately out of scope for now.

Safety model:
  - Always writes `<config>.bak` on first rewrite, never overwrites an
    existing `.bak` (so restore always goes back to the true original).
  - Idempotent: if an entry is already wrapped (command == jmunch-mcp),
    no-op and return `"already_wrapped"`.
  - Atomic: write to a temp file in the same directory, then rename.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .discovery import Candidate


RewriteStatus = Literal[
    "rewrote", "already_wrapped", "not_found", "unsupported",
    "restored", "unwrapped", "no_backup", "not_wrapped",
]


@dataclass
class RewriteResult:
    path: Path
    server_key: str
    status: RewriteStatus
    before: dict | None = None
    after: dict | None = None


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _backup_once(path: Path) -> Path:
    """Write `<path>.bak` only if it doesn't already exist. Returns the bak path."""
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(path, bak)
    return bak


def _wrapped_entry(toml_path: Path, original: dict) -> dict:
    """Build the replacement mcpServers entry. Preserves env (and any other
    non-command/args keys the user may have added)."""
    new = dict(original)  # shallow copy — keeps env, disabled, autoApprove, etc.
    new["command"] = "jmunch-mcp"
    new["args"] = ["--config", str(toml_path)]
    return new


def _servers_container(data: dict, source_project: str) -> dict | None:
    """Return the mcpServers dict for this candidate's scope, or None."""
    if source_project:
        projects = data.get("projects")
        if not isinstance(projects, dict):
            return None
        proj = projects.get(source_project)
        if not isinstance(proj, dict):
            return None
        servers = proj.get("mcpServers")
        return servers if isinstance(servers, dict) else None
    servers = data.get("mcpServers")
    return servers if isinstance(servers, dict) else None


def plan_rewrite(
    candidate: Candidate,
    toml_path: Path,
) -> RewriteResult:
    """Compute what the rewrite would do without touching disk.

    Returns a result whose `before` and `after` fields show the exact
    mcpServers entry diff. `status` is `"rewrote"` if a change would
    happen, `"already_wrapped"` if no-op, `"not_found"` if the key is
    gone, or `"unsupported"` if the file schema doesn't match.
    """
    if not candidate.source_path or not candidate.server_key:
        return RewriteResult(path=Path(), server_key="", status="unsupported")

    data = _load(candidate.source_path)
    if not isinstance(data, dict):
        return RewriteResult(path=candidate.source_path, server_key=candidate.server_key,
                             status="unsupported")
    servers = _servers_container(data, candidate.source_project)
    if servers is None:
        return RewriteResult(path=candidate.source_path, server_key=candidate.server_key,
                             status="unsupported")
    original = servers.get(candidate.server_key)
    if not isinstance(original, dict):
        return RewriteResult(path=candidate.source_path, server_key=candidate.server_key,
                             status="not_found")
    if original.get("command") == "jmunch-mcp":
        return RewriteResult(path=candidate.source_path, server_key=candidate.server_key,
                             status="already_wrapped", before=original, after=original)

    after = _wrapped_entry(toml_path, original)
    return RewriteResult(path=candidate.source_path, server_key=candidate.server_key,
                         status="rewrote", before=original, after=after)


def apply_rewrite(
    candidate: Candidate,
    toml_path: Path,
) -> RewriteResult:
    """Execute the rewrite. Writes `.bak` once, then atomically replaces the config."""
    result = plan_rewrite(candidate, toml_path)
    if result.status != "rewrote":
        return result

    data = _load(candidate.source_path)  # type: ignore[arg-type]
    assert isinstance(data, dict)
    _backup_once(candidate.source_path)  # type: ignore[arg-type]
    servers = _servers_container(data, candidate.source_project)
    assert servers is not None  # plan_rewrite would have said unsupported
    servers[candidate.server_key] = result.after
    _atomic_write_json(candidate.source_path, data)  # type: ignore[arg-type]
    return result


def restore(path: Path) -> RewriteResult:
    """Restore `path` from its `.bak` sibling, if one exists.

    Wholesale restore — undoes every wrap in the file. Prefer `unwrap_entry`
    when you want to revert just one server.
    """
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        return RewriteResult(path=path, server_key="", status="not_found")
    shutil.copy2(bak, path)
    return RewriteResult(path=path, server_key="", status="restored")


def unwrap_entry(
    config_path: Path, server_key: str, source_project: str = "",
) -> RewriteResult:
    """Revert a single server entry back to its pre-wrap shape.

    Uses the `.bak` sibling as a frozen reference for the original entry,
    so other entries in the file (wrapped or not) are left untouched. This
    is what the dashboard's "Optimized off" toggle calls.
    """
    live = _load(config_path)
    if not isinstance(live, dict):
        return RewriteResult(path=config_path, server_key=server_key, status="unsupported")
    live_servers = _servers_container(live, source_project)
    if live_servers is None:
        return RewriteResult(path=config_path, server_key=server_key, status="unsupported")
    current = live_servers.get(server_key)
    if not isinstance(current, dict):
        return RewriteResult(path=config_path, server_key=server_key, status="not_found")
    if current.get("command") != "jmunch-mcp":
        return RewriteResult(path=config_path, server_key=server_key, status="not_wrapped")

    bak = config_path.with_suffix(config_path.suffix + ".bak")
    if not bak.exists():
        return RewriteResult(path=config_path, server_key=server_key, status="no_backup")
    bak_data = _load(bak)
    if not isinstance(bak_data, dict):
        return RewriteResult(path=config_path, server_key=server_key, status="no_backup")
    bak_servers = _servers_container(bak_data, source_project) or {}
    original = bak_servers.get(server_key)

    if isinstance(original, dict):
        # Wrapped an existing entry — restore it.
        live_servers[server_key] = original
        _atomic_write_json(config_path, live)
        return RewriteResult(path=config_path, server_key=server_key, status="unwrapped",
                             before=current, after=original)

    # .bak exists but has no such entry — we installed it (added a brand-new
    # entry that didn't exist pre-wrap). The inverse is to remove it.
    del live_servers[server_key]
    _atomic_write_json(config_path, live)
    return RewriteResult(path=config_path, server_key=server_key, status="unwrapped",
                         before=current, after=None)


def render_diff(result: RewriteResult) -> str:
    """Human-readable preview: just the before/after of the one entry."""
    if result.status != "rewrote" or result.before is None or result.after is None:
        return f"  ({result.status})"
    lines = [f"  {result.path}  [{result.server_key}]"]
    lines.append(f"    - command: {result.before.get('command')!r}")
    lines.append(f"    + command: {result.after.get('command')!r}")
    lines.append(f"    - args:    {result.before.get('args')!r}")
    lines.append(f"    + args:    {result.after.get('args')!r}")
    return "\n".join(lines)
