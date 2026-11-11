#!/usr/bin/env python3
"""Refresh the Velocity catalog snapshot this skill designs workflows against.

The snapshot lists everything a workflow manifest may name: agents, capabilities
and their trust flags, models and their reasoning levels, MCP tools, step skills
and the predefined workflows. ``validate_manifest.py`` reads the JSON form;
``docs/catalog.md`` is the human-readable rendering of the same data.

Pick ONE mode:

  --source BACKEND_DIR   Rebuild everything from a Velocity backend checkout. Imports its
                         capability registry, model catalog, permission caps, MCP catalog
                         and integration providers, and parses AGENT.md, SKILL.md and
                         workflow.yaml files. Run it with the backend's own interpreter so
                         its dependencies import, for example from the backend folder:
                             uv run python <skill>/scripts/refresh_catalog.py --source .

  --api BASE_URL         Rebuild from a running Velocity server. Reads GET /api/capabilities,
                         /api/agents/library, /api/skills/library and /api/workflows with a
                         bearer token (--token, or the VELOCITY_API_TOKEN environment
                         variable). Fields the API does not expose (agent
                         produces/consumes/tools, trust caps, budget ceilings, MCP tool
                         lists, integration scopes) are kept from the existing snapshot.

  --render               Do not collect anything. Re-render docs/catalog.md and re-sync the
                         schema from the current references/catalog.json. Use it after
                         editing catalog.json by hand (for example to add a tool before the
                         platform release that ships it). The file is checked first.

  --check                Change nothing. Exit 1 if catalog.json is invalid, docs/catalog.md
                         differs from what catalog.json renders, or the schema's enum lists
                         are out of date. Safe for CI.

Every mode except --check also updates the schema (schema/workflow-manifest.schema.json):
its enum lists for capability names, MCP tools, integration scopes and effort levels, and the
counts and trust sentences in its `$comment` text. Use --no-schema to skip that.
After a --source or --api refresh the script prints what changed against the previous
snapshot: add guidance for new names to docs/field-guide.md and
docs/requirements-analysis.md (see docs/extending.md).

Outputs (defaults are inside this skill folder):
  references/catalog.json    machine-readable snapshot
  docs/catalog.md            human-readable tables
  schema/workflow-manifest.schema.json   synced enum lists (unless --no-schema)

Exit code 0 on success, 1 on failure or drift. Stdlib only, except that --source needs
PyYAML (every Velocity backend already depends on it).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema_sync  # noqa: E402  (sibling module: keeps the schema's enum lists in step with the catalog)
from validate_manifest import CATALOG_ICONS  # noqa: E402  (the icon names the catalog card renders)

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JSON = SKILL_DIR / "references" / "catalog.json"
DEFAULT_MD = SKILL_DIR / "docs" / "catalog.md"
DEFAULT_SCHEMA = schema_sync.DEFAULT_SCHEMA

# Capability kinds a manifest can name, in the order the docs present them.
MANIFEST_KINDS = (
    "strategy",
    "deliverable",
    "gate",
    "validator",
    "hook",
    "context_provider",
    "input_provider",
    "task_parser",
    "tool",
    "mechanical",
    "compaction",
    "post_step",
    "mcp_server",
    "integration_provider",
)


def _empty_catalog() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": "",
        "source": {},
        "warnings": [],
        "trust": {},
        "limits": {},
        "capabilities": {},
        "models": [],
        "mcp_servers": {},
        "integration_scopes": {},
        "agents": {},
        "skills": {},
        "workflows": {},
        "reasoning_effort_levels": [],
    }


# --------------------------------------------------------------------------- utils


def _git(cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body) for a markdown file with a leading --- block."""
    if not text.startswith("---"):
        return "", text
    lines = text.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    return "", text


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _iter_steps(steps: list, depth: int = 0) -> Iterator[tuple[dict, int]]:
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step, depth
        sub = step.get("subagents")
        if isinstance(sub, dict):
            yield from _iter_steps(sub.get("steps") or [], depth + 1)


