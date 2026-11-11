#!/usr/bin/env python3
"""Validate a Velocity workflow manifest before it is saved or run.

Three layers run on every call:

  1. JSON Schema  - schema/workflow-manifest.schema.json (needs the optional
                    `jsonschema` package; skipped with a notice when missing).
  2. Compiler     - the same rules the platform's WorkflowCompiler enforces:
                    strict keys, instance_id shape and uniqueness, subagent
                    nesting, registered capability names, trust caps, tool
                    grants, MCP gating, routes, deliverable, limits, cycles,
                    fan-out sources and route decision sources.
  3. Design lint  - things that compile but misbehave at run time: unreachable
                    steps, steps the resolver may reorder, unknown agents,
                    models or skills, decision prompts that cannot route,
                    validators that never run, budget overruns and more.

Optionally `--compiler BACKEND_DIR` also runs the platform's real compiler on
the manifest (run this script with the backend's interpreter for that, e.g.
`uv run python .../validate_manifest.py wf.json --compiler .` from backend/).

Usage:
  python validate_manifest.py FILE [--trust user|db|file|builtin] [--summary]
                              [--json] [--strict] [--catalog PATH] [--schema PATH]

Exit codes: 0 = valid (warnings allowed unless --strict), 1 = errors, 2 = usage/IO.
Stdlib only; `jsonschema` and `PyYAML` are optional.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = SKILL_DIR / "schema" / "workflow-manifest.schema.json"
DEFAULT_CATALOG = SKILL_DIR / "references" / "catalog.json"

# ── platform constants (mirrors the compiler; the catalog overrides when present) ──
TOP_KEYS = {
    "id", "version", "name", "display_name", "short_name", "description", "icon",
    "user_launchable", "is_beta", "launch_surface", "design_mode", "chained_from",
    "planner", "clarify", "deliverable", "context_providers", "input_providers",
    "seed_files", "allowed_workers", "limits", "capabilities", "model", "chat", "steps",
}
REQUIRED_TOP = ("id", "steps", "deliverable", "planner", "clarify")
STEP_KEYS = {
    "agent", "strategy", "mechanical", "gates", "hooks", "validators", "compaction",
    "task_source", "post_step", "require_render", "tools", "model", "fix", "fanout",
    "route", "produces", "consumes", "on_conflict", "retry", "injects", "depends_on",
    "instance_id", "name", "prompt", "skills", "subagents", "produces_solution_plan",
    "redoable", "reply", "condition", "outputs", "replaces",
}
SUBAGENT_KEYS = {"mode", "max_parallel", "task_source", "steps"}
SUBAGENT_MODES = ("parallel", "sequential", "fanout")
TASK_SOURCE_KEYS = {"kind", "parser", "target", "source_step", "spec_step", "path"}
TASK_SOURCE_KINDS = ("none", "inline", "parsed", "file", "custom_path")
FANOUT_KEYS = {"mode", "max_parallel", "agent", "count", "workers", "merge_agent"}
ROUTE_KEYS = {"condition_agent", "outcomes", "default_next", "loop_max_iterations",
              "trigger_max_depth", "on_loop_exhausted"}
OUTCOME_KEYS = {"trigger", "target", "feedback"}
MODEL_KEYS = {"model", "max_tokens", "cost_class", "fallback", "effort"}
RETRY_KEYS = {"max_attempts", "backoff_seconds", "on"}
FIX_KEYS = {"mode", "max_attempts"}
LIMIT_KEYS = {"max_tokens", "max_subagents", "max_depth", "wall_clock_seconds"}
INJECTS = ("design_system", "template", "template_example", "craft")
TOOL_BOOL_DEFAULT = ("read_files", "write_files", "exec", "git", "network", "spawn_subagents")
TOOL_LIST_DEFAULT = ("secrets", "mcp", "integrations", "tool_sets")
MECHANICAL_DEFAULT = ("assemble_backlog", "assemble_prototype", "extract_prototype_ui", "publish")
ON_CONFLICT_DEFAULT = ("abort", "human_gate", "merge_agent", "partial")
HITL_GATES = ("human", "before-human", "approval")
ENGINEER_TRUST = ("file", "builtin")  # the only trust the runtime security gate lets exec through
DEFAULT_HOOKS = ("audit_logger", "secret_scan")
INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
CUSTOM = "custom-agent"
RESERVED_PATHS_DEFAULT = (".uploads", ".logs", ".verify", ".browser", ".agents", ".chain",
                          ".context", "skills", "conversation_history", ".chain-legacy", ".extract")
EFFORT_DEFAULT = ("none", "low", "medium", "high", "xhigh", "max")
MODEL_PREFIXES = ("eu.", "us.", "apac.", "global.", "anthropic.")
MODEL_SUFFIX_RE = re.compile(r"(-\d{8})?(-v\d+(?::\d+)?)?$")
EXEMPT_CONSUMES = ("planning_context", "constitution")
PASTE_REFERENCE_RE = re.compile(r"(?i)\b(?:shown|pasted) above\b")
# The prompt standard (docs/quick-reference.md section 8). The shortest custom-agent prompt in the
# shipped examples is 3,031 characters; decision steps and placeholders are exempt.
MIN_PROMPT_CHARS = 2000
PROMPT_PARTS = (
    ("a role line ('You are the ...')", ("you are the",)),
    ("an input section (WHAT YOU RECEIVE)", ("what you receive", "input")),
    ("numbered steps", ("\n1.",)),
    ("an output section (OUTPUT or HOW TO DELIVER)", ("output", "how to deliver")),
    ("rules (RULES or NEVER)", ("rules", "never")),
    ("a missing-input rule (IF INPUT IS MISSING)", ("missing", "needs_input", "not provided")),
)
# Only the first step receives the brief in its message (engine _compose_context_message).
BRIEF_REFERENCE_RE = re.compile(
    r"(?i)\b(?:(?:brief|request|ticket|topic) in your message|original (?:brief|request)|in the (?:brief|request))\b")
CATALOG_ICONS = ("FileText", "Presentation", "Layout", "Rocket", "Puzzle", "GitBranch", "MessageSquare",
                 "Search", "GitPullRequest", "Network", "Waves")
COMPOSER_MAX_ROOTS = 16
COMPOSER_MAX_CHILDREN = 8
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}"),
)

LEVEL_ORDER = {"error": 0, "warning": 1, "info": 2}
NEGATION_RE = re.compile(r"(?i)\b(?:not|cannot|can't|never|without)\b")


def expects_brief(prompt: str) -> bool:
    """True when a prompt says the brief is in the step's own message (negated clauses do not count)."""
    for match in BRIEF_REFERENCE_RE.finditer(prompt):
        # The whole clause counts: "the original request is not in your message" negates after the match.
        clause = re.split(r"[.\n;:]", prompt[:match.start()])[-1] + re.split(r"[.\n;:]", prompt[match.start():])[0]
        if not NEGATION_RE.search(clause):
            return True
    return False


@dataclass
class Finding:
    level: str
    code: str
    where: str
    message: str
    hint: str = ""


@dataclass
class CStep:
    """One compiled step, as the engine will see it (flattened, children first)."""

    agent_id: str
    agent: str
    instance_id: str
    name: str
    raw: dict
    where: str
    path: str
    depth: int
    strategy: str
    gates: list
    depends_on: list
    route: dict | None
    produces: list
    consumes: list
    tools_requested: dict
    tools: dict
    task_source: dict | None
    fanout: dict | None
    mechanical: str | None
    hooks: list
    validators: list
    skills: list
    reply: str
    parent: str = ""
    dispatched_by: str = ""
    group_mode: str = ""
    is_leaf: bool = False
    children: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────── catalog


class Catalog:
    def __init__(self, data: dict | None):
        self.data = data or {}
        self.present = bool(data)
        self.exec_trust = tuple((self.data.get("trust") or {}).get("exec_runtime_trust") or ENGINEER_TRUST)
        self.caps: dict = self.data.get("capabilities") or {}
        self.models: list = self.data.get("models") or []
        self.agents: dict = self.data.get("agents") or {}
        self.skills: dict = self.data.get("skills") or {}
        self.workflows: dict = self.data.get("workflows") or {}
        self.mcp: dict = self.data.get("mcp_servers") or {}
        self.trust: dict = self.data.get("trust") or {}
        self.limits: dict = self.data.get("limits") or {}
        self.effort_levels = tuple(self.data.get("reasoning_effort_levels") or EFFORT_DEFAULT)
        self.mechanical = tuple(self.limits.get("mechanical_kinds") or MECHANICAL_DEFAULT)
        self.on_conflict = tuple(self.limits.get("on_conflict") or ON_CONFLICT_DEFAULT)
        self.reserved = tuple(self.limits.get("reserved_paths") or RESERVED_PATHS_DEFAULT)
        self.bool_fields = tuple(self.trust.get("grant_bool_fields") or TOOL_BOOL_DEFAULT)
        self.list_fields = tuple(self.trust.get("grant_list_fields") or TOOL_LIST_DEFAULT)

    # capabilities
    def registered(self, kind: str, name: str) -> bool:
        if not self.caps:
            return True  # no catalog: cannot judge
        return name in (self.caps.get(kind) or {})

    def flag(self, kind: str, name: str, key: str) -> bool:
        return bool(((self.caps.get(kind) or {}).get(name) or {}).get(key, False))

    def names(self, kind: str) -> list:
        return sorted((self.caps.get(kind) or {}).keys())

    # trust
    def profile(self, trust: str) -> str:
        levels = self.trust.get("levels") or {}
        if trust in levels:
            return levels[trust]
        return "trusted" if trust in ("file", "builtin", "db") else "untrusted"

    def cap(self, profile: str) -> dict:
        caps = self.trust.get("caps") or {}
        if profile in caps:
            return caps[profile]
        defaults = {
            "trusted": {"read_files": True, "write_files": True, "exec": True, "git": True, "network": False,
                        "spawn_subagents": True,
                        "tool_sets": ["workspace", "prototype", "prototype_emit_only", "planning", "internet",
                                      "pptx", "playwright", "file_extract", "spawn_subagents", "ask_user"]},
            "saved": {"read_files": True, "write_files": True, "exec": False, "git": False, "network": False,
                      "spawn_subagents": True,
                      "tool_sets": ["file_extract", "playwright", "prototype_emit_only", "ask_user"]},
            "untrusted": {"read_files": True, "write_files": True, "exec": False, "git": False, "network": False,
                          "spawn_subagents": False, "tool_sets": ["file_extract", "playwright"]},
        }
        return defaults.get(profile, defaults["untrusted"])

    def ceiling(self, profile: str) -> dict:
        if profile == "untrusted":
            return self.limits.get("default_ceiling") or {"max_subagents": 8, "max_depth": 2, "wall_clock_seconds": 900}
        if profile == "saved":
            return self.limits.get("saved_ceiling") or {"max_subagents": 200, "max_depth": 2, "wall_clock_seconds": 10800}
        return {}

    def runtime_default(self, key: str, fallback: int) -> int:
        return int((self.limits.get("runtime_defaults") or {}).get(key, fallback))

    # models
    def model(self, model_id: str) -> dict | None:
        for m in self.models:
            if m.get("id") == model_id:
                return m
        key = normalize_model_id(model_id)
        for m in self.models:
            if normalize_model_id(str(m.get("id"))) == key:
                return m
        return None

    def model_exact(self, model_id: str) -> dict | None:
        return next((m for m in self.models if m.get("id") == model_id), None)


