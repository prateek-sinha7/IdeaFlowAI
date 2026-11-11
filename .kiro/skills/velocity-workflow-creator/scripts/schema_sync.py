#!/usr/bin/env python3
"""Keep the manifest JSON Schema in step with the catalog snapshot.

The schema's enum lists (capability names, MCP tools, integration scopes, effort
levels, ...) and the registry counts quoted in its `$comment` text come from the
catalog (`references/catalog.json`). This module rewrites exactly those parts and
leaves every hand-written description alone.

Used by `refresh_catalog.py` (every mode) and `selftest.py`. Run directly to sync or
check on its own:

  python schema_sync.py              # rewrite the schema from references/catalog.json
  python schema_sync.py --check      # exit 1 when the schema is out of date (no write)

Rules:
  * A retained name keeps its position; new names are appended in alphabetical order.
  * Nothing is ever written from an empty list (an empty enum rejects every value);
    that binding is skipped with a warning.
  * Names that are new or gone are reported so you can update the prose that
    explains them (field descriptions are hand-written).

Stdlib only.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = SKILL_DIR / "references" / "catalog.json"
DEFAULT_SCHEMA = SKILL_DIR / "schema" / "workflow-manifest.schema.json"
WIDTH = 100


# ───────────────────────────────────────────────────────────────── formatter


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _inline(value: Any) -> str | None:
    """One-line form of a value, or None when it must be expanded."""
    if _is_scalar(value):
        return _scalar(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            text = _inline(item)
            if text is None:
                return None
            parts.append(text)
        return "[" + ", ".join(parts) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        if "description" in value or "$comment" in value:
            return None  # prose is never squeezed onto one line
        parts = []
        for key, item in value.items():
            text = _inline(item)
            if text is None:
                return None
            parts.append(f"{_scalar(key)}: {text}")
        return "{ " + ", ".join(parts) + " }"
    return _scalar(value)


def _dump(value: Any, indent: int, lead: int) -> str:
    """Serialize `value`; `lead` is the text width already on its first line."""
    one = _inline(value)
    if one is not None and lead + len(one) <= WIDTH:
        return one
    pad = "  " * indent
    inner = "  " * (indent + 1)
    if isinstance(value, dict) and value:
        lines = []
        for key, item in value.items():
            key_text = _scalar(key)
            lines.append(f"{inner}{key_text}: {_dump(item, indent + 1, len(inner) + len(key_text) + 2)}")
        return "{\n" + ",\n".join(lines) + "\n" + pad + "}"
    if isinstance(value, list) and value:
        if all(_is_scalar(item) for item in value):
            rows: list[str] = []
            current = ""
            for item in value:
                token = _scalar(item) + ","
                if current and len(inner) + len(current) + 1 + len(token) > WIDTH:
                    rows.append(current)
                    current = token
                else:
                    current = f"{current} {token}" if current else token
            rows.append(current)
            rows[-1] = rows[-1].rstrip(",")
            return "[\n" + "\n".join(inner + row for row in rows) + "\n" + pad + "]"
        lines = [inner + _dump(item, indent + 1, len(inner)) for item in value]
        return "[\n" + ",\n".join(lines) + "\n" + pad + "]"
    return one if one is not None else _scalar(value)


def dump_schema(schema: Any) -> str:
    """Stable, readable JSON text for the schema (same input, same bytes)."""
    return _dump(schema, 0, 0) + "\n"


# ──────────────────────────────────────────────────────────────── bindings


@dataclass(frozen=True)
class Binding:
    field: tuple  # path to the property node (holds `$comment`; `items` below it for arrays)
    array: bool  # the enum sits under field/items
    source: str  # where the values come from, see derive()
    nullable: bool = False  # keep a trailing null in the enum
    kind: str | None = None  # registry kind quoted in the `$comment` opener
    noun: str = "names"
    mode: str = "standard"  # standard | tool | mcp: shape of the generated trust sentence


STEP = ("$defs", "stepBase", "properties")
PERM = ("$defs", "toolPermissions", "properties")

BINDINGS = (
    Binding(("properties", "context_providers"), True, "cap:context_provider", kind="context_provider"),
    Binding(("properties", "input_providers"), True, "cap:input_provider", kind="input_provider"),
    Binding(("$defs", "deliverable", "properties", "strategy"), False, "cap:deliverable", kind="deliverable"),
    Binding(PERM + ("tool_sets",), True, "cap:tool", kind="tool", noun="sets", mode="tool"),
    Binding(PERM + ("mcp",), True, "mcp_tools", kind="mcp_server", noun="servers", mode="mcp"),
    Binding(PERM + ("integrations",), True, "scopes", kind="integration_provider", noun="providers"),
    Binding(("$defs", "taskSource", "properties", "parser"), False, "cap:task_parser", nullable=True),
    Binding(STEP + ("strategy",), False, "cap:strategy", kind="strategy"),
    Binding(STEP + ("mechanical",), False, "mechanical", nullable=True),
    Binding(STEP + ("gates",), True, "cap:gate", kind="gate"),
    Binding(STEP + ("validators",), True, "cap:validator", kind="validator"),
    Binding(STEP + ("hooks",), True, "cap:hook", kind="hook"),
    Binding(STEP + ("compaction",), False, "cap:compaction", nullable=True, kind="compaction"),
    Binding(STEP + ("post_step",), False, "cap:post_step", nullable=True, kind="post_step"),
    Binding(STEP + ("on_conflict",), False, "on_conflict"),
    Binding(("$defs", "modelPolicy", "properties", "effort"), False, "effort"),
)


def derive(catalog: dict, source: str) -> list[str]:
    """Catalog values for a binding source (sorted, no duplicates)."""
    caps = catalog.get("capabilities") or {}
    if source.startswith("cap:"):
        return sorted(caps.get(source[4:]) or {})
    if source == "mcp_tools":
        out = []
        for server, entry in sorted((catalog.get("mcp_servers") or {}).items()):
            out.extend(f"{server}.{tool}" for tool in sorted(entry.get("tools") or []))
        return out
    if source == "scopes":
        return sorted(catalog.get("integration_scopes") or {})
    if source == "mechanical":
        return sorted((catalog.get("limits") or {}).get("mechanical_kinds") or [])
    if source == "on_conflict":
        return sorted((catalog.get("limits") or {}).get("on_conflict") or [])
    if source == "effort":
        # Effort levels are an ordered scale (none < low < ... < max), so keep that order,
        # not alphabetical. 'on' is the extra level adaptive/budget Claude models accept.
        levels = list(catalog.get("reasoning_effort_levels") or [])
        for model in catalog.get("models") or []:
            reasoning = model.get("reasoning") or {}
            levels.extend(x for x in reasoning.get("levels") or [] if x not in levels)
            if reasoning.get("mode") in ("adaptive", "budget") and "on" not in levels:
                levels.append("on")
        return levels
    raise KeyError(source)


def merge_order(existing: list, wanted: list[str]) -> list:
    """Retained names keep their place; new names are appended."""
    kept = [x for x in existing if x in wanted]
    return kept + [x for x in wanted if x not in kept]


# ───────────────────────────────────────────────────────────── $comment text

OPENER_RE = re.compile(r"Registry kind '[^']+' \([^)]*\)\.")
# Matches the sentences this module writes AND the hand-written ones the schema shipped with,
# so the first sync replaces them instead of duplicating them.
TRUST_RE = re.compile(
    r" ?(?:All names are allowed at user trust\."
    r"|User trust may not use: [^.]*\.(?: Saved workflows may still use: [^.]*\.)?"
    r"|Trust caps decide here instead of user_allowed: [^.]*\. Any other set silently resolves away\."
    r"|Powerful servers \([^)]*\) need [^.]*\."
    r"|Not user_allowed: [^.(]*(?:\([^)]*\))?\."
    r"|Neither is user_allowed \([^)]*\)\."
    r"|Intersected with the trust cap, which decides here instead of user_allowed: [^.]*\."
    r"|[a-z_ ,]+ (?:is|are) powerful: they require gate 'security' plus a 'secrets' grant, and are not user_allowed\.)"
)
REGISTRY_RE = re.compile(r"CAPABILITY REGISTRY: .*? Kinds a manifest can name:", re.S)
SYNCED_RE = re.compile(r"(?:Synced with the catalog snapshot \([^)]*\)\.|Generated from the code on branch [^@]*@ [^.]*\.)")


def _join(items: list[str]) -> str:
    return ", ".join(items)


def trust_sentence(binding: Binding, catalog: dict) -> str:
    rows = (catalog.get("capabilities") or {}).get(binding.kind or "", {})
    if binding.mode == "tool":
        caps = (catalog.get("trust") or {}).get("caps") or {}
        levels = (catalog.get("trust") or {}).get("levels") or {}
        every = set(rows)
        parts = []
        for cap_name in dict.fromkeys(levels.values()):
            sets = (caps.get(cap_name) or {}).get("tool_sets") or []
            who = "/".join(level for level, c in levels.items() if c == cap_name)
            parts.append(f"{who} trust keeps " + ("every set" if every <= set(sets) else "only " + _join(sets)))
        if not parts:
            return ""
        return "Trust caps decide here instead of user_allowed: " + "; ".join(parts) + ". Any other set silently resolves away."
    if binding.mode == "mcp":
        powerful = sorted(n for n, e in (catalog.get("mcp_servers") or {}).items() if e.get("powerful"))
        if not powerful:
            return ""
        return f"Powerful servers ({_join(powerful)}) need gate 'security' plus a 'secrets' grant and are not user_allowed."
    blocked = sorted(n for n, r in rows.items() if not r.get("user_allowed"))
    if not blocked:
        return "All names are allowed at user trust."
    saved = [n for n in blocked if rows[n].get("saved_workflow_allowed")]
    text = f"User trust may not use: {_join(blocked)}."
    if saved:
        text += f" Saved workflows may still use: {_join(saved)}."
    return text


def rewrite_comment(comment: str, binding: Binding, catalog: dict) -> str | None:
    """Regenerate the opener and trust sentence; None when the opener is missing."""
    match = OPENER_RE.search(comment)
    if not match or not binding.kind:
        return None
    count = len((catalog.get("capabilities") or {}).get(binding.kind, {}))
    opener = f"Registry kind '{binding.kind}' ({count} {binding.noun})."
    trust = trust_sentence(binding, catalog)
    head = TRUST_RE.sub("", comment[: match.start()])
    tail = TRUST_RE.sub("", comment[match.end():])
    return re.sub(r" {2,}", " ", head + opener + (" " + trust if trust else "") + tail).rstrip()


def rewrite_top_comment(comment: str, catalog: dict) -> str:
    caps = catalog.get("capabilities") or {}
    total = sum(len(v) for v in caps.values())
    api_rows = total - len(caps.get("model_catalog") or {})
    registry = (
        f"CAPABILITY REGISTRY: the catalog snapshot lists {total} capability coordinates in {len(caps)} kinds; "
        f"GET /api/capabilities returns {api_rows} rows because model_catalog:default is expanded into model records. "
        "Kinds a manifest can name:"
    )
    comment = REGISTRY_RE.sub(lambda _m: registry, comment, count=1)
    src = catalog.get("source") or {}
    where = (
        f"{src.get('branch') or '?'} @ {src.get('commit') or '?'}" if src.get("mode") == "source"
        else f"server {src.get('url')}" if src.get("mode") == "api" else "unknown source"
    )
    synced = f"Synced with the catalog snapshot ({where})."
    if SYNCED_RE.search(comment):
        return SYNCED_RE.sub(lambda _m: synced, comment, count=1)
    return comment.rstrip() + " " + synced


# ──────────────────────────────────────────────────────────────────── sync


def _node(schema: Any, path: tuple) -> Any:
    node = schema
    for part in path:
        node = node[part]
    return node


def sync_schema(schema: dict, catalog: dict) -> tuple[dict, list[str], list[str]]:
    """Return (new schema, changes, warnings). The input is not modified."""
    out = copy.deepcopy(schema)
    changes: list[str] = []
    warnings: list[str] = []
    for b in BINDINGS:
        label = "/".join(str(p) for p in b.field[-2:] if p != "properties")
        try:
            field = _node(out, b.field)
            holder = field["items"] if b.array else field
            existing = list(holder["enum"])
        except (KeyError, TypeError):
            warnings.append(f"schema has no enum at {'/'.join(map(str, b.field))}; binding skipped")
            continue
        wanted = derive(catalog, b.source)
        if not wanted:
            warnings.append(f"{label}: the catalog has no values for '{b.source}'; enum left unchanged")
            continue
        names = merge_order([x for x in existing if x is not None], wanted)
        new = names + ([None] if b.nullable else [])
        if sorted(map(str, new)) == sorted(map(str, existing)):
            new = existing  # same members: never reshuffle a hand-ordered list
        if new != existing:
            added = [x for x in wanted if x not in existing]
            removed = [x for x in existing if x is not None and x not in wanted]
            holder["enum"] = new
            bits = ([f"+{_join(added)}"] if added else []) + ([f"-{_join(removed)}"] if removed else [])
            changes.append(f"{label}: {' '.join(bits) or 'reordered'}")
        if b.kind and "$comment" in field:
            text = rewrite_comment(field["$comment"], b, catalog)
            if text is None:
                warnings.append(f"{label}: $comment has no 'Registry kind ...' opener; counts not updated")
            elif text != field["$comment"]:
                field["$comment"] = text
                changes.append(f"{label}: $comment refreshed")
    if "$comment" in out:
        text = rewrite_top_comment(out["$comment"], catalog)
        if text != out["$comment"]:
            out["$comment"] = text
            changes.append("top-level $comment refreshed")
    return out, changes, warnings


def sync_file(schema_path: Path, catalog: dict, write: bool = True) -> tuple[list[str], list[str], bool]:
    """Sync the schema file. Returns (changes, warnings, drifted)."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    new, changes, warnings = sync_schema(schema, catalog)
    text = dump_schema(new)
    current = schema_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    drifted = text != current
    if drifted and write:
        with open(schema_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return changes, warnings, drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--check", action="store_true", help="report drift and exit 1; write nothing")
    args = parser.parse_args(argv)
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        changes, warnings, drifted = sync_file(args.schema, catalog, write=not args.check)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for change in changes:
        print(f"  {change}")
    for warning in warnings:
        print(f"  warning: {warning}")
    if args.check:
        print("schema is out of date" if drifted else "schema is in sync with the catalog")
        return 1 if drifted else 0
    print(f"schema {'rewritten' if drifted else 'already in sync'}: {args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