_ASCII = str.maketrans({"\u2014": "-", "\u2013": "-", "\u2192": "->", "\u2026": "...", "\u2018": "'",
                        "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text or "").split()).translate(_ASCII)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _md_cell(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value) if value else "-"
    text = str(value) if value not in (None, "") else "-"
    return text.translate(_ASCII).replace("|", "\\|").replace("\n", " ")


def _kv(mapping: dict) -> str:
    return ", ".join(f"`{k}` {v}" for k, v in (mapping or {}).items()) or "-"


# ---------------------------------------------------------------- source mode


def _workflows_from_source(backend: Path, yaml_mod: Any, catalog: dict) -> None:
    wf_root = backend / "agents" / "workflows"
    if not wf_root.is_dir():
        catalog["warnings"].append(f"no workflows folder at {wf_root}")
        return
    for wf_dir in sorted(p for p in wf_root.iterdir() if p.is_dir()):
        manifest_path = wf_dir / "workflow.yaml"
        if not manifest_path.is_file():
            continue
        try:
            data = yaml_mod.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 — record and continue
            catalog["warnings"].append(f"could not parse {manifest_path}: {exc}")
            continue
        steps = list(_iter_steps(data.get("steps") or []))
        deliverable = data.get("deliverable") or {}
        chained = []
        for entry in data.get("chained_from") or []:
            chained.append(entry.get("id") if isinstance(entry, dict) else str(entry).split(":")[0])
        wf_id = str(data.get("id") or wf_dir.name)
        catalog["workflows"][wf_id] = {
            "name": data.get("name") or "",
            "display_name": data.get("display_name") or "",
            "description": data.get("description") or "",
            "user_launchable": bool(data.get("user_launchable", False)),
            "is_beta": bool(data.get("is_beta", False)),
            "planner": data.get("planner") or "",
            "clarify_mode": (data.get("clarify") or {}).get("mode", ""),
            "deliverable": {
                "strategy": deliverable.get("strategy"),
                "name": deliverable.get("name"),
                "chains_from": bool(deliverable.get("chains_from", False)),
                "revises_existing": bool(deliverable.get("revises_existing", False)),
            },
            "context_providers": list(data.get("context_providers") or []),
            "chained_from": [c for c in chained if c],
            "step_count": len(steps),
            "agents": sorted({str(s.get("agent")) for s, _ in steps if s.get("agent")}),
        }


def _agents_from_source(backend: Path, yaml_mod: Any, catalog: dict) -> None:
    used_in: dict[str, list[str]] = {}
    for wf_id, wf in catalog["workflows"].items():
        for agent in wf.get("agents", []):
            used_in.setdefault(agent, []).append(wf_id)

    specs: list[dict] = []
    try:
        from agents.loader import iter_agent_specs  # type: ignore

        for spec in iter_agent_specs():
            specs.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "role": spec.role,
                    "description": spec.description,
                    "pipeline_type": spec.pipeline_type,
                    "produces": list(spec.produces or []),
                    "consumes": list(spec.consumes or []),
                    "tools": list(spec.tools or []),
                    "model": spec.model,
                    "gate": spec.gate,
                    "injects": list(spec.injects or []),
                    "template": bool(getattr(spec, "template", False)),
                    "prompt_policy": getattr(spec, "prompt_policy", None),
                    "context_from": list(spec.context_from or []),
                }
            )
    except Exception as exc:  # noqa: BLE001 — fall back to parsing the files
        catalog["warnings"].append(f"agents.loader import failed ({exc}); parsed AGENT.md files directly")
        prompts = backend / "agents" / "prompts"
        for agent_md in sorted(prompts.glob("*/AGENT.md")):
            front, _body = _split_frontmatter(agent_md.read_text(encoding="utf-8"))
            meta = yaml_mod.safe_load(front) or {}
            specs.append(
                {
                    "id": str(meta.get("id") or agent_md.parent.name),
                    "name": meta.get("name") or "",
                    "role": meta.get("role") or "",
                    "description": meta.get("description") or meta.get("role") or "",
                    "pipeline_type": meta.get("pipeline_type"),
                    "produces": _as_list(meta.get("produces")),
                    "consumes": _as_list(meta.get("consumes")),
                    "tools": _as_list(meta.get("tools")),
                    "model": meta.get("model"),
                    "gate": meta.get("gate"),
                    "injects": _as_list(meta.get("injects")),
                    "template": bool(meta.get("template", False)),
                    "prompt_policy": meta.get("prompt_policy"),
                    "context_from": _as_list(meta.get("context_from")),
                }
            )
    for spec in sorted(specs, key=lambda s: s["id"]):
        spec["used_in"] = sorted(used_in.get(spec["id"], []))
        catalog["agents"][spec.pop("id")] = spec


def _skills_from_source(backend: Path, yaml_mod: Any, catalog: dict) -> None:
    try:
        from app.agents.skills_catalog import list_global_skills  # type: ignore

        for entry in list_global_skills():
            data = asdict(entry) if is_dataclass(entry) else dict(entry)
            skill_id = str(data.get("id"))
            catalog["skills"][skill_id] = {
                "name": data.get("name") or skill_id,
                "category": data.get("category") or "",
                "description": _short(data.get("description") or "", 220),
            }
        return
    except Exception as exc:  # noqa: BLE001 — fall back to a folder scan
        catalog["warnings"].append(f"skills catalog import failed ({exc}); scanned skills/global directly")
    for skill_md in sorted((backend / "skills" / "global").glob("*/SKILL.md")):
        front, _body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
        try:
            meta = yaml_mod.safe_load(front) or {}
        except Exception:  # noqa: BLE001
            meta = {}
        skill_id = skill_md.parent.name
        catalog["skills"][skill_id] = {
            "name": meta.get("name") or skill_id,
            "category": meta.get("category") or "",
            "description": _short(meta.get("description") or "", 220),
        }


def _scopes_from_source(catalog: dict) -> None:
    """Fill catalog['integration_scopes'] from the platform's provider table.

    Reads PROVIDERS / SCOPE_TO_SERVER (integration_providers/providers.py), the same table the
    engine uses to turn a granted scope into an MCP server, not the MCP servers' own `scope`
    field. A scope that does not match its server's scope is still listed, with a warning.
    Needs `catalog['mcp_servers']` and `catalog['capabilities']` to be filled first.
    """
    try:
        from agents.capabilities.integration_providers.providers import PROVIDERS, SCOPE_TO_SERVER  # type: ignore

        provider_caps = catalog["capabilities"].get("integration_provider", {})
        for scope, provider in sorted(PROVIDERS.items()):
            provider_name = getattr(provider, "name", "") or SCOPE_TO_SERVER.get(scope, "")
            server = SCOPE_TO_SERVER.get(scope) or provider_name
            entry = catalog["mcp_servers"].get(server)
            catalog["integration_scopes"][scope] = {
                "provider": provider_name,
                "server": server,
                "powerful": bool(entry and entry.get("powerful")),
                "user_allowed": bool(provider_caps.get(provider_name, {}).get("user_allowed", False)),
            }
            if entry is None:
                catalog["warnings"].append(
                    f"integration scope '{scope}' bridges MCP server '{server}', which is not in the MCP catalog"
                )
            elif entry.get("scope") and entry["scope"] != scope:
                catalog["warnings"].append(
                    f"integration scope '{scope}' bridges '{server}', whose own scope is '{entry['scope']}'"
                )
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"integration providers import failed ({exc}); inferred scopes from MCP servers")
        for name, entry in catalog["mcp_servers"].items():
            if entry.get("scope") and not entry.get("powerful"):
                catalog["integration_scopes"][entry["scope"]] = {
                    "provider": name, "server": name, "powerful": False, "user_allowed": bool(entry.get("user_allowed")),
                }