def normalize_model_id(model_id: str) -> str:
    key = model_id or ""
    changed = True
    while changed:
        changed = False
        for prefix in MODEL_PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix):]
                changed = True
    return MODEL_SUFFIX_RE.sub("", key)


# ─────────────────────────────────────────────────────────────── checker


class Checker:
    def __init__(self, manifest: Any, catalog: Catalog, trust: str):
        self.m = manifest
        self.cat = catalog
        self.trust = trust
        self.profile = catalog.profile(trust)
        self.trusted = self.profile == "trusted"
        self.findings: list[Finding] = []
        self.steps: list[CStep] = []
        self.by_name: dict[str, CStep] = {}

    # ── reporting ──
    def add(self, level: str, code: str, where: str, message: str, hint: str = "") -> None:
        self.findings.append(Finding(level, code, where, message, hint))

    def err(self, code, where, message, hint=""):
        self.add("error", code, where, message, hint)

    def warn(self, code, where, message, hint=""):
        self.add("warning", code, where, message, hint)

    def info(self, code, where, message, hint=""):
        self.add("info", code, where, message, hint)

    # ── trust ──
    def allowed(self, kind: str, name: str) -> bool:
        if self.trusted:
            return True
        if self.cat.flag(kind, name, "user_allowed"):
            return True
        if self.profile == "saved" and self.cat.flag(kind, name, "saved_workflow_allowed"):
            return True
        return not self.cat.caps  # no catalog: cannot judge

    def check_cap(self, kind: str, name: Any, where: str) -> bool:
        if not isinstance(name, str) or not name:
            self.err("capability", where, f"{kind} reference must be a non-empty string, got {name!r}")
            return False
        if not self.cat.registered(kind, name):
            self.err("capability", where, f"unknown {kind} '{name}'",
                     f"registered {kind} names: {', '.join(self.cat.names(kind)) or '(none in catalog)'}")
            return False
        if not self.allowed(kind, name):
            self.err("trust", where, f"{kind} '{name}' is not allowed for '{self.trust}' trust",
                     "remove it, or target a trusted source (a saved Composer workflow runs at 'db' trust for "
                     "callers entitled to the custom pipeline)")
            return False
        return True

    # ── entry ──
    def run(self) -> None:
        m = self.m
        if not isinstance(m, dict):
            self.err("structure", "$", "the manifest must be a JSON object")
            return
        self.check_top()
        steps = m.get("steps")
        if not isinstance(steps, list):
            return
        if not steps:
            self.warn("steps", "steps", "the workflow has no steps; a saved or inline Composer manifest needs at least one")
        seen: set[str] = set()
        self.identity_tree(steps, 0, seen, "steps")
        for i, raw in enumerate(steps):
            if isinstance(raw, dict):
                self.expand(raw, f"steps[{i}]", 0, "")
        for s in self.steps:
            self.by_name.setdefault(s.agent_id, s)
            if s.instance_id:
                self.by_name.setdefault(s.instance_id, s)
        self.check_dag()
        self.check_fanout_sources()
        self.check_routes()
        self.compute_leaves()
        self.lint()

    # ─────────────────────────────────────────── top level

    def check_top(self) -> None:
        m = self.m
        extra = sorted(set(m) - TOP_KEYS)
        if extra:
            self.err("unknown-key", "$", f"unknown top-level key(s) {extra}",
                     "the parser rejects unknown keys; repo binding, comments and notes are not authorable")
        for key in REQUIRED_TOP:
            if key not in m:
                self.err("required", "$", f"missing required top-level key '{key}'")
        wf_id = m.get("id")
        if "id" in m and (not isinstance(wf_id, str) or not wf_id.strip()):
            self.err("id", "id", "id must be a non-empty string")
        elif isinstance(wf_id, str) and not re.match(r"^[a-z0-9][a-z0-9_-]*$", wf_id):
            self.info("id", "id", f"id '{wf_id}' is not lower-case snake/kebab case",
                      "lower-case letters, digits, '_' or '-' keep it safe as a folder name and route target")
        if "version" in m and (not isinstance(m["version"], int) or isinstance(m["version"], bool)):
            self.err("type", "version", "version must be an integer")
        for key in ("user_launchable", "is_beta"):
            if key in m and not isinstance(m[key], bool):
                self.err("type", key, f"{key} must be a real boolean (true/false), not {m[key]!r}")
        for key in ("name", "display_name", "short_name", "description", "icon", "launch_surface"):
            if key in m and not isinstance(m[key], str):
                self.err("type", key, f"{key} must be a string")
        if isinstance(m.get("icon"), str) and m["icon"] not in CATALOG_ICONS:
            self.info("icon", "icon", f"icon '{m['icon']}' renders as the default icon",
                      f"the catalog card renders: {', '.join(CATALOG_ICONS)}")
        for key in ("name", "display_name", "description"):
            if m.get("user_launchable") and not m.get(key):
                self.info("presentation", key, f"a launchable workflow should set '{key}'")
        if "design_mode" in m and m["design_mode"] not in ("web", "deck"):
            self.err("enum", "design_mode", "design_mode must be 'web' or 'deck'")
        planner = m.get("planner")
        if "planner" in m and planner not in ("run", "skip"):
            self.err("enum", "planner", f"planner must be 'run' or 'skip', got {planner!r}")
        clarify = m.get("clarify")
        if "clarify" in m:
            if not isinstance(clarify, dict):
                self.err("type", "clarify", "clarify must be an object")
            else:
                mode = clarify.get("mode", "auto")
                if mode not in ("auto", "skip", "disabled", "off"):
                    self.err("enum", "clarify.mode", f"clarify.mode {mode!r} is not one of auto, skip, disabled, off")
                elif mode in ("disabled", "off"):
                    self.info("clarify", "clarify.mode",
                              f"clarify.mode '{mode}' does not override anything; only 'auto' and 'skip' change behaviour")
                defaults = clarify.get("defaults", [])
                if not isinstance(defaults, list) or not all(isinstance(d, str) and d for d in defaults):
                    self.err("type", "clarify.defaults", "clarify.defaults must be a list of topic id strings")
                elif mode == "auto" and not defaults:
                    self.info("clarify", "clarify.defaults",
                              "clarify.mode is 'auto' with no defaults; list the topics the clarifier should ask about")
                rounds = clarify.get("rounds", 1)
                if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 1:
                    self.err("type", "clarify.rounds", "clarify.rounds must be an integer >= 1")
                if mode == "auto" and planner == "skip":
                    self.warn("clarify", "clarify.mode",
                              "clarify.mode is 'auto' but planner is 'skip': the engine skips the planner and the "
                              "clarifier together, so no question is ever asked",
                              "set planner: run to ask before the run, or clarify.mode: skip to say no questions are asked")
                # engine _apply_selections forces clarify 'skip' when selections carry __deliverable__,
                # and the Composer (Run once and saved workflows) always sends one
                if mode == "auto" and planner == "run" and self.trust in ("user", "db"):
                    self.warn("clarify-launch", "clarify.mode",
                              "a run started from the Composer always selects an output type, which forces clarify "
                              "to skip, so no question is asked",
                              "to ask before the work at this trust, start with an intake step with gates [human], "
                              "redoable: true and reply: last_message (patterns.md section 21), and set planner and clarify "
                              "to skip")
        self.check_deliverable()
        for key, kind in (("context_providers", "context_provider"), ("input_providers", "input_provider")):
            value = m.get(key, [])
            if not isinstance(value, list):
                self.err("type", key, f"{key} must be a list")
                continue
            if len(set(map(str, value))) != len(value):
                self.err("duplicate", key, f"{key} lists a provider twice")
            for i, name in enumerate(value):
                self.check_cap(kind, name, f"{key}[{i}]")
        self.check_seed_files()
        workers = m.get("allowed_workers", [])
        if not isinstance(workers, list) or not all(isinstance(w, str) and w for w in workers):
            self.err("type", "allowed_workers", "allowed_workers must be a list of agent id strings")
        self.check_limits()
        caps = m.get("capabilities")
        if caps is not None:
            if not isinstance(caps, dict):
                self.err("type", "capabilities", "capabilities must be an object")
            else:
                extra_caps = sorted(set(caps) - {"internet"})
                if extra_caps:
                    self.err("unknown-key", "capabilities", f"unknown capabilities key(s) {extra_caps}; only 'internet'")
                if "internet" in caps and not isinstance(caps["internet"], bool):
                    self.err("type", "capabilities.internet", "capabilities.internet must be a boolean")
        if "model" in m:
            self.check_model_policy(m["model"], "model")
        if "chat" in m and not isinstance(m["chat"], dict):
            self.err("type", "chat", "chat must be an object")
        chained = m.get("chained_from", [])
        if not isinstance(chained, list):
            self.err("type", "chained_from", "chained_from must be a list")
        else:
            for i, entry in enumerate(chained):
                where = f"chained_from[{i}]"
                if isinstance(entry, str):
                    src = entry[:-5] if entry.endswith(":beta") else entry
                elif isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"].strip():
                    src = entry["id"]
                else:
                    self.err("type", where, "each chained_from entry is a workflow id string or {id, beta?, text?}")
                    continue
                if self.cat.workflows and src not in self.cat.workflows:
                    self.warn("chain", where, f"chained_from source '{src}' is not a known predefined workflow",
                              "sources are predefined workflow ids that may offer 'chain into this workflow'")
        steps = m.get("steps")
        if "steps" in m and not isinstance(steps, list):
            self.err("type", "steps", "steps must be a list")

    def check_deliverable(self) -> None:
        d = self.m.get("deliverable")
        if "deliverable" not in self.m:
            return
        if not isinstance(d, dict):
            self.err("type", "deliverable", "deliverable must be an object")
            return
        strategy = d.get("strategy")
        if strategy is None:
            self.warn("deliverable", "deliverable.strategy", "deliverable.strategy is missing; declare how the output is produced")
        else:
            self.check_cap("deliverable", strategy, "deliverable.strategy")
        name = d.get("name")
        if name is not None:
            if not isinstance(name, str) or not name:
                self.err("deliverable", "deliverable.name", "deliverable.name must be a non-empty string")
            else:
                if any(sep in name for sep in "/\\:"):
                    self.err("deliverable", "deliverable.name", f"deliverable.name {name!r} must be a plain file name (no / \\ or :)")
                if name in (".", ".."):
                    self.err("deliverable", "deliverable.name", "deliverable.name must not be '.' or '..'")
                if name.lower() in ("logs.jsonl", "summary.md"):
                    self.err("deliverable", "deliverable.name", f"deliverable.name {name!r} collides with a reserved chain file")
        if d.get("chains_from") and not name:
            self.err("deliverable", "deliverable.chains_from", "chains_from: true needs a deliverable.name")
        policy = d.get("chain_policy", "refuse")
        if policy != "refuse":
            self.err("deliverable", "deliverable.chain_policy", f"chain_policy {policy!r} is invalid; the only value is 'refuse'")
        rc = d.get("revision_context", "artifact")
        if rc not in ("artifact", "workspace"):
            self.err("deliverable", "deliverable.revision_context", f"revision_context {rc!r} must be 'artifact' or 'workspace'")
        glob = d.get("publish_from_glob")
        if glob is not None and (not isinstance(glob, str) or glob.count("*") != 1):
            self.err("deliverable", "deliverable.publish_from_glob", "publish_from_glob must contain exactly one '*'")
        for key in ("revises_existing", "chains_from"):
            if key in d and not isinstance(d[key], bool):
                self.err("type", f"deliverable.{key}", f"deliverable.{key} must be a boolean")

    def check_seed_files(self) -> None:
        seeds = self.m.get("seed_files")
        if seeds is None:
            return
        if not isinstance(seeds, dict):
            self.err("type", "seed_files", "seed_files must be an object")
            return
        import posixpath

        for i, entry in enumerate(seeds.get("from_run") or []):
            raw = str(entry)
            norm = posixpath.normpath(raw)
            norm = "" if norm in (".", "/") else norm
            # The compiler rejects any form that STARTS WITH a reserved name, bare or with '/'.
            if any(form and form.startswith(r) for form in (raw, norm) for r in self.cat.reserved):
                self.err("seed-files", f"seed_files.from_run[{i}]", f"seed file {raw!r} names a reserved sandbox path")

    def check_limits(self) -> None:
        limits = self.m.get("limits")
        if limits is None:
            return
        if not isinstance(limits, dict):
            self.err("type", "limits", "limits must be an object")
            return
        extra = sorted(set(limits) - LIMIT_KEYS)
        if extra:
            self.err("unknown-key", "limits", f"unknown limits key(s) {extra}")
        for key in LIMIT_KEYS & set(limits):
            value = limits[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                self.err("type", f"limits.{key}", f"limits.{key} must be a non-negative integer")
        ceiling = self.cat.ceiling(self.profile)
        for key, cap in ceiling.items():
            value = limits.get(key)
            if isinstance(value, int) and value > cap:
                self.err("trust", f"limits.{key}",
                         f"limits.{key}={value} exceeds the {cap} ceiling for '{self.trust}' trust",
                         "a user-trust manifest may only lower budget caps")
        if self.profile == "trusted":
            saved = self.cat.limits.get("saved_ceiling") or {}
            for key, cap in saved.items():
                value = limits.get(key)
                if isinstance(value, int) and value > cap:
                    self.warn("limits", f"limits.{key}",
                              f"limits.{key}={value} is above the largest value any built-in uses ({cap})")

    # ─────────────────────────────────────────── identity tree

    def identity_tree(self, raws: list, depth: int, seen: set, base: str) -> None:
        for i, raw in enumerate(raws):
            path = f"{base}[{i}]"
            if not isinstance(raw, dict):
                self.err("structure", path, "every step must be an object")
                continue
            where = self.where(raw, path)
            extra = sorted(set(raw) - STEP_KEYS)
            if extra:
                self.err("unknown-key", where, f"unknown step key(s) {extra}",
                         "manifests are pure data; there is no if/when/for or comment field")
            iid = raw.get("instance_id")
            if iid is not None:
                if not isinstance(iid, str) or not INSTANCE_ID_RE.match(iid):
                    self.err("instance-id", where, f"invalid instance_id {iid!r}; it must match ^[a-z0-9][a-z0-9-]*$")
                elif iid in seen:
                    self.err("instance-id", where, f"duplicate instance_id '{iid}'; ids are unique across the whole tree")
                else:
                    seen.add(iid)
            if raw.get("prompt") and raw.get("agent") != CUSTOM:
                self.err("prompt", where, "'prompt' is only valid on a custom-agent step",
                         "built-in agents keep their AGENT.md prompt; use custom-agent for bespoke instructions")
            sub = raw.get("subagents")
            if sub is None:
                continue
            if not isinstance(sub, dict):
                self.err("subagents", where, "subagents must be an object")
                continue
            extra_sub = sorted(set(sub) - SUBAGENT_KEYS)
            if extra_sub:
                self.err("unknown-key", where, f"unknown subagents key(s) {extra_sub}")
            mode = sub.get("mode")
            if mode not in SUBAGENT_MODES:
                self.err("subagents", where, f"subagents.mode {mode!r} must be one of {', '.join(SUBAGENT_MODES)}")
            if mode == "fanout" and not sub.get("task_source"):
                self.err("subagents", where, "subagents.mode 'fanout' needs a task_source")
            if mode != "fanout" and sub.get("task_source") is not None:
                self.err("subagents", where, "subagents.task_source is only valid with mode 'fanout'")
            mp = sub.get("max_parallel")
            if mp is not None and (not isinstance(mp, int) or isinstance(mp, bool) or mp < 1):
                self.err("subagents", where, "subagents.max_parallel must be an integer >= 1")
            children = sub.get("steps")
            if not isinstance(children, list) or not children:
                self.err("subagents", where, "subagents.steps must be a non-empty list")
                continue
            if mode == "fanout" and len(children) > 1:
                self.err("subagents", where, "a fanout group clones ONE worker template; declare exactly one child step")
            if len(children) > COMPOSER_MAX_CHILDREN:
                self.warn("composer", where, f"{len(children)} direct sub-agents; the Composer canvas shows at most {COMPOSER_MAX_CHILDREN}")
            if depth + 1 > 2:
                self.err("subagents", where, "subagents nest deeper than two levels (root, child, grandchild)")
                continue
            self.identity_tree(children, depth + 1, seen, f"{path}.subagents.steps")

    @staticmethod
    def where(raw: dict, path: str) -> str:
        label = raw.get("instance_id") or raw.get("agent") or "?"
        return f"{path} ({label})"

    # ─────────────────────────────────────────── expansion + per-step compile

    def expand(self, raw: dict, path: str, depth: int, parent: str) -> tuple[list, CStep]:
        flat: list[CStep] = []
        extra_deps: list[str] = []
        direct: list[CStep] = []
        sub = raw.get("subagents") if isinstance(raw.get("subagents"), dict) else None
        mode = sub.get("mode") if sub else None
        children = [c for c in (sub.get("steps") or []) if isinstance(c, dict)] if sub else []
        own = self.compile_step(raw, path, depth)
        if sub and mode == "fanout" and children:
            child_flat, child = self.expand(children[0], f"{path}.subagents.steps[0]", depth + 1, own.agent_id)
            flat.extend(child_flat)
            child.task_source = sub.get("task_source") if isinstance(sub.get("task_source"), dict) else None
            if child.task_source is not None:
                self.check_task_source(child.task_source, f"{path}.subagents.task_source")
            child.fanout = {"mode": "parallel", "max_parallel": sub.get("max_parallel"), "agent": "self"}
            child.strategy = "fanout_batch"
            child.group_mode = "fanout"
            extra_deps = [child.agent_id]
            direct = [child]
        elif sub and mode in ("parallel", "sequential"):
            for j, child_raw in enumerate(children):
                child_flat, child = self.expand(child_raw, f"{path}.subagents.steps[{j}]", depth + 1, own.agent_id)
                flat.extend(child_flat)
                child.group_mode = mode
                direct.append(child)
            if mode == "sequential":
                for j in range(1, len(direct)):
                    prev = direct[j - 1].agent_id
                    if prev not in direct[j].depends_on:
                        direct[j].depends_on = list(direct[j].depends_on) + [prev]
            extra_deps = [c.agent_id for c in direct]
            if mode == "parallel":
                for child in direct:
                    child.dispatched_by = own.agent_id
                own.strategy = "parallel_group"
                own.fanout = {"mode": "parallel", "max_parallel": sub.get("max_parallel"),
                              "workers": [c.agent_id for c in direct], "count": len(direct)}
        own.children = [c.agent_id for c in direct]
        own.parent = parent
        for dep in extra_deps:
            if dep not in own.depends_on:
                own.depends_on = list(own.depends_on) + [dep]
        flat.append(own)
        if depth == 0:
            self.steps.extend(flat)
        return flat, own

    def compile_step(self, raw: dict, path: str, depth: int) -> CStep:
        where = self.where(raw, path)
        agent = raw.get("agent")
        if not isinstance(agent, str) or not agent.strip():
            self.err("agent", where, "step needs a non-empty 'agent'")
            agent = "?"
        iid = raw.get("instance_id") if isinstance(raw.get("instance_id"), str) else ""
        agent_id = f"{CUSTOM}:{iid}" if agent == CUSTOM and iid else agent

        strategy = raw.get("strategy", "single_shot")
        self.check_cap("strategy", strategy, f"{where}.strategy")

        mechanical = raw.get("mechanical")
        if mechanical is not None:
            if mechanical not in self.cat.mechanical:
                self.err("mechanical", where, f"unknown mechanical kind {mechanical!r}; one of {', '.join(self.cat.mechanical)}")
            if raw.get("tools") is not None:
                self.err("mechanical", where, "a mechanical step runs no agent, so it cannot declare 'tools'")

        gates = raw.get("gates", []) or []
        if not isinstance(gates, list):
            self.err("type", f"{where}.gates", "gates must be a list")
            gates = []
        for g in gates:
            self.check_cap("gate", g, f"{where}.gates")
        hitl = [g for g in gates if g in HITL_GATES]
        if len(hitl) > 1:
            self.err("hitl", where, f"more than one human-review gate ({', '.join(hitl)}); a step may declare at most one")

        raw_hooks = raw.get("hooks")
        if raw_hooks is None:
            hooks = [h for h in DEFAULT_HOOKS if self.cat.registered("hook", h)]
        elif isinstance(raw_hooks, list):
            hooks = list(raw_hooks)
            for h in hooks:
                self.check_cap("hook", h, f"{where}.hooks")
        else:
            self.err("type", f"{where}.hooks", "hooks must be a list")
            hooks = []

        validators = raw.get("validators", []) or []
        if not isinstance(validators, list):
            self.err("type", f"{where}.validators", "validators must be a list")
            validators = []
        for v in validators:
            self.check_cap("validator", v, f"{where}.validators")
        for key, kind in (("compaction", "compaction"), ("post_step", "post_step")):
            if raw.get(key) is not None:
                self.check_cap(kind, raw.get(key), f"{where}.{key}")

        task_source = raw.get("task_source")
        if task_source is not None:
            if isinstance(task_source, dict):
                self.check_task_source(task_source, f"{where}.task_source")
            else:
                self.err("type", f"{where}.task_source", "task_source must be an object")
                task_source = None

        requested, effective = self.check_tools(raw, where, gates)

        fanout = raw.get("fanout")
        if fanout is not None:
            if not isinstance(fanout, dict):
                self.err("type", f"{where}.fanout", "fanout must be an object")
                fanout = None
            else:
                extra = sorted(set(fanout) - FANOUT_KEYS)
                if extra:
                    self.err("unknown-key", f"{where}.fanout", f"unknown fanout key(s) {extra}")
        route = raw.get("route")
        if route is not None:
            route = self.check_route(route, where)
        produces = list(raw.get("produces") or []) if isinstance(raw.get("produces", []), list) else []
        consumes = list(raw.get("consumes") or []) if isinstance(raw.get("consumes", []), list) else []
        reply = raw.get("reply", "all")
        if reply not in ("all", "last_message"):
            self.err("enum", f"{where}.reply", f"reply {reply!r} must be 'all' or 'last_message'")
        has_outcomes = bool(route and route.get("outcomes"))
        if "conditional" in gates and not has_outcomes:
            self.err("route", where, "gates include 'conditional' but there is no route with outcomes")
        if has_outcomes and "conditional" not in gates:
            self.err("route", where, "route declared but gates lack 'conditional'")
        oc = raw.get("on_conflict", "human_gate") or "human_gate"
        if oc not in self.cat.on_conflict:
            self.err("enum", f"{where}.on_conflict", f"on_conflict {oc!r} must be one of {', '.join(self.cat.on_conflict)}")
        if "model" in raw:
            self.check_model_policy(raw["model"], f"{where}.model")
        self.check_simple_block(raw.get("retry"), RETRY_KEYS, f"{where}.retry")
        retry = raw.get("retry")
        if isinstance(retry, dict) and any(o != "transient" for o in retry.get("on", []) or []):
            self.err("enum", f"{where}.retry.on", "retry.on only supports 'transient'")
        self.check_simple_block(raw.get("fix"), FIX_KEYS, f"{where}.fix")
        fix = raw.get("fix")
        if isinstance(fix, dict) and fix.get("mode", "off") not in ("off", "internal", "gated"):
            self.err("enum", f"{where}.fix.mode", "fix.mode must be off, internal or gated")
        injects = raw.get("injects", []) or []
        for inj in injects if isinstance(injects, list) else []:
            if inj not in INJECTS:
                self.err("enum", f"{where}.injects", f"unknown inject {inj!r}; one of {', '.join(INJECTS)}")
        depends_on = raw.get("depends_on", []) or []
        if not isinstance(depends_on, list) or not all(isinstance(d, str) and d for d in depends_on):
            self.err("type", f"{where}.depends_on", "depends_on must be a list of step id strings")
            depends_on = []
        skills = raw.get("skills", []) or []
        if not isinstance(skills, list):
            self.err("type", f"{where}.skills", "skills must be a list")
            skills = []
        for key in ("produces_solution_plan", "redoable", "replaces"):
            if key in raw and not isinstance(raw[key], bool):
                self.warn("type", f"{where}.{key}", f"{key} should be a boolean")
        if "require_render" in raw and raw["require_render"] is not None and not isinstance(raw["require_render"], bool):
            self.err("type", f"{where}.require_render", "require_render must be a boolean or null")
        for key in ("name", "prompt", "condition"):
            if key in raw and raw[key] is not None and not isinstance(raw[key], str):
                self.err("type", f"{where}.{key}", f"{key} must be a string")

        return CStep(
            agent_id=agent_id, agent=agent, instance_id=iid, name=str(raw.get("name") or ""), raw=raw,
            where=where, path=path, depth=depth, strategy=str(strategy), gates=list(gates),
            depends_on=list(depends_on), route=route, produces=produces, consumes=consumes,
            tools_requested=requested, tools=effective,
            task_source=task_source if isinstance(task_source, dict) else None,
            fanout=fanout if isinstance(fanout, dict) else None, mechanical=mechanical, hooks=hooks,
            validators=list(validators), skills=list(skills), reply=str(reply),
        )

    def check_prompt_standard(self, s: "CStep") -> None:
        """Depth and sections of a working custom-agent prompt (quick-reference section 8).
        Decision steps and human-choice placeholders are short on purpose."""
        prompt = s.raw.get("prompt") or ""
        if s.mechanical or not prompt.strip():
            return
        if "route_decision" in s.produces or "conditional" in s.gates or "awaiting choice" in prompt.lower():
            return
        if len(prompt) < MIN_PROMPT_CHARS:
            self.warn("prompt-depth", s.where,
                      f"prompt has {len(prompt)} characters; a step prompt in the standard (quick-reference section 8) "
                      "is usually 3,000-7,000, as in the shipped examples",
                      "write every section of the standard for this step's job (role, what you receive, phases with "
                      "rules and numbered steps, missing input, output, checks, delivery); do not pad it")
        low = prompt.lower()
        missing = [label for label, needles in PROMPT_PARTS if not any(n in low for n in needles)]
        if missing:
            self.info("prompt-structure", s.where, f"prompt lacks part(s) of the standard: {', '.join(missing)}",
                      "see quick-reference section 8 and catalog_lookup.py example prototype_v2 fi-close")

    def check_simple_block(self, block: Any, keys: set, where: str) -> None:
        if block is None:
            return
        if not isinstance(block, dict):
            self.err("type", where, f"{where.rsplit('.', 1)[-1]} must be an object")
            return
        extra = sorted(set(block) - keys)
        if extra:
            self.err("unknown-key", where, f"unknown key(s) {extra}; allowed: {', '.join(sorted(keys))}")
        if "max_attempts" in block and (not isinstance(block["max_attempts"], int) or isinstance(block["max_attempts"], bool)
                                        or block["max_attempts"] < 0):
            self.err("type", f"{where}.max_attempts", "max_attempts must be an integer >= 0")

    def check_task_source(self, ts: dict, where: str) -> None:
        extra = sorted(set(ts) - TASK_SOURCE_KEYS)
        if extra:
            self.err("unknown-key", where, f"unknown task_source key(s) {extra}")
        kind = ts.get("kind", "none")
        if kind not in TASK_SOURCE_KINDS:
            self.err("enum", f"{where}.kind", f"task_source.kind {kind!r} must be one of {', '.join(TASK_SOURCE_KINDS)}")
        parser = ts.get("parser")
        if parser is not None:
            self.check_cap("task_parser", parser, f"{where}.parser")
        if kind == "custom_path" and not (isinstance(ts.get("path"), str) and ts["path"].strip()):
            self.err("task-source", where, "task_source kind 'custom_path' needs a 'path'")
        if kind == "parsed" and not parser:
            self.warn("task-source", where, "task_source kind 'parsed' without a parser; name heading_tasks, json_tasks or screen_plan")

    def check_tools(self, raw: dict, where: str, gates: list) -> tuple[dict, dict]:
        tools = raw.get("tools")
        requested = {f: (f == "read_files") for f in self.cat.bool_fields}
        for f in self.cat.list_fields:
            requested[f] = []
        if tools is None:
            return requested, self.apply_cap(requested)
        if not isinstance(tools, dict):
            self.err("type", f"{where}.tools", "tools must be a permission object")
            return requested, self.apply_cap(requested)
        allowed_keys = set(self.cat.bool_fields) | set(self.cat.list_fields)
        extra = sorted(set(tools) - allowed_keys)
        if extra:
            self.err("unknown-key", f"{where}.tools", f"unknown tools key(s) {extra}; allowed: {', '.join(sorted(allowed_keys))}")
        for f in self.cat.bool_fields:
            if f in tools:
                if not isinstance(tools[f], bool):
                    self.err("type", f"{where}.tools.{f}", f"tools.{f} must be a boolean")
                requested[f] = bool(tools[f])
        for f in self.cat.list_fields:
            if f in tools:
                value = tools[f]
                if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                    self.err("type", f"{where}.tools.{f}", f"tools.{f} must be a list of strings")
                    value = []
                requested[f] = list(value)
        # privileged grants
        if not self.trusted:
            priv = [f for f in ("exec", "network") if requested.get(f)]
            if requested.get("secrets"):
                priv.append("secrets")
            if requested.get("spawn_subagents") and self.profile != "saved":
                priv.append("spawn_subagents")
            if priv:
                self.err("trust", f"{where}.tools", f"grant of {priv} is not permitted for '{self.trust}' trust",
                         "declarative fan-out (subagents, fanout_batch, wave_scheduler) needs no spawn grant")
        if requested.get("exec"):
            missing = sorted({"security", "approval"} - set(gates))
            if missing:
                self.err("exec-gates", where, f"tools.exec needs gates 'security' and 'approval' (missing {missing})")
            if self.trusted and self.trust not in self.cat.exec_trust:
                self.err("runtime-block", f"{where}.tools.exec",
                         f"exec compiles at '{self.trust}' trust, but the runtime security gate refuses exec below "
                         "file/builtin trust, so the run fails at this step",
                         "ship it as an engineer workflow (file trust), or remove exec and the code_* validators")
        # The security gate is default-deny for network and secrets in this platform build.
        for grant in ("secrets", "network"):
            if requested.get(grant) and self.trusted:
                if "security" in gates:
                    self.err("runtime-block", f"{where}.tools.{grant}",
                             f"the security gate blocks every step that grants {grant}, so the run fails at this step")
                else:
                    self.warn("tools", f"{where}.tools.{grant}", f"tools.{grant} binds nothing in this platform build")
        # MCP
        has_security = "security" in gates
        for ref in requested.get("mcp") or []:
            if "." not in ref:
                self.err("mcp", f"{where}.tools.mcp", f"mcp reference {ref!r} must be 'server.tool'")
                continue
            server, _, tool = ref.partition(".")
            entry = self.cat.mcp.get(server)
            if self.cat.caps and not self.cat.registered("mcp_server", server):
                self.err("mcp", f"{where}.tools.mcp", f"unknown MCP server '{server}' in {ref!r}")
                continue
            if not self.allowed("mcp_server", server):
                self.err("trust", f"{where}.tools.mcp", f"MCP server '{server}' is not allowed for '{self.trust}' trust")
            if entry is not None:
                if tool not in (entry.get("tools") or []):
                    self.err("mcp", f"{where}.tools.mcp", f"{ref!r} is not an exposed tool; {server} exposes {', '.join(entry.get('tools') or [])}")
                if entry.get("powerful") and not (has_security and requested.get("secrets")):
                    self.err("mcp", f"{where}.tools.mcp", f"'{server}' is a powerful server: the step needs gate 'security' and a 'secrets' grant")
        scopes = set((self.cat.data.get("integration_scopes") or {}).keys()) or {"github_read", "gitlab_read", "jira_read", "slack_post"}
        for scope in requested.get("integrations") or []:
            if scope not in scopes:
                self.err("capability", f"{where}.tools.integrations", f"unknown integration scope {scope!r}; one of {', '.join(sorted(scopes))}")
        known_sets = set(self.cat.names("tool")) or set(self.cat.cap("trusted").get("tool_sets") or [])
        for ts_name in requested.get("tool_sets") or []:
            if known_sets and ts_name not in known_sets:
                self.err("capability", f"{where}.tools.tool_sets", f"unknown tool set {ts_name!r}; one of {', '.join(sorted(known_sets))}")
        effective = self.apply_cap(requested)
        dropped = [t for t in requested.get("tool_sets") or [] if t not in effective.get("tool_sets", []) and t in known_sets]
        if dropped:
            self.warn("tool-sets", f"{where}.tools.tool_sets",
                      f"tool set(s) {dropped} are silently dropped under '{self.trust}' trust",
                      f"the {self.profile} cap keeps only {', '.join(self.cat.cap(self.profile).get('tool_sets') or []) or 'none'}")
        return requested, effective

    def apply_cap(self, requested: dict) -> dict:
        cap = self.cat.cap(self.profile)
        out: dict = {}
        for f in self.cat.bool_fields:
            out[f] = bool(requested.get(f)) and bool(cap.get(f, False))
        out["tool_sets"] = [t for t in requested.get("tool_sets") or [] if t in (cap.get("tool_sets") or [])]
        for f in self.cat.list_fields:
            if f != "tool_sets":
                out[f] = list(requested.get(f) or [])
        return out

    def check_route(self, route: Any, where: str) -> dict | None:
        if not isinstance(route, dict):
            self.err("type", f"{where}.route", "route must be an object")
            return None
        extra = sorted(set(route) - ROUTE_KEYS)
        if extra:
            self.err("unknown-key", f"{where}.route", f"unknown route key(s) {extra}")
        outcomes = route.get("outcomes") or {}
        if not isinstance(outcomes, dict):
            self.err("type", f"{where}.route.outcomes", "route.outcomes must be an object")
            outcomes = {}
        for key, outcome in outcomes.items():
            w = f"{where}.route.outcomes.{key}"
            if not isinstance(outcome, dict):
                self.err("type", w, "each outcome is an object {trigger, target, feedback?}")
                continue
            extra_o = sorted(set(outcome) - OUTCOME_KEYS)
            if extra_o:
                self.err("unknown-key", w, f"unknown outcome key(s) {extra_o}")
            trigger = outcome.get("trigger")
            if trigger not in ("step", "workflow", "end"):
                self.err("route", w, f"trigger must be 'step', 'workflow' or 'end', got {trigger!r}")
            target = outcome.get("target")
            if trigger == "end":
                # 'end' finishes the run at this step: it names no destination and carries no retry guidance.
                for inert in ("target", "feedback"):
                    if outcome.get(inert) not in (None, ""):
                        self.err("route", w, f"trigger 'end' finishes the run and takes no {inert}; remove it")
            elif not isinstance(target, str) or not target.strip():
                self.err("route", w, "target must be a non-empty string")
            if "feedback" in outcome and outcome["feedback"] is not None and not isinstance(outcome["feedback"], str):
                self.err("type", w, "feedback must be a string")
        if route.get("trigger_max_depth", 5) != 5:
            self.err("route", f"{where}.route.trigger_max_depth", "trigger_max_depth is fixed at 5; omit it")
        if route.get("on_loop_exhausted", "continue") not in ("continue", "fail"):
            self.err("route", f"{where}.route.on_loop_exhausted", "on_loop_exhausted must be 'continue' or 'fail'")
        lmi = route.get("loop_max_iterations", 5)
        if not isinstance(lmi, int) or isinstance(lmi, bool) or lmi < 1:
            self.err("route", f"{where}.route.loop_max_iterations", "loop_max_iterations must be an integer >= 1")
        clean = dict(route)
        clean["outcomes"] = {k: v for k, v in outcomes.items() if isinstance(v, dict)}
        return clean

    def check_model_policy(self, policy: Any, where: str) -> None:
        if not isinstance(policy, dict):
            self.err("type", where, "model must be an object {model, effort, fallback, cost_class, max_tokens}")
            return
        extra = sorted(set(policy) - MODEL_KEYS)
        if extra:
            self.err("unknown-key", where, f"unknown model key(s) {extra}")
        model_id = policy.get("model")
        entry = None
        if model_id is not None:
            if not isinstance(model_id, str) or not model_id:
                self.err("model", f"{where}.model", "model.model must be a model id string")
            elif self.cat.models:
                entry = self.cat.model_exact(model_id)
                if entry is None:
                    near = self.cat.model(model_id)
                    hint = f"did you mean '{near['id']}'?" if near else "pick an id from docs/catalog.md (Models)"
                    self.err("model", f"{where}.model", f"model '{model_id}' is not in the model catalog; launch rejects it", hint)
                elif not entry.get("user_allowed", True):
                    self.err("model", f"{where}.model", f"model '{model_id}' is not user-allowed")
                elif entry.get("cost_class") == "premium":
                    self.info("model", f"{where}.model",
                              f"'{model_id}' is premium; accounts on the basic tier cannot launch it")
        for i, fb in enumerate(policy.get("fallback") or []):
            if self.cat.models and self.cat.model_exact(str(fb)) is None:
                self.err("model", f"{where}.fallback[{i}]", f"fallback model '{fb}' is not in the model catalog")
        cc = policy.get("cost_class", "standard")
        if cc not in ("premium", "standard", "cheap"):
            self.err("enum", f"{where}.cost_class", "cost_class must be premium, standard or cheap")
        if "max_tokens" in policy:
            mt = policy["max_tokens"]
            if not isinstance(mt, int) or isinstance(mt, bool) or mt < 1:
                self.err("type", f"{where}.max_tokens", "max_tokens must be a positive integer")
            else:
                self.info("model", f"{where}.max_tokens",
                          "model.max_tokens is parsed but the current runtime does not apply it; output uses the model ceiling")
        effort = policy.get("effort")
        if effort is not None:
            resolved = entry or (self.cat.model(model_id) if isinstance(model_id, str) and model_id else None)
            if resolved is not None:
                valid = list((resolved.get("reasoning") or {}).get("levels") or [])
                if (resolved.get("reasoning") or {}).get("mode") in ("adaptive", "budget") and "on" not in valid:
                    valid.append("on")
            else:
                valid = list(self.cat.effort_levels)
            if effort not in valid:
                self.err("effort", f"{where}.effort",
                         f"effort {effort!r} is not valid for {model_id or 'the default model'}; accepts {valid or 'none'}",
                         "set model.model alongside effort so it is checked against that model's own levels")

    # ─────────────────────────────────────────── graph checks

    def check_dag(self) -> None:
        seen: set[str] = set()
        for s in self.steps:
            if s.agent_id in seen:
                hint = ("give each custom-agent step its own instance_id" if s.agent == CUSTOM
                        else "a built-in agent may appear only once per workflow; use custom-agent steps for repeats")
                self.err("duplicate-id", s.where, f"duplicate compiled step id '{s.agent_id}'", hint)
            seen.add(s.agent_id)
        ids = [s.agent_id for s in self.steps]
        index = {a: 0 for a in ids}
        adj: dict[str, list[str]] = {a: [] for a in ids}
        for s in self.steps:
            for dep in s.depends_on:
                if dep in index and s.agent_id in index:
                    adj[dep].append(s.agent_id)
                    index[s.agent_id] += 1
        queue = [a for a, d in index.items() if d == 0]
        removed = 0
        while queue:
            node = queue.pop()
            removed += 1
            for nxt in adj[node]:
                index[nxt] -= 1
                if index[nxt] == 0:
                    queue.append(nxt)
        if removed != len(index):
            stuck = sorted(a for a, d in index.items() if d > 0)
            self.err("cycle", "steps", f"cycle in depends_on among {stuck}",
                     "use a conditional route for loops; depends_on must stay acyclic")

    def check_fanout_sources(self) -> None:
        upstream: set[str] = set()
        for s in self.steps:
            src = (s.task_source or {}).get("source_step")
            if s.strategy == "fanout_batch" and src and src not in upstream:
                self.err("fanout-source", s.where, f"task_source.source_step '{src}' does not name an EARLIER step",
                         "the task-list producer must come before the fan-out (children run before their parent)")
            upstream.add(s.agent_id)

    def check_route_has_exit(self, step: Any, route: dict, index_of: dict[str, int]) -> None:
        """A loop-only route cannot succeed: the engine fails a decision that matches no outcome.

        When every outcome jumps back to this step or an earlier one, and there is no 'end'
        outcome, forward outcome, workflow hand-off or default_next, the only way the run leaves
        the loop is by exhausting loop_max_iterations. The decision that means "done" (for example
        "pass") matches nothing, and a decision that matches nothing and has no default_next ends
        the run as failed. Declaring that decision as {"trigger": "end"} is the fix.
        """
        outcomes = route.get("outcomes") or {}
        if not outcomes or route.get("default_next"):
            return
        here = index_of.get(step.agent_id, -1)
        for outcome in outcomes.values():
            trigger = outcome.get("trigger")
            if trigger in ("end", "workflow"):
                return
            if trigger == "step" and index_of.get(outcome.get("target"), -1) > here:
                return
        self.err("route-no-exit", f"{step.where}.route",
                 "every outcome loops back and none ends the run, so the decision that means 'done' matches nothing "
                 "and fails the run",
                 "add an outcome for it, for example \"pass\": {\"trigger\": \"end\"}, or a forward step outcome, "
                 "or set route.default_next")

    def check_routes(self) -> None:
        ids = {s.agent_id for s in self.steps} | {s.instance_id for s in self.steps if s.instance_id}
        index_of: dict[str, int] = {}
        for i, s in enumerate(self.steps):
            index_of[s.agent_id] = i
            if s.instance_id:
                index_of.setdefault(s.instance_id, i)
        for s in self.steps:
            route = s.route
            if not route:
                continue
            for key, outcome in (route.get("outcomes") or {}).items():
                target = outcome.get("target")
                if outcome.get("trigger") == "step" and target not in ids:
                    self.err("route", f"{s.where}.route.outcomes.{key}", f"step target '{target}' is not a step in this workflow")
                if outcome.get("trigger") == "workflow" and isinstance(target, str):
                    if target != "self" and not UUID_RE.match(target) and self.cat.workflows and target not in self.cat.workflows:
                        self.warn("route", f"{s.where}.route.outcomes.{key}",
                                  f"workflow target '{target}' is not a known predefined workflow id or a saved-workflow UUID",
                                  "targets are resolved and tier-checked when the trigger fires")
                    if not outcome.get("feedback"):
                        self.warn("route", f"{s.where}.route.outcomes.{key}",
                                  "a triggered child run starts with an empty message; 'feedback' is the only thing it receives")
            default_next = route.get("default_next")
            if default_next is not None and default_next not in ids:
                self.err("route", f"{s.where}.route.default_next", f"default_next '{default_next}' is not a step in this workflow")
            self.check_route_has_exit(s, route, index_of)
            if route.get("outcomes"):
                ref = route.get("condition_agent") or s.agent_id
                source = self.by_name.get(ref)
                if source is None:
                    self.err("route", f"{s.where}.route.condition_agent", f"condition_agent '{ref}' is not a step in this workflow")
                elif "route_decision" not in source.produces:
                    self.err("route", s.where, f"decision source '{source.agent_id}' must declare produces: [\"route_decision\"]")

    def compute_leaves(self) -> None:
        index_of: dict[str, int] = {}
        for i, s in enumerate(self.steps):
            index_of[s.agent_id] = i
            if s.instance_id:
                index_of.setdefault(s.instance_id, i)
        depended = {d for s in self.steps for d in s.depends_on}
        jump_targets: set[int] = set()
        for i, s in enumerate(self.steps):
            if not s.route:
                continue
            for o in (s.route.get("outcomes") or {}).values():
                t = index_of.get(o.get("target")) if o.get("trigger") == "step" else None
                if t is not None and t > i:
                    jump_targets.add(t)
            dn = index_of.get(s.route.get("default_next")) if s.route.get("default_next") else None
            if dn is not None and dn > i:
                jump_targets.add(dn)
        for i, s in enumerate(self.steps):
            if s.agent_id in depended:
                s.is_leaf = False
            elif s.route and s.route.get("outcomes"):
                s.is_leaf = not (any(o.get("trigger") == "step" for o in s.route["outcomes"].values())
                                 or bool(s.route.get("default_next")))
            else:
                s.is_leaf = (i + 1 >= len(self.steps)) or ((i + 1) in jump_targets)

    def reachable(self) -> set[str]:
        steps = self.steps
        if not steps:
            return set()
        index_of: dict[str, int] = {}
        for i, s in enumerate(steps):
            index_of[s.agent_id] = i
            if s.instance_id:
                index_of.setdefault(s.instance_id, i)

        def next_serial(i: int) -> int | None:
            j = i + 1
            while j < len(steps) and steps[j].dispatched_by:
                j += 1
            return j if j < len(steps) else None

        start = 0
        while start < len(steps) and steps[start].dispatched_by:
            start += 1
        seen: set[int] = set()
        stack = [start] if start < len(steps) else []
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            s = steps[i]
            succ: list[int | None] = []
            if s.route and s.route.get("outcomes"):
                backward = False
                for o in s.route["outcomes"].values():
                    if o.get("trigger") == "step" and o.get("target") in index_of:
                        t = index_of[o["target"]]
                        succ.append(t)
                        backward = backward or t <= i
                if s.route.get("default_next") in index_of:
                    succ.append(index_of[s.route["default_next"]])
                if backward and s.route.get("on_loop_exhausted", "continue") == "continue":
                    succ.append(next_serial(i))
            elif not s.is_leaf:
                succ.append(next_serial(i))
            stack.extend(x for x in succ if x is not None and x not in seen)
        reached = {steps[i].agent_id for i in seen}
        # parallel children run when their parent runs
        for s in steps:
            if s.dispatched_by and s.dispatched_by in reached:
                reached.add(s.agent_id)
        return reached

    # ─────────────────────────────────────────── design lint

    def lint(self) -> None:
        m = self.m
        steps = self.steps
        d = m.get("deliverable") if isinstance(m.get("deliverable"), dict) else {}
        strategy = d.get("strategy")
        context = list(m.get("context_providers") or []) if isinstance(m.get("context_providers"), list) else []
        top_level = [s for s in steps if s.depth == 0]
        if len(top_level) > COMPOSER_MAX_ROOTS:
            self.warn("composer", "steps", f"{len(top_level)} top-level steps; the Composer canvas holds at most {COMPOSER_MAX_ROOTS}",
                      "group work under subagents, use a fan-out, or split into chained workflows")

        # agents: who produces what (the resolver matches consumes against these)
        producers: dict[str, set[str]] = {}

        def _produce(label: str, step_id: str) -> None:
            producers.setdefault(label, set()).add(step_id)

        for s in steps:
            for label in s.produces:
                _produce(label, s.agent_id)
            if s.agent != CUSTOM and s.agent in self.cat.agents:
                for label in self.cat.agents[s.agent].get("produces") or []:
                    _produce(label, s.agent_id)
            if s.mechanical:
                for label in ((self.cat.caps.get("mechanical") or {}).get(s.mechanical) or {}).get("writes") or []:
                    _produce(label, s.agent_id)
        uses_step_consumes = any(s.consumes for s in steps)
        for s in steps:
            needs = list(s.consumes)
            if s.agent != CUSTOM and s.agent in self.cat.agents:
                needs = list(self.cat.agents[s.agent].get("consumes") or []) + needs
            needs = [c for c in dict.fromkeys(needs) if c not in EXEMPT_CONSUMES]
            if needs:
                satisfied = [c for c in needs if producers.get(c, set()) - {s.agent_id}]
                if not satisfied:
                    self.err("consumes", s.where, f"consumes {needs}, but no other step produces any of them",
                             "the resolver refuses a step with no satisfied input; add the producer, or drop consumes "
                             "and let the step read earlier files itself")
                elif len(satisfied) < len(needs):
                    unmet = [c for c in needs if c not in satisfied]
                    self.info("consumes", s.where, f"consumes entries {unmet} have no producer and are ignored")
        for s in steps:
            if s.agent == CUSTOM:
                if not s.instance_id:
                    self.warn("custom-agent", s.where, "custom-agent step without instance_id",
                              "every custom-agent step needs a unique kebab-case instance_id")
                if not (s.raw.get("prompt") or "").strip() and not s.mechanical:
                    self.warn("custom-agent", s.where, "custom-agent step without a prompt runs on the generic preamble only")
                self.check_prompt_standard(s)
                if not s.name:
                    self.info("custom-agent", s.where, "add a 'name' so the step shows a readable label")
                if "tools" not in s.raw and not s.mechanical:
                    self.info("tools", s.where, "no tools block: the step gets read_files: true, write_files: false",
                              "declare tools on every step so the grant is visible; a paste hand-off needs read_files: false")
            elif s.agent != "?" and self.cat.agents:
                spec = self.cat.agents.get(s.agent)
                if spec is None:
                    self.err("agent", s.where, f"unknown agent '{s.agent}'; no AGENT.md with that id",
                             "use agent 'custom-agent' with an instance_id and prompt, or refresh the catalog")
                    continue
                if spec.get("template"):
                    self.warn("agent", s.where, f"'{s.agent}' is a template agent; give it an instance_id and prompt")
                needs_design = [i for i in spec.get("injects") or [] if i in ("template", "design_system", "template_example", "craft")]
                if needs_design and "opendesign" not in context:
                    self.warn("template-context", s.where,
                              f"agent '{s.agent}' injects {needs_design} but the workflow does not declare the opendesign "
                              "provider, so it runs without design context")
                pipeline = spec.get("pipeline_type")
                used_in = spec.get("used_in") or []
                if used_in and pipeline != "custom" and m.get("id") not in used_in:
                    self.info("agent", s.where, f"'{s.agent}' is built for {', '.join(used_in)}; check its contract fits this workflow")

        # ordering pins: step-level consumes give the resolver edges it may re-sort by
        if uses_step_consumes:
            unpinned = [s.agent_id for i, s in enumerate(top_level) if i > 0 and "depends_on" not in s.raw]
            if unpinned:
                self.warn("order-pin", "steps",
                          f"steps declare consumes, so the resolver may re-sort the plan; these top-level steps have no depends_on: {unpinned}",
                          "pin the intended order: give each step depends_on: [<previous compiled id>]")

        # depends_on references
        ids = {s.agent_id for s in steps}
        for s in steps:
            for dep in s.raw.get("depends_on") or []:
                if dep not in ids:
                    hint = f"use '{CUSTOM}:{dep}'" if f"{CUSTOM}:{dep}" in ids else "use a compiled step id"
                    self.warn("depends-on", s.where, f"depends_on '{dep}' matches no compiled step id and is silently ignored", hint)

        # reachability
        reached = self.reachable()
        for s in steps:
            if s.agent_id not in reached:
                self.err("unreachable", s.where, f"step '{s.agent_id}' can never run on any path",
                         "an earlier step ends the run (leaf) or routes past it; add depends_on or a route outcome")

        # decision steps, gates, validators, tools
        for s in steps:
            prompt = s.raw.get("prompt") or ""
            if "route_decision" in s.produces and s.agent == CUSTOM:
                outcome_keys: set[str] = set()
                human_supplied = False
                for other in steps:
                    if other.route and (other.route.get("condition_agent") or other.agent_id) in (s.agent_id, s.instance_id):
                        outcome_keys.update((other.route.get("outcomes") or {}).keys())
                        # a person types the decision into this step's output at the next step's before-human gate
                        human_supplied = human_supplied or (other is not s and "before-human" in other.gates)
                if prompt and outcome_keys and not human_supplied:
                    if '"decision"' not in prompt:
                        self.warn("decision-prompt", s.where, 'decision prompt never shows the {"decision": "..."} reply shape')
                    absent = sorted(k for k in outcome_keys if k not in prompt)
                    if absent:
                        self.warn("decision-prompt", s.where, f"decision prompt does not mention outcome(s) {absent}")
                if s.tools.get("write_files") and s.reply != "last_message":
                    self.warn("decision-reply", s.where, "decision step can write files but reply is 'all'",
                              "set reply: last_message so only the final JSON line is routed")
            if "redoable" in s.raw and s.raw.get("redoable") and "human" not in s.gates:
                self.warn("gates", s.where, "redoable has no effect without a 'human' gate")
            if "human" in s.gates and (s.tools.get("write_files") or s.tools.get("tool_sets")) and s.reply != "last_message":
                self.info("gates", s.where, "reviewers see every streamed word; reply: last_message shows only the final message")
            if "before-human" in s.gates and "conditional" in s.gates and not (s.route or {}).get("condition_agent"):
                self.info("gates", s.where, "before-human edits the PREVIOUS step's output; set route.condition_agent to that step "
                                            "so the person's answer is the decision")
            if s.validators and "validation" not in s.gates and s.strategy != "task_loop":
                self.warn("validators", s.where, "validators only run behind the 'validation' gate (or inside task_loop)",
                          "add 'validation' to gates")
            if "validation" in s.gates and not s.validators:
                self.warn("validators", s.where, "'validation' gate with no validators does nothing")
            if "validation" in s.gates and s.validators and not (s.raw.get("fix") or {}).get("max_attempts"):
                self.info("validators", s.where, "no fix.max_attempts: the first critical finding fails the run",
                          "add fix: {max_attempts: 2} to retry the step with the findings")
            if s.validators and not s.is_leaf:
                self.info("validators", s.where, f"validators check the deliverable file ({d.get('text_name') or d.get('name') or '?'}) "
                                                 "as it exists after this step, not this step's own reply")
            name = str(d.get("text_name") or d.get("name") or "")
            for v in s.validators:
                if v in ("html_static", "html_render") and not name.lower().endswith((".html", ".htm")):
                    self.warn("validators", s.where, f"'{v}' checks a single-file HTML prototype, but the deliverable is '{name}'")
                if v in ("code_compile", "code_test", "code_lint") and not s.tools.get("exec"):
                    self.warn("validators", s.where, f"'{v}' needs an exec grant (engineer-shipped file trust only); "
                                                     "without it it is skipped with a warning")
            if s.raw.get("require_render") and "html_render" not in s.validators:
                self.info("validators", s.where, "require_render only affects html_render")
            if s.skills:
                for sk in s.skills:
                    if self.cat.skills and sk not in self.cat.skills:
                        self.warn("skill", s.where, f"skill '{sk}' is not in the skills catalog; unknown ids are dropped at run time")
                if not s.tools.get("read_files"):
                    self.warn("skill", s.where, "skills are staged as files; the step needs read_files: true to open them")
            if s.raw.get("injects") and "opendesign" not in context:
                self.warn("injects", s.where, "injects have no effect unless context_providers includes 'opendesign'")
            if s.tools_requested.get("git"):
                self.info("tools", s.where, "tools.git binds no agent tool today; step-boundary commits happen anyway")
            if isinstance(s.raw.get("hooks"), list) and not s.raw["hooks"]:
                self.warn("hooks", s.where, "hooks: [] disables the default audit_logger and secret_scan hooks")
            elif isinstance(s.raw.get("hooks"), list):
                missing_defaults = [h for h in DEFAULT_HOOKS if h not in s.raw["hooks"]]
                if missing_defaults:
                    self.info("hooks", s.where, f"explicit hooks replace the defaults; {missing_defaults} will not run on this step")
            if s.strategy in ("fanout_batch", "wave_scheduler", "task_loop") and not s.task_source:
                self.warn("strategy", s.where, f"strategy '{s.strategy}' needs a task_source")
            if s.strategy in ("fanout_batch", "wave_scheduler") and not s.fanout:
                self.warn("strategy", s.where, f"strategy '{s.strategy}' should declare fanout {{mode, max_parallel, agent: self}}")
            if s.strategy == "parallel_group" and not (s.fanout or {}).get("workers"):
                self.warn("strategy", s.where, "parallel_group runs nothing without children; declare subagents: {mode: parallel}")
            if s.strategy == "wave_scheduler" and (s.task_source or {}).get("parser") == "heading_tasks":
                self.info("strategy", s.where, "heading_tasks carries no dependencies; json_tasks gives waves their order")
            src = (s.task_source or {}).get("source_step")
            if src and src not in ids:
                self.warn("task-source", s.where, f"task_source.source_step '{src}' is not a compiled step id")
            spec_step = (s.task_source or {}).get("spec_step")
            if spec_step and spec_step not in ids:
                self.warn("task-source", s.where, f"task_source.spec_step '{spec_step}' is not a compiled step id")
            for key in ("max_parallel",):
                value = (s.fanout or {}).get(key)
                limit = self.cat.runtime_default("max_concurrency", 5)
                if isinstance(value, int) and value > limit:
                    self.info("fanout", s.where, f"max_parallel {value} is clamped to {limit} at run time")
            workers = (s.fanout or {}).get("workers") or []
            if workers and s.strategy != "parallel_group":
                allowed_workers = set(m.get("allowed_workers") or [])
                for w in workers:
                    if w not in allowed_workers:
                        self.err("fanout", s.where, f"fanout worker '{w}' is not in allowed_workers; run_fanout rejects it")
                    if self.cat.agents and w not in self.cat.agents and not w.startswith(f"{CUSTOM}:"):
                        self.err("fanout", s.where, f"fanout worker '{w}' is not a known agent")
            if s.raw.get("on_conflict") == "merge_agent" and not (s.fanout or {}).get("merge_agent"):
                self.warn("fanout", s.where, "on_conflict: merge_agent needs fanout.merge_agent")
            for pat in SECRET_PATTERNS:
                if pat.search(prompt):
                    self.err("secret", s.where, "the prompt looks like it contains a credential; never put secrets in a manifest")
                    break

        # paste vs roster hand-offs: consumed output is pasted only into a step that cannot read files;
        # a step that can read files sees an earlier step's file only when it depends_on that step
        for s in steps:
            if s.agent != CUSTOM or s.mechanical:
                continue
            consumed = [c for c in s.consumes if c not in EXEMPT_CONSUMES]
            pasted = bool(consumed) and not s.tools.get("read_files")
            labels = [c for c in consumed if c != "route_decision"]
            if labels and s.tools.get("read_files"):
                sources = sorted({p for c in labels for p in producers.get(c, set()) if p != s.agent_id})
                if sources and not set(sources) & set(s.depends_on):
                    self.warn("paste-flow", s.where,
                              f"consumes {labels}, but read_files is true, so nothing is pasted, and no producer "
                              f"({', '.join(sources)}) is in depends_on, so its file is not in the roster either",
                              "paste hand-off: set tools.read_files: false; file hand-off: add depends_on: "
                              "[<producer>] and tell the prompt which file to read")
                elif sources:
                    self.info("paste-flow", s.where,
                              f"consumes {labels} is not pasted because read_files is true; the step reads the "
                              "producer's file from its roster",
                              "for a paste hand-off set tools.read_files: false")
            if PASTE_REFERENCE_RE.search(s.raw.get("prompt") or "") and not pasted:
                self.warn("paste-flow", s.where, "the prompt refers to output 'shown above', but nothing is pasted into this step",
                          "paste needs a producer with produces: [label], this step with consumes: [label] and "
                          "tools.read_files: false; otherwise tell the prompt which file to read")

        # only the first step receives the brief in its message (engine _compose_context_message); later
        # steps get pasted outputs, a task block (fan-out) or nothing, and can read .context/user-prompt.md
        first_id = steps[0].agent_id if steps else ""
        for s in steps:
            if s.agent != CUSTOM or s.mechanical or s.agent_id == first_id or d.get("revises_existing"):
                continue
            prompt = s.raw.get("prompt") or ""
            if "user-prompt.md" not in prompt and expects_brief(prompt):
                self.warn("brief", s.where, "the prompt expects the brief in this step's message, but only the first step receives it",
                          "pass what this step needs through an earlier step's output, or give it read_files: true "
                          "and tell it to read .context/user-prompt.md")
            pasted = any(producers.get(c, set()) - {s.agent_id} for c in s.consumes if c not in EXEMPT_CONSUMES)
            gets_task = s.strategy in ("fanout_batch", "wave_scheduler", "task_loop")
            if not s.tools.get("read_files") and not pasted and not gets_task and "before-human" not in s.gates:
                self.warn("input", s.where, "this step receives nothing: it is not the first step, nothing is pasted "
                                            "into it, and read_files is false",
                          "paste an earlier step's output (produces/consumes), or set read_files: true and tell the "
                          "prompt to read .context/user-prompt.md or an earlier step's file")

        # clarify answers are written to PLANNER.md only; no step's message carries them
        clarify = m.get("clarify") if isinstance(m.get("clarify"), dict) else {}
        # (only judged when the workflow has custom-agent steps: a catalog agent's own prompt decides what it reads)
        if m.get("planner") == "run" and clarify.get("mode", "auto") == "auto" \
                and any(s.agent == CUSTOM for s in steps):
            if not any(s.agent == CUSTOM and s.tools.get("read_files") and "PLANNER.md" in (s.raw.get("prompt") or "")
                       for s in steps):
                self.warn("clarify", "clarify", "the clarify answers are written to PLANNER.md only, and no step with "
                                                "read_files: true names PLANNER.md, so the answers reach no step",
                          "tell the first step (read_files: true) to read PLANNER.md; its Explicit Constraints list the answers")

        # deliverable sanity
        leaves = [s for s in steps if s.is_leaf and s.agent_id in reached]
        writers = [s for s in steps if s.tools.get("write_files")]
        if strategy == "streamed_text":
            for s in leaves:
                if s.tools.get("write_files"):
                    self.warn("deliverable", s.where, "streamed_text delivers the last step's REPLY, but this final step can write files",
                              "set write_files: false on the final step so it answers instead of writing")
        if strategy == "serialized_sandbox" and not writers:
            self.warn("deliverable", "deliverable", "serialized_sandbox bundles files, but no step can write any")
        if strategy == "single_file":
            if d.get("publish_from_glob") and not any(s.mechanical == "publish" for s in steps):
                self.warn("deliverable", "deliverable.publish_from_glob", "publish_from_glob is only used by a 'mechanical: publish' step")
            for s in leaves:
                if s.mechanical and s.mechanical != "publish":
                    self.info("deliverable", s.where, f"final step is mechanical '{s.mechanical}'; make sure it writes '{d.get('name')}'")
        if any(s.mechanical == "publish" for s in steps) and not d.get("publish_from_glob"):
            self.err("deliverable", "deliverable", "a 'mechanical: publish' step needs deliverable.publish_from_glob")
        for s in steps:
            # the built-in workflow itself (same id) is the one these kinds are written for
            if s.mechanical in ("assemble_backlog", "assemble_prototype", "extract_prototype_ui") \
                    and m.get("id") not in self.cat.workflows:
                self.warn("mechanical", s.where, f"'{s.mechanical}' only works with its built-in workflow's exact files and instance ids",
                          "outside those workflows use a custom-agent step instead")
        if d.get("revises_existing") and m.get("planner") == "run":
            self.err("deliverable", "planner", "a revision workflow (revises_existing) must use planner: skip")
        if m.get("chained_from"):
            if not d.get("chains_from"):
                self.warn("chain", "deliverable.chains_from", "this workflow accepts chains (chained_from) but deliverable.chains_from is false")
            if "chain_context" not in context:
                self.warn("chain", "context_providers", "add 'chain_context' so the source run's payload reaches .context/")

        # capabilities.internet
        caps = m.get("capabilities") if isinstance(m.get("capabilities"), dict) else {}
        if caps.get("internet") or any("internet" in (s.tools_requested.get("tool_sets") or []) for s in steps):
            self.warn("internet", "capabilities.internet", "internet tools are stubs in this platform build (no network egress)",
                      "do not design steps that depend on live web data")

        # uploads
        if any("file_extract" in (s.tools.get("tool_sets") or []) for s in steps):
            self.info("uploads", "steps", "a step has file_extract: documents are read from .uploads/ and inline attachments "
                                          "are stripped from the brief; launches must stage the uploads")

        # budget
        limits = m.get("limits") if isinstance(m.get("limits"), dict) else {}
        cap = limits.get("max_subagents", self.cat.runtime_default("max_subagents", 8))
        static = 0
        dynamic: list[str] = []
        for s in steps:
            if s.strategy == "parallel_group":
                static += len((s.fanout or {}).get("workers") or [])
            elif s.strategy in ("fanout_batch", "wave_scheduler"):
                count = (s.fanout or {}).get("count")
                if isinstance(count, int):
                    static += count
                else:
                    dynamic.append(s.agent_id)
        if isinstance(cap, int) and static > cap:
            self.err("budget", "limits.max_subagents", f"declared fan-out spawns {static} workers but max_subagents is {cap}",
                     "raise limits.max_subagents (trusted only) or reduce the parallel children")
        if dynamic:
            self.info("budget", "limits", f"{dynamic} spawn one worker per task; the task list must stay within "
                                          f"{cap - static} remaining workers (max_subagents {cap})")
        if (dynamic or static) and "wall_clock_seconds" not in limits:
            self.info("budget", "limits", f"fan-out wall clock defaults to {self.cat.runtime_default('wall_clock_seconds', 900)}s; "
                                          "set limits.wall_clock_seconds if the fan-out needs longer (trusted) or less")

    # ─────────────────────────────────────────── summary

    def summary_lines(self) -> list[str]:
        out = []
        d = self.m.get("deliverable") if isinstance(self.m.get("deliverable"), dict) else {}
        reached = self.reachable()
        out.append("Plan (compiled order; children run before their parent):")
        out.append(f"  {'#':>2}  {'step id':34} {'strategy':15} {'gates':24} {'model (effort)':40} {'tools':10} notes")
        for i, s in enumerate(self.steps, 1):
            model = ((s.raw.get("model") or {}).get("model") if isinstance(s.raw.get("model"), dict) else None) or "-"
            effort = (s.raw.get("model") or {}).get("effort") if isinstance(s.raw.get("model"), dict) else None
            if effort:
                model = f"{model} ({effort})"
            t = s.tools
            tools = "".join(c for c, k in (("r", "read_files"), ("w", "write_files"), ("x", "exec")) if t.get(k)) or "-"
            if t.get("tool_sets"):
                tools += "+" + ",".join(t["tool_sets"])
            notes = []
            if s.mechanical:
                notes.append(f"mechanical:{s.mechanical}")
            if s.dispatched_by:
                notes.append(f"parallel child of {s.dispatched_by}")
            elif s.parent:
                notes.append(f"{s.group_mode} child of {s.parent}")
            if s.route and s.route.get("outcomes"):
                arms = ", ".join(f"{k}->{v.get('target') or v.get('trigger')}{' (workflow)' if v.get('trigger') == 'workflow' else ''}"
                                 for k, v in s.route["outcomes"].items())
                notes.append(f"route[{arms}]")
            if s.is_leaf:
                notes.append("ends run")
            if s.agent_id not in reached:
                notes.append("UNREACHABLE")
            gates = ",".join(s.gates) or "-"
            out.append(f"  {i:>2}  {s.agent_id[:34]:34} {s.strategy[:15]:15} {gates[:24]:24} {str(model)[:40]:40} {tools[:10]:10} {'; '.join(notes)}")
        out.append(f"Deliverable: {d.get('strategy')} {d.get('name') or ''}".rstrip())
        writers = [s.agent_id for s in self.steps if s.is_leaf and s.agent_id in reached]
        if writers:
            out.append(f"Final step(s): {', '.join(writers)}")
        return out


# ─────────────────────────────────────────────────────────────── IO


def _no_duplicate_keys(pairs: list) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def load_manifest(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SystemExit("error: reading YAML needs PyYAML (pip install pyyaml), or pass the JSON file") from exc
        return yaml.safe_load(text)
    return json.loads(text, object_pairs_hook=_no_duplicate_keys)


def schema_findings(manifest: Any, schema_path: Path) -> tuple[list[Finding], str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return [], "skipped (pip install jsonschema to enable)"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [Finding("warning", "schema", str(schema_path), f"could not read schema: {exc}")], "unavailable"
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    findings = []
    for error in sorted(validator.iter_errors(manifest), key=lambda e: list(map(str, e.absolute_path))):
        loc = "$"
        for part in error.absolute_path:
            loc += f"[{part}]" if isinstance(part, int) else f".{part}"
        message = error.message
        if len(message) > 300:
            message = message[:297] + "..."
        findings.append(Finding("error", "schema", loc, message))
    return findings, f"{len(findings)} schema error(s)" if findings else "passed"


def compiler_findings(manifest: Any, backend: Path, trust: str) -> list[Finding]:
    backend = backend.resolve()
    cwd = os.getcwd()
    sys.path.insert(0, str(backend))
    try:
        os.chdir(backend)
        from agents.capabilities.registry import CapabilityRegistry  # type: ignore
        from agents.workflows.compiler import CompilerError, WorkflowCompiler  # type: ignore
        from agents.workflows.manifest import ManifestValidationError, build_manifest_from_dict  # type: ignore
    except Exception as exc:  # noqa: BLE001
        os.chdir(cwd)
        return [Finding("warning", "compiler", str(backend), f"real compiler unavailable: {exc}",
                        "run this script with the backend interpreter (uv run python ...)")]
    findings: list[Finding] = []
    try:
        parsed = build_manifest_from_dict(copy.deepcopy(manifest), "skill:validate_manifest")
        WorkflowCompiler().compile(parsed, CapabilityRegistry(), trust=trust)
    except (ManifestValidationError, CompilerError) as exc:
        findings.append(Finding("error", "compiler", "real compiler", str(exc)))
    except Exception as exc:  # noqa: BLE001
        findings.append(Finding("error", "compiler", "real compiler", f"{type(exc).__name__}: {exc}"))
    else:
        findings.append(Finding("info", "compiler", "real compiler", f"compiled at trust '{trust}'"))
    try:
        from agents.loader import load_agent_spec  # type: ignore

        def walk(steps: list) -> None:
            for step in steps or []:
                if not isinstance(step, dict):
                    continue
                agent = step.get("agent")
                if isinstance(agent, str) and agent != CUSTOM:
                    try:
                        load_agent_spec(agent)
                    except Exception as exc:  # noqa: BLE001
                        findings.append(Finding("error", "compiler", f"agent {agent}", f"AGENT.md load failed: {exc}"))
                sub = step.get("subagents")
                if isinstance(sub, dict):
                    walk(sub.get("steps") or [])

        walk(manifest.get("steps") if isinstance(manifest, dict) else [])
    except Exception:  # noqa: BLE001
        pass
    finally:
        os.chdir(cwd)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="workflow manifest (.json, or .yaml with PyYAML)")
    parser.add_argument("--trust", default="user", choices=("user", "db", "file", "builtin"),
                        help="trust the manifest will compile at (default: user, the strictest)")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--compiler", type=Path, metavar="BACKEND_DIR", help="also run the platform's real compiler")
    parser.add_argument("--summary", action="store_true", help="print the compiled plan")
    parser.add_argument("--json", action="store_true", help="print a machine-readable report")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--quiet-info", action="store_true", help="hide info-level notes")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {args.manifest}: {exc}", file=sys.stderr)
        return 2
    catalog_data: dict = {}
    if args.catalog.is_file():
        try:
            catalog_data = json.loads(args.catalog.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"warning: catalog unreadable ({exc}); name checks are skipped", file=sys.stderr)
    catalog = Catalog(catalog_data)

    checker = Checker(manifest, catalog, args.trust)
    checker.run()
    schema_found, schema_status = schema_findings(manifest, args.schema)
    findings = schema_found + checker.findings
    if not catalog.present:
        findings.append(Finding("warning", "catalog", str(args.catalog), "no catalog snapshot; agent, model and capability names were not checked"))
    if args.compiler:
        findings += compiler_findings(manifest, args.compiler, args.trust)
    if args.quiet_info:
        findings = [f for f in findings if f.level != "info"]
    findings.sort(key=lambda f: LEVEL_ORDER.get(f.level, 3))
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    ok = not errors and not (args.strict and warnings)

    if args.json:
        report = {
            "file": str(args.manifest),
            "trust": args.trust,
            "cap": checker.profile,
            "valid": ok,
            "schema": schema_status,
            "catalog": (catalog_data.get("source") or {}) | {"generated_at": catalog_data.get("generated_at")},
            "counts": {"errors": len(errors), "warnings": len(warnings),
                       "info": len([f for f in findings if f.level == "info"])},
            "steps": [
                {"id": s.agent_id, "strategy": s.strategy, "gates": s.gates, "is_leaf": s.is_leaf,
                 "dispatched_by": s.dispatched_by, "depends_on": s.depends_on,
                 "tools": {k: v for k, v in s.tools.items() if v}}
                for s in checker.steps
            ],
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(report, indent=2))
        return 0 if ok else 1

    wf_id = manifest.get("id") if isinstance(manifest, dict) else "?"
    print(f"Manifest: {wf_id} ({args.manifest})")
    print(f"Trust: {args.trust} -> {checker.profile} cap | schema: {schema_status} | "
          f"catalog: {catalog_data.get('generated_at') or 'missing'}")
    if args.summary and checker.steps:
        print()
        for line in checker.summary_lines():
            print(line)
    print()
    for f in findings:
        tag = {"error": "ERROR", "warning": "WARN ", "info": "info "}.get(f.level, f.level)
        print(f"{tag} [{f.code}] {f.where}: {f.message}")
        if f.hint:
            print(f"       hint: {f.hint}")
    if findings:
        print()
    verdict = "VALID" if ok else "INVALID"
    print(f"{verdict}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
