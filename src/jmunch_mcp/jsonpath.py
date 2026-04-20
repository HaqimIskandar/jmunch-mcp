"""Minimal JSONPath interpreter — zero deps, small attack surface.

Supported syntax (deliberately a subset — covers ~95% of agent queries):

    $                  root
    .field             child (dot notation; field must be a bare identifier)
    ['field']          child (bracket notation; any string)
    ["field"]          child (double-quoted)
    [n]                array index (n >= 0)
    [*]                wildcard over array or dict values
    ..field            recursive descent to any `field` under the current node
    ..[*]              recursive descent yielding every value in the subtree

Returns: list of (path, value) pairs, where `path` is a human-readable
dotted/bracketed string like `$.items[3].name`.

Not supported (by design — file a ticket if you need these): filter
expressions `[?(...)]`, slices `[a:b]`, unions `[a,b]`, functions. If/when
we need them, swap for jsonpath-ng behind the same API.
"""
from __future__ import annotations

import re
from typing import Any

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class JSONPathError(ValueError):
    pass


def compile_path(expr: str) -> list[tuple[str, Any]]:
    """Tokenize a JSONPath expression into a list of (op, arg) steps.

    Ops: "root", "field", "index", "wildcard", "descend_field", "descend_any".
    """
    if not expr or expr[0] != "$":
        raise JSONPathError("JSONPath must start with '$'")
    i = 1
    steps: list[tuple[str, Any]] = [("root", None)]
    n = len(expr)
    while i < n:
        c = expr[i]
        if c == ".":
            if i + 1 < n and expr[i + 1] == ".":
                # Recursive descent: ..field or ..[*]
                i += 2
                if i < n and expr[i] == "[":
                    # ..[*] — descend to all nodes
                    j, arg = _read_bracket(expr, i)
                    if arg != ("wildcard", None):
                        raise JSONPathError("recursive descent supports '..[*]' or '..field' only")
                    steps.append(("descend_any", None))
                    i = j
                else:
                    m = _IDENT.match(expr, i)
                    if not m:
                        raise JSONPathError(f"expected field after '..' at col {i}")
                    steps.append(("descend_field", m.group(0)))
                    i = m.end()
            else:
                i += 1
                m = _IDENT.match(expr, i)
                if not m:
                    raise JSONPathError(f"expected field name after '.' at col {i}")
                steps.append(("field", m.group(0)))
                i = m.end()
        elif c == "[":
            j, step = _read_bracket(expr, i)
            steps.append(step)
            i = j
        else:
            raise JSONPathError(f"unexpected character '{c}' at col {i}")
    return steps


def _read_bracket(expr: str, i: int) -> tuple[int, tuple[str, Any]]:
    # Assumes expr[i] == '['
    end = expr.find("]", i)
    if end == -1:
        raise JSONPathError(f"unterminated '[' at col {i}")
    body = expr[i + 1:end].strip()
    if body == "*":
        return end + 1, ("wildcard", None)
    if body.isdigit() or (body.startswith("-") and body[1:].isdigit()):
        return end + 1, ("index", int(body))
    if len(body) >= 2 and body[0] == body[-1] and body[0] in ("'", '"'):
        return end + 1, ("field", body[1:-1])
    raise JSONPathError(f"unsupported bracket expression '{body}'")


def query(root: Any, expr: str) -> list[tuple[str, Any]]:
    """Evaluate `expr` against `root`. Returns [(path_str, value), ...]."""
    steps = compile_path(expr)
    current: list[tuple[str, Any]] = [("$", root)]
    for op, arg in steps:
        if op == "root":
            continue
        current = list(_apply_step(current, op, arg))
    return current


def _apply_step(nodes, op: str, arg):
    for path, value in nodes:
        if op == "field":
            if isinstance(value, dict) and arg in value:
                yield _join_field(path, arg), value[arg]
        elif op == "index":
            if isinstance(value, list):
                idx = arg if arg >= 0 else len(value) + arg
                if 0 <= idx < len(value):
                    yield f"{path}[{idx}]", value[idx]
        elif op == "wildcard":
            if isinstance(value, list):
                for i, v in enumerate(value):
                    yield f"{path}[{i}]", v
            elif isinstance(value, dict):
                for k, v in value.items():
                    yield _join_field(path, k), v
        elif op == "descend_field":
            for p, v in _walk(path, value):
                if isinstance(v, dict) and arg in v:
                    yield _join_field(p, arg), v[arg]
        elif op == "descend_any":
            for p, v in _walk(path, value):
                yield p, v


def _walk(path: str, value: Any):
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(_join_field(path, k), v)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(f"{path}[{i}]", v)


def _join_field(path: str, field: str) -> str:
    if _IDENT.fullmatch(field):
        return f"{path}.{field}"
    # Escape embedded single quotes
    safe = field.replace("'", "\\'")
    return f"{path}['{safe}']"