def from_source(backend: Path) -> dict:
    backend = backend.resolve()
    if not (backend / "agents").is_dir():
        raise SystemExit(f"error: {backend} is not a Velocity backend folder (no agents/ directory)")
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("error: --source needs PyYAML; run with the backend interpreter (uv run python ...)") from exc

    sys.path.insert(0, str(backend))
    os.chdir(backend)  # settings modules read .env from the working directory
    catalog = _empty_catalog()
    catalog["source"] = {
        "mode": "source",
        # folder name only: an absolute path would leak the local machine layout
        "path": backend.name,
        "branch": _git(backend, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(backend, "rev-parse", "--short", "HEAD"),
    }

    # ── capability registry ────────────────────────────────────────────────
    try:
        from agents.capabilities import registry as reg  # type: ignore

        reg.discover()
        registry = reg.CapabilityRegistry()
        for kind, name in sorted(reg._KNOWN):  # noqa: SLF001 — the registry's own membership set
            meta = registry.describe(kind, name)
            catalog["capabilities"].setdefault(kind, {})[name] = {
                "user_allowed": bool(registry.is_user_allowed(kind, name)),
                "saved_workflow_allowed": bool(registry.is_saved_workflow_allowed(kind, name)),
                "bound": (kind, name) in reg._IMPLS,  # noqa: SLF001
                "description": meta.get("description", "") or "",
                "process": meta.get("process", "") or "",
                "reads": list(meta.get("reads") or []),
                "writes": list(meta.get("writes") or []),
                "config_schema": meta.get("config_schema") or {},
            }
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"capability registry import failed: {exc}")

    # ── trust caps and budget ceilings ─────────────────────────────────────
    try:
        from agents.workflows import compiler as comp  # type: ignore
        from agents.workflows import permission_caps as pc  # type: ignore

        caps = {}
        for key, perms in pc.PERMISSION_CAP_INDEX.items():
            row = {field: bool(getattr(perms, field)) for field in pc.GRANT_BOOL_FIELDS}
            row["tool_sets"] = list(getattr(perms, "tool_sets", []) or [])
            caps[key] = row
        catalog["trust"] = {
            "trusted_levels": sorted(comp._TRUSTED_SOURCES),  # noqa: SLF001
            "levels": {
                "file": "trusted",
                "builtin": "trusted",
                "db": "trusted" if "db" in comp._TRUSTED_SOURCES else "saved",  # noqa: SLF001
                "user": "untrusted",
            },
            "caps": caps,
            "grant_bool_fields": list(pc.GRANT_BOOL_FIELDS),
            "grant_list_fields": list(pc.GRANT_LIST_FIELDS),
        }
        try:
            # The runtime security gate re-checks exec against its own trust set.
            from agents.capabilities.gates import security as security_gate  # type: ignore

            catalog["trust"]["exec_runtime_trust"] = sorted(security_gate._ENGINEER_TRUST)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            catalog["warnings"].append(f"security gate import failed: {exc}")
        catalog["limits"] = {
            "default_ceiling": dict(comp._LIMITS_DEFAULT_CEILING),  # noqa: SLF001
            "saved_ceiling": dict(comp._LIMITS_SAVED_CEILING),  # noqa: SLF001
            "max_subagents_nesting": int(comp._MAX_SUBAGENTS_DEPTH),  # noqa: SLF001
            "mechanical_kinds": sorted(comp._ALLOWED_MECHANICAL_KINDS),  # noqa: SLF001
            "on_conflict": sorted(comp._ALLOWED_ON_CONFLICT),  # noqa: SLF001
            "reserved_paths": sorted(p for p in comp._COMPILER_RESERVED_PATHS if not p.endswith("/")),  # noqa: SLF001
        }
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"compiler/permission_caps import failed: {exc}")
    try:
        from agents.execution_engine import budget  # type: ignore

        catalog["limits"]["runtime_defaults"] = {
            "max_subagents": budget.DEFAULT_MAX_SUBAGENTS,
            "max_concurrency": budget.DEFAULT_MAX_CONCURRENCY,
            "max_depth": budget.DEFAULT_MAX_DEPTH,
            "wall_clock_seconds": budget.DEFAULT_WALL_CLOCK_SECONDS,
        }
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"budget defaults import failed: {exc}")

    # ── models ─────────────────────────────────────────────────────────────
    try:
        from agents.capabilities.model_catalog import ModelCatalog  # type: ignore

        try:
            from agents.capabilities.model_catalog import REASONING_EFFORT_LEVELS  # type: ignore

            catalog["reasoning_effort_levels"] = list(REASONING_EFFORT_LEVELS)
        except ImportError:
            pass
        try:
            from agents.model_policy import selectable_models  # type: ignore

            selectable = {m.id for m in selectable_models()}
        except Exception:  # noqa: BLE001
            selectable = None
        for m in ModelCatalog().list():
            catalog["models"].append(
                {
                    "id": m.id,
                    "label": m.label,
                    "description": m.description,
                    "tier": m.tier,
                    "cost_class": m.cost_class,
                    "context_window": m.context_window,
                    "user_allowed": bool(m.user_allowed),
                    "vision": bool(m.vision),
                    "selectable": (m.id in selectable) if selectable is not None else True,
                    "reasoning": {
                        "mode": m.reasoning.mode,
                        "levels": list(m.reasoning.levels),
                        "default_effort": m.reasoning.default_effort,
                    },
                    "price_per_1m_usd": {
                        "input": round(m.pricing.input * 1_000_000, 4),
                        "output": round(m.pricing.output * 1_000_000, 4),
                    },
                }
            )
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"model catalog import failed: {exc}")

    # ── MCP servers / integration scopes ───────────────────────────────────
    try:
        from agents.capabilities.mcp_servers.catalog import CATALOG  # type: ignore

        for name, entry in sorted(CATALOG.items()):
            catalog["mcp_servers"][name] = {
                "tools": sorted(entry.exposed_tools),
                "powerful": bool(entry.powerful),
                "scope": entry.scope,
                "user_allowed": bool(
                    catalog["capabilities"].get("mcp_server", {}).get(name, {}).get("user_allowed", False)
                ),
            }
    except Exception as exc:  # noqa: BLE001
        catalog["warnings"].append(f"MCP catalog import failed: {exc}")

    _scopes_from_source(catalog)
    _workflows_from_source(backend, yaml, catalog)
    _agents_from_source(backend, yaml, catalog)
    _skills_from_source(backend, yaml, catalog)
    return catalog


