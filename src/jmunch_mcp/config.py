"""Config loading for jmunch-mcp.

M0: only `upstream.command` / `upstream.args` / `upstream.env` are read.
Threshold, eviction, backend toggles are declared but inert until M1+.
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UpstreamConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    upstream: UpstreamConfig
    threshold_tokens: int = 2000
    log_level: str = "INFO"
    report: bool = False


def load(path: str | os.PathLike) -> Config:
    p = Path(path)
    raw = p.read_bytes()
    data = tomllib.loads(raw.decode("utf-8")) if p.suffix == ".toml" else json.loads(raw)

    up = data.get("upstream") or {}
    if "command" not in up:
        raise ValueError(f"{p}: [upstream].command is required")

    return Config(
        upstream=UpstreamConfig(
            command=up["command"],
            args=list(up.get("args", [])),
            env=dict(up.get("env", {})),
        ),
        threshold_tokens=int(data.get("threshold_tokens", 2000)),
        log_level=str(data.get("log_level", "INFO")),
        report=bool(data.get("report", False)),
    )