# ------------------------------------------------------------------- api mode


def from_api(base_url: str, token: str, previous: dict) -> dict:
    def get(path: str) -> Any:
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 — operator-supplied URL
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"error: GET {path} returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"error: GET {path} failed: {exc.reason}") from exc

    catalog = _empty_catalog()
    # Data the API does not expose survives from the previous snapshot.
    for key in ("trust", "limits", "mcp_servers", "integration_scopes", "reasoning_effort_levels"):
        catalog[key] = previous.get(key) or type(catalog[key])()
    catalog["source"] = {"mode": "api", "url": base_url.rstrip("/")}

    palette = get("/api/capabilities")
    prev_caps = previous.get("capabilities") or {}
    for row in palette.get("capabilities", []):
        kind, name = row.get("kind"), row.get("name")
        if not kind or not name:
            continue
        old = prev_caps.get(kind, {}).get(name, {})
        catalog["capabilities"].setdefault(kind, {})[name] = {
            "user_allowed": bool(row.get("user_allowed")),
            "saved_workflow_allowed": bool(old.get("saved_workflow_allowed", row.get("user_allowed"))),
            "bound": True,
            "description": row.get("description") or "",
            "process": row.get("process") or "",
            "reads": list(row.get("reads") or []),
            "writes": list(row.get("writes") or []),
            "config_schema": row.get("config_schema") or {},
        }
    prev_models = {m["id"]: m for m in previous.get("models") or []}
    for row in palette.get("model_catalog", []):
        old = prev_models.get(row.get("id"), {})
        catalog["models"].append(
            {
                "id": row.get("id"),
                "label": row.get("label") or "",
                "description": row.get("description") or "",
                "tier": row.get("tier") or "",
                "cost_class": row.get("cost_class") or "",
                "context_window": row.get("context_window") or 0,
                "user_allowed": bool(row.get("user_allowed", True)),
                "vision": bool(old.get("vision", True)),
                "selectable": True,
                "reasoning": {
                    "mode": row.get("reasoning_mode") or "none",
                    "levels": list(row.get("reasoning_levels") or []),
                    "default_effort": (old.get("reasoning") or {}).get("default_effort"),
                },
                "price_per_1m_usd": {
                    "input": row.get("input_rate_per_1m", 0.0),
                    "output": row.get("output_rate_per_1m", 0.0),
                },
            }
        )

    prev_agents = previous.get("agents") or {}
    library = get("/api/agents/library")
    for row in library.get("agents", []):
        agent_id = str(row.get("id") or "")
        if not agent_id or row.get("is_user_agent") or agent_id.startswith("user-agent:"):
            continue  # saved library entries are templates, not runnable ids
        old = prev_agents.get(agent_id, {})
        catalog["agents"][agent_id] = {
            "name": row.get("name") or "",
            "role": row.get("role") or "",
            "description": row.get("description") or "",
            "pipeline_type": row.get("pipeline_type"),
            "produces": old.get("produces", []),
            "consumes": old.get("consumes", []),
            "tools": old.get("tools", []),
            "model": old.get("model"),
            "gate": row.get("gate"),
            "injects": old.get("injects", []),
            "template": bool(old.get("template", agent_id == "custom-agent")),
            "prompt_policy": old.get("prompt_policy"),
            "context_from": old.get("context_from", []),
            "used_in": old.get("used_in", []),
        }

    skills = get("/api/skills/library")
    for row in skills.get("skills", []):
        skill_id = str(row.get("id") or "")
        if skill_id:
            catalog["skills"][skill_id] = {
                "name": row.get("name") or skill_id,
                "category": row.get("category") or "",
                "description": _short(row.get("description") or "", 220),
            }

    prev_workflows = previous.get("workflows") or {}
    for row in get("/api/workflows") or []:
        wf_id = str(row.get("id") or "")
        if not wf_id:
            continue
        old = prev_workflows.get(wf_id, {})
        catalog["workflows"][wf_id] = {
            "name": row.get("name") or "",
            "display_name": row.get("display_name") or "",
            "description": row.get("description") or "",
            "user_launchable": bool(row.get("user_launchable", False)),
            "is_beta": bool(row.get("is_beta", False)),
            "planner": old.get("planner", ""),
            "clarify_mode": old.get("clarify_mode", ""),
            "deliverable": old.get("deliverable", {}),
            "context_providers": list(row.get("context_providers") or []),
            "chained_from": [c.get("id") for c in row.get("chained_from") or [] if c.get("id")],
            "step_count": int(row.get("step_count") or 0),
            "agents": sorted({s.get("agent_id") for s in row.get("steps") or [] if s.get("agent_id")}),
        }
    catalog["warnings"].append(
        "api mode: agent produces/consumes/tools, trust caps, budget ceilings and MCP tool lists come from the previous snapshot"
    )
    return catalog


# ------------------------------------------------------------------- markdown


def render_markdown(cat: dict) -> str:
    src = cat.get("source", {})
    where = (
        f"a Velocity `{src.get('path')}` checkout on `{src.get('branch') or '?'}` @ `{src.get('commit') or '?'}`"
        if src.get("mode") == "source"
        else f"server `{src.get('url')}`"
    )
    caps = cat.get("capabilities", {})
    n_caps = sum(len(v) for v in caps.values())
    out: list[str] = []
    w = out.append
    w("# Velocity catalog snapshot")
    w("")
    w(
        f"Generated {cat.get('generated_at')} from {where}. Regenerate with "
        "`scripts/refresh_catalog.py` whenever the target platform changes; "
        "`references/catalog.json` holds the same data for `validate_manifest.py`."
    )
    w("")
    w(
        f"Counts: {len(cat.get('agents', {}))} agents, {n_caps} capability coordinates, "
        f"{len(cat.get('models', []))} models, {len(cat.get('skills', {}))} step skills, "
        f"{len(cat.get('workflows', {}))} predefined workflows."
    )
    if cat.get("warnings"):
        w("")
        w("Snapshot warnings:")
        for warning in cat["warnings"]:
            w(f"- {warning}")

    # ── trust ──
    trust = cat.get("trust") or {}
    if trust:
        w("")
        w("## Trust caps (what a step's `tools` grant can resolve to)")
        w("")
        w("| Cap | read | write | exec | git | network | spawn_subagents | tool_sets kept |")
        w("|---|---|---|---|---|---|---|---|")
        for key, row in (trust.get("caps") or {}).items():
            w(
                f"| {key} | {row.get('read_files')} | {row.get('write_files')} | {row.get('exec')} | "
                f"{row.get('git')} | {row.get('network')} | {row.get('spawn_subagents')} | "
                f"{_md_cell(row.get('tool_sets'))} |"
            )
        w("")
        levels = trust.get("levels") or {}
        w("Trust level to cap: " + ", ".join(f"`{k}` -> {v}" for k, v in levels.items()) + ".")
        if trust.get("exec_runtime_trust"):
            w("")
            w(
                "Runtime security gate: `exec` passes only at "
                + ", ".join(f"`{t}`" for t in trust["exec_runtime_trust"])
                + " trust (with the `approval` gate); `network` and `secrets` are blocked on any step "
                "that declares the `security` gate."
            )
    limits = cat.get("limits") or {}
    if limits:
        w("")
        w("## Budget limits")
        w("")
        w(f"- Runtime defaults: {_kv(limits.get('runtime_defaults'))}")
        w(f"- `user` trust may only lower: {_kv(limits.get('default_ceiling'))}")
        w(f"- Largest values any built-in uses: {_kv(limits.get('saved_ceiling'))}")
        w(f"- Subagent nesting blocks allowed: {limits.get('max_subagents_nesting')}")

    # ── capabilities ──
    # Tool sets are bound by the trust cap's tool_sets list, not by the registry's user_allowed
    # flag (permission_caps.py), so the `user` column for them comes from the untrusted cap.
    user_cap = ((trust.get("caps") or {}).get((trust.get("levels") or {}).get("user", "untrusted")) or {})
    user_tool_sets = set(user_cap.get("tool_sets") or [])

    def capability_table(kind: str, rows: dict) -> None:
        w("")
        w(f"### `{kind}` ({len(rows)})")
        w("")
        w("| Name | user | What it does | Reads | Writes |")
        w("|---|---|---|---|---|")
        for name, row in sorted(rows.items()):
            text = row.get("description") or ""
            if row.get("process"):
                text = f"{text} {row['process']}".strip()
            allowed = name in user_tool_sets if kind == "tool" and user_cap else row.get("user_allowed")
            w(
                f"| `{name}` | {'yes' if allowed else 'no'} | {_md_cell(_short(text, 260))} | "
                f"{_md_cell(row.get('reads'))} | {_md_cell(row.get('writes'))} |"
            )
        if kind == "tool" and user_cap:
            w("")
            w(
                "For tool sets the `user` column follows the `user` trust cap in the Trust caps table at the top, not "
                "the registry flag: a set that cap does not keep is silently dropped from the step."
            )

    w("")
    w("## Capabilities a manifest can name")
    w("")
    w("`user` = allowed in a `user`-trust manifest (inline Run once, override rows).")
    w("Everything listed is allowed for `file`, `builtin` and `db` trust.")
    for kind in MANIFEST_KINDS:
        if caps.get(kind):
            capability_table(kind, caps[kind])
    others = sorted(k for k in caps if k not in MANIFEST_KINDS and caps.get(k))
    if others:
        w("")
        w("## Registry kinds a manifest cannot name")
        w("")
        w(
            "The engine picks these itself (merge strategy, prompt policy, runtime, repo index and so on). They are "
            "listed for reference only: no manifest field accepts them. The `skill` kind below lists skill sources, "
            "not step skills; step skills are in the Step skills section."
        )
        for kind in others:
            capability_table(kind, caps[kind])

    # ── icons ──
    w("")
    w("## Icons (`icon`)")
    w("")
    w(
        "The catalog card renders these Lucide names (frontend/src/lib/workflowIcons.ts); any other name shows the "
        "default icon: " + ", ".join(f"`{name}`" for name in CATALOG_ICONS) + "."
    )

    # ── models ──
    w("")
    w("## Models")
    w("")
    w("| Model id | Label | Cost class | Tier | Context | Reasoning | Effort levels | Default effort | Vision | Picker |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for m in cat.get("models", []):
        r = m.get("reasoning") or {}
        w(
            f"| `{m.get('id')}` | {_md_cell(m.get('label'))} | {m.get('cost_class')} | {m.get('tier')} | "
            f"{m.get('context_window')} | {r.get('mode')} | {_md_cell(r.get('levels'))} | "
            f"{_md_cell(r.get('default_effort'))} | {'yes' if m.get('vision') else 'no'} | "
            f"{'yes' if m.get('selectable') else 'no (raw id only)'} |"
        )

    # ── MCP ──
    mcp = cat.get("mcp_servers") or {}
    if mcp:
        w("")
        w("## MCP servers (`tools.mcp: [\"server.tool\"]`)")
        w("")
        w("| Server | user | Powerful | Exposed tools | Own scope |")
        w("|---|---|---|---|---|")
        for name, row in sorted(mcp.items()):
            w(
                f"| `{name}` | {'yes' if row.get('user_allowed') else 'no'} | {'yes' if row.get('powerful') else 'no'} | "
                f"{_md_cell(row.get('tools'))} | {_md_cell(row.get('scope'))} |"
            )
    scopes = cat.get("integration_scopes") or {}
    if scopes:
        w("")
        w("## Integration scopes (`tools.integrations: [\"scope\"]`)")
        w("")
        w("Each scope turns on the tools of one MCP server for the run. List the matching `server.tool` names in `tools.mcp`.")
        w("")
        w("| Scope | Provider | MCP server | user |")
        w("|---|---|---|---|")
        for scope, row in sorted(scopes.items()):
            row = row if isinstance(row, dict) else {"server": row, "provider": row}
            w(
                f"| `{scope}` | `{_md_cell(row.get('provider'))}` | `{_md_cell(row.get('server'))}` | "
                f"{'yes' if row.get('user_allowed', True) else 'no'} |"
            )

    # ── agents ──
    agents = cat.get("agents") or {}
    w("")
    w("## Agents (`step.agent`)")
    w("")
    w(
        "`custom-agent` is the blank template: give each use an `instance_id` and a `prompt`. "
        "Every other id is an AGENT.md agent with a fixed prompt and contract; `used in` lists the "
        "predefined workflows that already run it."
    )
    by_pipeline: dict[str, list[str]] = {}
    for agent_id, row in agents.items():
        pt = row.get("pipeline_type")
        key = ", ".join(pt) if isinstance(pt, list) else str(pt or "?")
        by_pipeline.setdefault(key, []).append(agent_id)
    for pipeline in sorted(by_pipeline, key=lambda k: (k != "custom", k)):
        w("")
        w(f"### pipeline_type `{pipeline}`")
        w("")
        w("| Agent | Role / description | Produces | Consumes | Tools | Model | Used in |")
        w("|---|---|---|---|---|---|---|")
        for agent_id in sorted(by_pipeline[pipeline]):
            row = agents[agent_id]
            label = row.get("description") or row.get("role") or ""
            if row.get("template"):
                label = f"TEMPLATE. {label}"
            w(
                f"| `{agent_id}` | {_md_cell(_short(label, 200))} | {_md_cell(row.get('produces'))} | "
                f"{_md_cell(row.get('consumes'))} | {_md_cell(row.get('tools'))} | {_md_cell(row.get('model'))} | "
                f"{_md_cell(row.get('used_in'))} |"
            )

    # ── skills ──
    skills = cat.get("skills") or {}
    w("")
    w(f"## Step skills (`step.skills`, {len(skills)})")
    w("")
    w("A skill is staged at `/skills/<id>/SKILL.md`; the step needs `read_files: true` to open it.")
    w("")
    w("| Skill id | Category | Description |")
    w("|---|---|---|")
    for skill_id, row in sorted(skills.items()):
        w(f"| `{skill_id}` | {_md_cell(row.get('category'))} | {_md_cell(_short(row.get('description') or '', 180))} |")

    # ── workflows ──
    workflows = cat.get("workflows") or {}
    w("")
    w("## Predefined workflows (valid `trigger: workflow` targets and `chained_from` ids)")
    w("")
    w("| Id | Launchable | Beta | Steps | Planner | Deliverable | Chained from |")
    w("|---|---|---|---|---|---|---|")
    for wf_id, row in sorted(workflows.items()):
        d = row.get("deliverable") or {}
        w(
            f"| `{wf_id}` | {'yes' if row.get('user_launchable') else 'no'} | {'yes' if row.get('is_beta') else 'no'} | "
            f"{row.get('step_count')} | {_md_cell(row.get('planner'))} | {_md_cell(d.get('strategy'))} "
            f"{_md_cell(d.get('name')) if d.get('name') else ''} | {_md_cell(row.get('chained_from'))} |"
        )
    w("")
    return "\n".join(out)


# ----------------------------------------------------------------------- main


def _write(path: Path, text: str) -> None:
    """Write text with LF endings on every platform so output is byte-stable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def validate_catalog(cat: Any) -> tuple[list[str], list[str]]:
    """Check a catalog (for example one edited by hand). Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(cat, dict):
        return ["catalog.json must be a JSON object"], warnings
    shape = {"capabilities": dict, "models": list, "agents": dict, "skills": dict, "workflows": dict,
             "mcp_servers": dict, "integration_scopes": dict, "trust": dict, "limits": dict}
    for key, kind in shape.items():
        if key not in cat:
            errors.append(f"missing key '{key}'")
        elif not isinstance(cat[key], kind):
            errors.append(f"'{key}' must be a {kind.__name__}")
    if errors:
        return errors, warnings
    caps = cat["capabilities"]
    for kind, rows in caps.items():
        if not isinstance(rows, dict):
            errors.append(f"capabilities.{kind} must be an object of name -> row")
            continue
        for name, row in rows.items():
            if not isinstance(row, dict):
                errors.append(f"capabilities.{kind}.{name} must be an object")
                continue
            for flag in ("user_allowed", "saved_workflow_allowed"):
                if flag not in row:
                    warnings.append(f"capabilities.{kind}.{name} has no '{flag}' (treated as false)")
            if not row.get("description") and kind not in ("model_catalog",):
                warnings.append(f"capabilities.{kind}.{name} has no description (the agent reads it in catalog.md)")
    for i, model in enumerate(cat["models"]):
        if not isinstance(model, dict) or not model.get("id"):
            errors.append(f"models[{i}] needs an 'id'")
    tool_names = set(caps.get("tool") or {})
    for cap_name, row in ((cat["trust"].get("caps")) or {}).items():
        for tool in row.get("tool_sets") or []:
            if tool_names and tool not in tool_names:
                warnings.append(f"trust.caps.{cap_name}.tool_sets lists '{tool}', which is not a registered tool")
    for tool in sorted(tool_names):
        if (cat["trust"].get("caps")) and not any(tool in (r.get("tool_sets") or []) for r in cat["trust"]["caps"].values()):
            warnings.append(f"tool set '{tool}' is in no trust cap's tool_sets, so every trust level drops it")
    server_caps = set(caps.get("mcp_server") or {})
    for server in cat["mcp_servers"]:
        if server_caps and server not in server_caps:
            warnings.append(f"mcp_servers.{server} has no capabilities.mcp_server.{server} entry")
        if not cat["mcp_servers"][server].get("tools"):
            warnings.append(f"mcp_servers.{server} exposes no tools")
    for scope, row in cat["integration_scopes"].items():
        server = row.get("server") if isinstance(row, dict) else row
        if server not in cat["mcp_servers"]:
            warnings.append(f"integration scope '{scope}' bridges '{server}', which is not in mcp_servers")
    for agent_id, row in cat["agents"].items():
        pipeline = row.get("pipeline_type") if isinstance(row, dict) else None
        if not pipeline:
            warnings.append(f"agents.{agent_id} has no pipeline_type")
    return errors, warnings


def diff_catalogs(old: dict, new: dict) -> list[str]:
    """Human-readable list of names added or removed between two snapshots."""
    lines: list[str] = []

    def compare(label: str, before: set, after: set) -> None:
        added, removed = sorted(after - before), sorted(before - after)
        if added:
            lines.append(f"+ {label}: {', '.join(map(str, added))}")
        if removed:
            lines.append(f"- {label}: {', '.join(map(str, removed))}")

    old_caps, new_caps = old.get("capabilities") or {}, new.get("capabilities") or {}
    for kind in sorted(set(old_caps) | set(new_caps)):
        compare(f"{kind}", set(old_caps.get(kind) or {}), set(new_caps.get(kind) or {}))
    for kind in sorted(set(old_caps) | set(new_caps)):
        for name in sorted(set(old_caps.get(kind) or {}) & set(new_caps.get(kind) or {})):
            before, after = old_caps[kind][name], new_caps[kind][name]
            for flag in ("user_allowed", "saved_workflow_allowed"):
                if before.get(flag) != after.get(flag):
                    lines.append(f"~ {kind}.{name}: {flag} {before.get(flag)} -> {after.get(flag)}")
    old_caps_t = (old.get("trust") or {}).get("caps") or {}
    new_caps_t = (new.get("trust") or {}).get("caps") or {}
    for cap_name in sorted(set(old_caps_t) | set(new_caps_t)):
        compare(f"trust cap '{cap_name}' tool_sets", set((old_caps_t.get(cap_name) or {}).get("tool_sets") or []),
                set((new_caps_t.get(cap_name) or {}).get("tool_sets") or []))
    compare("models", {m.get("id") for m in old.get("models") or []}, {m.get("id") for m in new.get("models") or []})
    old_mcp, new_mcp = old.get("mcp_servers") or {}, new.get("mcp_servers") or {}
    compare("mcp servers", set(old_mcp), set(new_mcp))
    compare("mcp tools", {f"{s}.{t}" for s, e in old_mcp.items() for t in e.get("tools") or []},
            {f"{s}.{t}" for s, e in new_mcp.items() for t in e.get("tools") or []})
    compare("integration scopes", set(old.get("integration_scopes") or {}), set(new.get("integration_scopes") or {}))
    compare("agents", set(old.get("agents") or {}), set(new.get("agents") or {}))
    compare("skills", set(old.get("skills") or {}), set(new.get("skills") or {}))
    compare("workflows", set(old.get("workflows") or {}), set(new.get("workflows") or {}))
    return lines


def run_schema_sync(catalog: dict, schema_path: Path, write: bool) -> tuple[list[str], list[str], bool]:
    if not schema_path.is_file():
        return [], [f"schema not found at {schema_path}; skipped"], False
    return schema_sync.sync_file(schema_path, catalog, write=write)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", type=Path, help="Velocity backend folder (contains agents/)")
    group.add_argument("--api", help="Velocity server base URL, e.g. https://velocity.example.com")
    group.add_argument("--render", action="store_true", help="re-render catalog.md and re-sync the schema from catalog.json")
    group.add_argument("--check", action="store_true", help="report drift between catalog.json, catalog.md and the schema")
    parser.add_argument("--token", default=os.environ.get("VELOCITY_API_TOKEN", ""), help="bearer token for --api")
    parser.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_MD)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="schema file to keep in sync")
    parser.add_argument("--no-schema", action="store_true", help="do not touch the schema")
    args = parser.parse_args(argv)

    out_json = args.out_json.resolve()
    out_md = args.out_md.resolve()
    schema_path = args.schema.resolve()
    previous: dict = {}
    if out_json.is_file():
        try:
            previous = json.loads(out_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}

    # ── modes that start from the existing catalog.json ──────────────────────
    if args.render or args.check:
        if not out_json.is_file():
            print(f"error: {out_json} not found; run --source or --api first", file=sys.stderr)
            return 1
        try:
            catalog = json.loads(out_json.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"error: {out_json} is not valid JSON: {exc}", file=sys.stderr)
            return 1
        errors, warnings = validate_catalog(catalog)
        for error in errors:
            print(f"error: catalog.json: {error}", file=sys.stderr)
        if errors:
            return 1
        for warning in warnings:
            print(f"warning: {warning}")
        rendered = render_markdown(catalog)
        if args.check:
            drift = []
            if not out_md.is_file() or _read_norm(out_md) != rendered:
                drift.append(f"{out_md.name} does not match catalog.json: run --render")
            if not args.no_schema:
                changes, schema_warnings, schema_drift = run_schema_sync(catalog, schema_path, write=False)
                if schema_drift:
                    drift.append(f"{schema_path.name} is out of date ({'; '.join(changes) or 'formatting'}): run --render")
                for warning in schema_warnings:
                    print(f"warning: {warning}")
            for line in drift:
                print(f"drift: {line}")
            print("catalog, catalog.md and schema are in sync" if not drift else f"{len(drift)} file(s) out of date")
            return 1 if drift else 0
        _write(out_md, rendered)
        print(f"re-rendered {out_md} from {out_json}")
        if not args.no_schema:
            changes, schema_warnings, drifted = run_schema_sync(catalog, schema_path, write=True)
            for change in changes:
                print(f"  schema: {change}")
            for warning in schema_warnings:
                print(f"warning: {warning}")
            print(f"schema {'updated' if drifted else 'already in sync'}: {schema_path}")
        return 0

    # ── modes that collect a fresh catalog ───────────────────────────────────
    if args.source:
        catalog = from_source(args.source)
    else:
        if not args.token:
            print("error: --api needs --token or VELOCITY_API_TOKEN", file=sys.stderr)
            return 1
        catalog = from_api(args.api, args.token, previous)

    catalog["generated_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not catalog["capabilities"] or not catalog["agents"]:
        print("error: refusing to write an empty catalog (no capabilities or agents found)", file=sys.stderr)
        for warning in catalog["warnings"]:
            print(f"  warning: {warning}", file=sys.stderr)
        return 1
    errors, warnings = validate_catalog(catalog)
    catalog["warnings"].extend(w for w in warnings if w not in catalog["warnings"])
    if errors:
        for error in errors:
            print(f"error: collected catalog is invalid: {error}", file=sys.stderr)
        return 1

    _write(out_json, json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    _write(out_md, render_markdown(catalog))
    n_caps = sum(len(v) for v in catalog["capabilities"].values())
    print(
        f"wrote {out_json} and {out_md}: {len(catalog['agents'])} agents, {n_caps} capabilities, "
        f"{len(catalog['models'])} models, {len(catalog['skills'])} skills, {len(catalog['workflows'])} workflows"
    )
    if not args.no_schema:
        changes, schema_warnings, drifted = run_schema_sync(catalog, schema_path, write=True)
        for change in changes:
            print(f"  schema: {change}")
        for warning in schema_warnings:
            catalog["warnings"].append(warning)
        print(f"schema {'updated' if drifted else 'already in sync'}: {schema_path}")
    if previous:
        changes = diff_catalogs(previous, catalog)
        if changes:
            print("\nChanges since the previous snapshot:")
            for line in changes:
                print(f"  {line}")
            print("  -> describe new names in docs/field-guide.md and docs/requirements-analysis.md (docs/extending.md)")
        else:
            print("No name changes since the previous snapshot.")
    for warning in catalog["warnings"]:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
