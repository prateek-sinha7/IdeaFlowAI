#!/usr/bin/env python3
"""Print only the part of the catalog or schema you need while designing a workflow.

references/catalog.json (about 200 KB), schema/workflow-manifest.schema.json (about 60 KB)
and docs/catalog.md (about 80 KB) are larger than one file read returns in most agent
hosts, so reading them arrives cut off. This script answers one question at a time in a
few lines of plain text.

Commands:
  overview [--trust T]    start here: models, icons, deliverables, gates, validators,
                          providers, tool grants and limits for trust T (default: user)
  models [--eu]           every model id with cost class, effort levels and default effort
  icons                   the icon names the catalog card renders
  kind KIND [--trust T]   every name of one capability kind: strategy, deliverable, gate,
                          validator, hook, context_provider, input_provider, task_parser,
                          tool, mechanical, compaction, post_step, mcp_server,
                          integration_provider
  agents [--all]          catalog agents that run on their own (--all: every agent)
  agent ID                one agent's contract: produces, consumes, tools, used in
  skills [WORDS...]       step skills whose id or description contains every word
  workflows               predefined workflow ids (route targets, chained_from sources)
  mcp                     MCP servers, their tools and the integration scopes
  trust T                 what trust T (user, db, file, builtin) allows and forbids
  field [PATH] [--full]   the schema's rules for one field: top, step, step.tools,
                          step.route.outcomes, deliverable.strategy, clarify, limits ...
  search WORDS...         every name, description and schema field containing all words
  example [ID] [STEP]     the shipped example workflows: no ID lists them; ID lists its
                          steps; ID STEP (instance_id or index) prints that step's JSON
                          and its prompt as plain text

Examples:
  python catalog_lookup.py overview --trust user
  python catalog_lookup.py example prototype_v2 fi-close
  python catalog_lookup.py field step.tools.tool_sets
  python catalog_lookup.py search word count

Run with `python` or `py -3`. On Windows, `python3` is a Microsoft Store alias that exits 9009.
Exit codes: 0 = answered (including "no match"), 2 = unknown command, name, kind or path.
Stdlib only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_catalog import MANIFEST_KINDS  # noqa: E402  (kinds a manifest can name, in doc order)
from validate_manifest import CATALOG_ICONS, DEFAULT_CATALOG, DEFAULT_SCHEMA  # noqa: E402

# Where each capability kind is written in a manifest.
KIND_FIELD = {
    "strategy": "step.strategy",
    "deliverable": "deliverable.strategy",
    "gate": "step.gates",
    "validator": "step.validators (with gates [\"validation\"] and fix)",
    "hook": "step.hooks (omit it: audit_logger + secret_scan apply by default)",
    "context_provider": "context_providers",
    "input_provider": "input_providers",
    "task_parser": "step.task_source.parser",
    "tool": "step.tools.tool_sets",
    "mechanical": "step.mechanical",
    "compaction": "step.compaction",
    "post_step": "step.post_step",
    "mcp_server": "step.tools.mcp as \"server.tool\"",
    "integration_provider": "step.tools.integrations as a scope (see: mcp)",
}
ROOT_ALIASES = ("top", "$", "manifest", "workflow")
MAX_SEARCH_PER_GROUP = 15
SKILL_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = SKILL_DIR / "examples"
LAUNCHER_NOTE = "Run with `python` or `py -3`. On Windows, `python3` is a Microsoft Store alias that exits 9009."
# What each shipped example shows (catalog_lookup.py example).
EXAMPLE_SHOWS = {
    "prototype": "Catalog agents (no prompts); optional first step with condition; task_loop with heading_tasks "
                 "and spec_step; html_static and html_render validators; html_skeleton compaction; opendesign and "
                 "chain_context providers; run_images; chained_from",
    "prototype_v2": "custom-agent pipeline of 3,000-17,000 character phase prompts; file_extract reading; "
                    "wave_scheduler with json_tasks and screen_plan; ask_user clarify step; mechanical "
                    "assemble_prototype; playwright validation; raised limits",
    "backlog": "Chains from prototype_v2; five ask_user clarify steps; mechanical assemble_backlog; "
               "backlog_plan_coverage validator with fix; wave_scheduler fan-outs; a reviewer step (us-review); "
               "text_name and chains_from deliverable",
    "ppt": "Short chain of catalog agents; ppt deliverable; opendesign; clarify auto with planner run; chained_from",
    "user_stories": "Chain of catalog agents; streamed_text deliverable with chains_from; chain_context; "
                    "clarify auto with planner run",
}
# Words that point at a limit no validator can check.
HONEST_LIMIT_WORDS = {"length", "word", "words", "count", "tone", "fact", "facts", "web", "live"}
TRIGGER_RE = re.compile(r"^(use (only |this skill )?when|use for)\b", re.IGNORECASE)


# ───────────────────────────────────────────────────────────────── helpers


def short(text: Any, limit: int = 150) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def first_sentence(text: Any, limit: int = 110) -> str:
    text = " ".join(str(text or "").split())
    end = text.find(". ")
    if 0 < end < limit:
        return text[: end + 1]
    return short(text, limit)


def joined(items: Any) -> str:
    return ", ".join(str(i) for i in items or []) or "-"


def matcher(words: list[str]):
    """True when every word starts a word in the text ('tone' matches 'tones', not 'milestones')."""
    patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(w.lower())) for w in words]

    def match(*parts: Any) -> bool:
        hay = " ".join(str(p or "") for p in parts).lower()
        return all(p.search(hay) for p in patterns)

    return match


def strip_triggers(text: Any) -> str:
    """A skill description without its trigger sentences ("Use when writing ..."), which name the
    situations a skill applies to, not what it is about."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
    return " ".join(s for s in sentences if not TRIGGER_RE.match(s))


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}")


def suggest(word: str, options: list[str]) -> str:
    close = difflib.get_close_matches(word, options, n=5, cutoff=0.5)
    return f" Did you mean: {', '.join(close)}?" if close else ""


class Trust:
    """Trust level -> cap, with the same allow rules the validator applies."""

    def __init__(self, cat: dict, level: str):
        trust = cat.get("trust") or {}
        self.levels: dict = trust.get("levels") or {"file": "trusted", "builtin": "trusted",
                                                     "db": "trusted", "user": "untrusted"}
        if level not in self.levels:
            raise KeyError(level)
        self.level = level
        self.profile = self.levels[level]
        self.cap: dict = (trust.get("caps") or {}).get(self.profile) or {}
        self.trusted = self.profile == "trusted"
        self.exec_trust = list(trust.get("exec_runtime_trust") or ["builtin", "file"])
        self.caps: dict = cat.get("capabilities") or {}

    def allows(self, kind: str, name: str) -> bool:
        if kind == "tool":  # tool sets: the trust cap decides, not the registry flag
            return name in (self.cap.get("tool_sets") or [])
        if self.trusted:
            return True
        row = (self.caps.get(kind) or {}).get(name) or {}
        if row.get("user_allowed"):
            return True
        return self.profile == "saved" and bool(row.get("saved_workflow_allowed"))

    def split(self, kind: str) -> tuple[list[str], list[str]]:
        names = sorted(self.caps.get(kind) or {})
        ok = [n for n in names if self.allows(kind, n)]
        return ok, [n for n in names if n not in ok]


def allowed_line(label: str, trust: Trust, kind: str) -> str:
    ok, no = trust.split(kind)
    text = f"{label}: {joined(ok)}"
    if no:
        text += f"   [not at '{trust.level}' trust: {joined(no)}]"
    return text


def trust_or_error(cat: dict, level: str) -> Trust | None:
    try:
        return Trust(cat, level)
    except KeyError:
        levels = (cat.get("trust") or {}).get("levels") or {}
        print(f"Unknown trust '{level}'. Use one of: {joined(levels)}.")
        return None


# ───────────────────────────────────────────────────────────────── schema access


def deref(schema: dict, node: Any) -> Any:
    """Follow local $ref pointers; sibling keys of the $ref win over the target."""
    for _ in range(10):
        if not isinstance(node, dict) or not str(node.get("$ref", "")).startswith("#/"):
            return node
        target: Any = schema
        for part in node["$ref"][2:].split("/"):
            target = target[part]
        merged = dict(target)
        merged.update({k: v for k, v in node.items() if k != "$ref"})
        node = merged
    return node


def bases(node: dict) -> list:
    """allOf parts that pull in a base definition ($ref), not the inline if/then rules."""
    return [part for part in node.get("allOf") or [] if isinstance(part, dict) and "$ref" in part]


def properties(schema: dict, node: Any) -> dict:
    """Properties of an object node, merged from its $ref bases (base first)."""
    node = deref(schema, node)
    if not isinstance(node, dict):
        return {}
    props: dict = {}
    for part in bases(node):
        for key, value in properties(schema, part).items():
            props[key] = value
    for key, value in (node.get("properties") or {}).items():
        if isinstance(value, dict) and isinstance(props.get(key), dict):
            merged = dict(props[key])
            merged.update(value)
            props[key] = merged
        else:
            props[key] = value
    return props


def required(schema: dict, node: Any) -> set[str]:
    node = deref(schema, node)
    if not isinstance(node, dict):
        return set()
    out = set(node.get("required") or [])
    for part in bases(node):
        out |= required(schema, part)
    return out


def children(schema: dict, node: Any) -> dict:
    """Named sub-fields of a node: an object's properties, or the properties of an array's items."""
    node = deref(schema, node)
    if not isinstance(node, dict):
        return {}
    props = properties(schema, node)
    if not props and isinstance(node.get("items"), dict):
        props = properties(schema, node["items"])
    return props


def cross_rules(schema: dict, node: Any, depth: int = 0) -> list[str]:
    """$comment of every allOf rule (if/then and friends) on a node and its bases."""
    if depth > 4 or not isinstance(node, dict):
        return []
    rules: list[str] = []
    for part in node.get("allOf") or []:
        if isinstance(part, dict) and "$ref" in part:
            rules += cross_rules(schema, deref(schema, part), depth + 1)
        elif isinstance(part, dict) and part.get("$comment"):
            rules.append(part["$comment"])
    return rules


def type_summary(schema: dict, node: Any) -> str:
    node = deref(schema, node)
    if node is False:
        return "not allowed here"
    if not isinstance(node, dict):
        return "any"
    if "const" in node:
        return f"always {json.dumps(node['const'])}"
    if "enum" in node:
        values = ["null" if v is None else str(v) for v in node["enum"]]
        text = "|".join(values)
        return f"one of {text}" if len(text) <= 20 else f"one of {len(values)} values"
    kind = node.get("type")
    if kind == "array" or (isinstance(kind, list) and "array" in kind):
        items = node.get("items")
        return "list of " + (type_summary(schema, items) if isinstance(items, dict) else "values")
    if isinstance(kind, list):
        return "|".join(kind)
    if kind:
        return str(kind)
    if "oneOf" in node:
        return " or ".join(type_summary(schema, part) for part in node["oneOf"])
    if properties(schema, node):
        return "object"
    return "any"


def enum_values(schema: dict, node: Any) -> list | None:
    node = deref(schema, node)
    if not isinstance(node, dict):
        return None
    if "enum" in node:
        return node["enum"]
    items = deref(schema, node.get("items"))
    if isinstance(items, dict) and "enum" in items:
        return items["enum"]
    return None


def resolve_field(schema: dict, path: str) -> tuple[Any, str, str | None, list[str]]:
    """Return (node, label, failed_part, options_at_failure)."""
    parts = [p for p in (path or "top").split(".") if p]
    head = parts[0] if parts else "top"
    if head in ROOT_ALIASES:
        node: Any = schema
        label, rest = "top", parts[1:]
    elif head in ("step", "steps"):
        node = schema["$defs"]["step"]
        label, rest = "step", parts[1:]
    else:
        node, label, rest = schema, "", parts
    for part in rest:
        props = children(schema, node)
        current = deref(schema, node)
        if part in props:
            node = props[part]
        elif isinstance(current, dict) and isinstance(current.get("additionalProperties"), dict):
            node = current["additionalProperties"]  # e.g. route.outcomes.<decision value>
        else:
            return None, label, part, sorted(props)
        label = f"{label}.{part}" if label else part
    return node, label or "top", None, []


def walk_fields(schema: dict) -> Iterator[tuple[str, dict]]:
    """Every (path, field) under the top level and under step, three levels deep."""

    def walk(node: Any, prefix: str, depth: int) -> Iterator[tuple[str, dict]]:
        for name, sub in children(schema, node).items():
            sub = deref(schema, sub)
            if not isinstance(sub, dict):
                continue
            path = f"{prefix}.{name}"
            yield path, sub
            if depth < 3 and name not in ("steps", "subagents"):
                yield from walk(sub, path, depth + 1)
                extra = sub.get("additionalProperties")
                if isinstance(extra, dict):
                    yield from walk(extra, f"{path}.*", depth + 1)

    for name, sub in properties(schema, schema).items():
        if name == "steps":
            continue
        sub = deref(schema, sub)
        if isinstance(sub, dict):
            yield name, sub
            yield from walk(sub, name, 1)
    yield from walk(schema["$defs"]["step"], "step", 1)
    sub = deref(schema, properties(schema, schema["$defs"]["step"]).get("subagents"))
    if isinstance(sub, dict):
        yield from walk(sub, "step.subagents", 2)


# ───────────────────────────────────────────────────────────────── commands


def cmd_overview(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    trust = trust_or_error(cat, args.trust)
    if trust is None:
        return 2
    src = cat.get("source") or {}
    print(f"Catalog snapshot {cat.get('generated_at')} ({src.get('branch') or src.get('url') or '?'} "
          f"@ {src.get('commit') or '?'}). Trust '{trust.level}' -> cap '{trust.profile}'.")
    print()
    print("MODELS in the picker (id, cost class, effort levels, default effort). All: models")
    for m in cat.get("models") or []:
        if not m.get("selectable"):
            continue
        r = m.get("reasoning") or {}
        print(f"  {m.get('id', ''):46} {str(m.get('cost_class')):9} {','.join(r.get('levels') or []):33} "
              f"default {r.get('default_effort')}")
    print("  Set effort only together with model.model. global.* ids route requests outside the EU.")
    print()
    print("ICONS: " + ", ".join(CATALOG_ICONS))
    print(allowed_line("DELIVERABLE strategies (deliverable.strategy)", trust, "deliverable"))
    print(allowed_line("GATES (step.gates)", trust, "gate"))
    print(allowed_line("STRATEGIES (step.strategy; single_shot is the default)", trust, "strategy"))
    print(allowed_line("CONTEXT PROVIDERS (context_providers)", trust, "context_provider"))
    print(allowed_line("INPUT PROVIDERS (input_providers)", trust, "input_provider"))
    print("VALIDATORS (step.validators; need gates [\"validation\"] and fix {\"max_attempts\": 2}):")
    for name, row in sorted(((cat.get("capabilities") or {}).get("validator") or {}).items()):
        mark = "" if trust.allows("validator", name) else "  [not at this trust]"
        print(f"  {name:24} {short(row.get('description'), 120)}{mark}")
    print("  None of them checks length, word count, tone or facts: enforce those in prompts, with an AI")
    print("  critic loop, or with a human gate.")
    print()
    grants = []
    for flag in (cat.get("trust") or {}).get("grant_bool_fields") or ["read_files", "write_files", "exec", "git",
                                                                       "network", "spawn_subagents"]:
        grants.append(f"{flag} {'yes' if trust.cap.get(flag) else 'no'}")
    print(f"TOOLS at '{trust.level}' trust: {', '.join(grants)}; secrets "
          f"{'blocked by the security gate at run time' if trust.trusted else 'no'}.")
    print(f"  Tool sets kept: {joined(trust.cap.get('tool_sets'))}. Any other set is silently dropped.")
    if trust.cap.get("exec") and trust.level not in trust.exec_trust:
        print(f"  exec compiles here, but the runtime security gate runs it only at {' or '.join(trust.exec_trust)} trust.")
    limits = cat.get("limits") or {}
    defaults = limits.get("runtime_defaults") or {}
    print("LIMITS: defaults " + ", ".join(f"{k} {v}" for k, v in defaults.items())
          + (". User trust may only lower them." if not trust.trusted else
             f". Largest any built-in uses: {', '.join(f'{k} {v}' for k, v in (limits.get('saved_ceiling') or {}).items())}."))
    print()
    print_asking(trust)
    print()
    print("Next: example | example <id> <step> | field step | field <path> | kind <kind> | search <words> | trust <level>")
    return 0


def print_asking(trust: Trust) -> None:
    """How a workflow can ask the user for facts at this trust (quick-reference §2a)."""
    print(f"ASKING THE USER at '{trust.level}' trust (quick-reference §2a):")
    if trust.level in ("user", "db"):
        print("  - Composer launches (Run once, or a saved workflow) always select an output type, which forces")
        print("    clarify to 'skip': no clarify question is asked. To ask before the work, start with an intake")
        print("    step with gates [\"human\"], redoable: true and reply: \"last_message\", and set planner and")
        print("    clarify to skip. The user answers with Request changes at the review card (docs/patterns.md §21).")
    print("  - clarify (planner run, clarify auto) asks only on launches that send no output type (an API run")
    print("    payload or a wizard). The questions come from the planner's missing information; clarify.defaults")
    print("    are used only when it reports none. Unanswered questions get the recommended answer. The answers")
    print("    go to PLANNER.md only, never into a step's message.")
    has_ask = "ask_user" in (trust.cap.get("tool_sets") or [])
    print(f"  - ask_user tool set (a step asks mid-run, as in the backlog example): "
          f"{'yes' if has_ask else 'no, silently dropped'} at '{trust.level}' trust.")


def cmd_models(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    rows = cat.get("models") or []
    if args.eu:
        rows = [m for m in rows if str(m.get("id", "")).startswith("eu.")]
    print("id | label | cost class | effort levels | default effort | in picker")
    for m in rows:
        r = m.get("reasoning") or {}
        print(f"  {m.get('id', ''):46} {short(m.get('label'), 20):20} {str(m.get('cost_class')):9} "
              f"{','.join(r.get('levels') or []):33} {str(r.get('default_effort')):6} "
              f"{'yes' if m.get('selectable') else 'raw id only'}")
    print("Cost classes: cheap < standard < premium; basic-tier accounts cannot launch premium models.")
    print("Budget-mode Claude models accept effort none or on; adaptive Claude models also accept 'on'.")
    print("Set effort only together with model.model: the validator checks it against that model's levels.")
    return 0


def cmd_icons(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    print(", ".join(CATALOG_ICONS))
    print("Any other Lucide name renders the default icon on the catalog card.")
    return 0


def cmd_kind(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    caps = cat.get("capabilities") or {}
    kind = args.kind
    if kind not in caps:
        print(f"Unknown kind '{kind}'. Kinds a manifest can name: {joined(MANIFEST_KINDS)}.{suggest(kind, list(caps))}")
        return 2
    trust = trust_or_error(cat, args.trust)
    if trust is None:
        return 2
    rows = caps[kind]
    if kind in KIND_FIELD:
        print(f"{kind} ({len(rows)} names), written as {KIND_FIELD[kind]}")
    else:
        print(f"{kind} ({len(rows)} names): the engine picks these itself; a manifest cannot name them.")
        if kind == "skill":
            print("  These are skill SOURCES, not step skills. For step skills run: skills <words>")
    print(f"  {'name':26} {trust.level + '?':6} what it does")
    for name in sorted(rows):
        row = rows[name]
        text = short(f"{row.get('description') or ''} {row.get('process') or ''}", 170)
        io = ""
        if row.get("reads") or row.get("writes"):
            io = f" | reads {short(joined(row.get('reads')), 60)} | writes {short(joined(row.get('writes')), 60)}"
        print(f"  {name:26} {'yes' if trust.allows(kind, name) else 'NO':6} {text}{io}")
    if kind == "tool":
        print(f"  For tool sets the '{trust.level}' trust cap decides (not the registry flag); "
              "a set it does not keep is silently dropped.")
    return 0


def cmd_agents(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    agents = cat.get("agents") or {}
    print("custom-agent: the blank template. Use it for almost every step (instance_id + name + prompt).")
    if args.all:
        groups: dict[str, list[str]] = {}
        for agent_id, row in agents.items():
            pt = row.get("pipeline_type")
            groups.setdefault(", ".join(pt) if isinstance(pt, list) else str(pt or "?"), []).append(agent_id)
        for pipeline in sorted(groups, key=lambda k: (k != "custom", k)):
            print(f"pipeline_type {pipeline}:")
            for agent_id in sorted(groups[pipeline]):
                row = agents[agent_id]
                print(f"  {agent_id:34} {short(row.get('description') or row.get('role'), 110)}")
    else:
        print("Catalog agents that run on their own (pipeline_type custom, no upstream inputs):")
        for agent_id in sorted(agents):
            row = agents[agent_id]
            if row.get("pipeline_type") == "custom" and not row.get("template") and not row.get("consumes"):
                print(f"  {agent_id:26} {short(row.get('description') or row.get('role'), 110)}")
        print("Every other agent belongs to a predefined workflow and expects its upstream files (agents --all).")
    print("A catalog agent takes no prompt and may appear once per workflow. Details: agent <id>")
    return 0


def cmd_agent(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    agents = cat.get("agents") or {}
    row = agents.get(args.id)
    if row is None:
        print(f"Unknown agent '{args.id}'.{suggest(args.id, list(agents))} List them with: agents --all")
        return 2
    print(f"{args.id}: {row.get('name') or ''} - {row.get('role') or ''}")
    print(f"  {short(row.get('description'), 300)}")
    for key in ("pipeline_type", "produces", "consumes", "tools", "model", "gate", "injects", "used_in"):
        value = row.get(key)
        print(f"  {key:14} {joined(value) if isinstance(value, list) else (value if value is not None else '-')}")
    if row.get("template"):
        print("  Template agent: give each use an instance_id and a prompt.")
    elif row.get("pipeline_type") != "custom":
        print("  Built for the workflows above; use it only together with the agents it consumes, "
              "or chain into / trigger that workflow instead.")
    else:
        print("  Takes no prompt (its AGENT.md is fixed). Use it at most once per workflow.")
    return 0


def cmd_skills(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    skills = cat.get("skills") or {}
    words = [w.lower() for w in args.words]
    if not words:
        counts: dict[str, int] = {}
        for row in skills.values():
            counts[str(row.get("category") or "uncategorized")] = counts.get(str(row.get("category") or "uncategorized"), 0) + 1
        print(f"{len(skills)} step skills by category: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        print("Add words to search, e.g.: skills tone | skills html page | skills market")
        return 0
    match = matcher(words)
    by_id = [(sid, row) for sid, row in sorted(skills.items()) if match(sid.replace("-", " "), sid)]
    id_hits = {sid for sid, _row in by_id}
    by_text = [(sid, row) for sid, row in sorted(skills.items())
               if sid not in id_hits and match(sid.replace("-", " "), sid, strip_triggers(row.get("description")))]
    hits = by_id + by_text
    if not hits:
        print(f"No step skill matches {' '.join(words)!r}.")
        print("Most steps need no step skill: put the domain rules in the custom-agent prompt "
              "(quick-reference §8). Run `skills` with no words to see the categories.")
        return 0
    for sid, row in hits[:40]:
        print(f"  {sid:34} {short(row.get('description'), 120)}")
    if len(hits) > 40:
        print(f"  ... {len(hits) - 40} more; add words to narrow it down")
    print("A step skill goes in step.skills; the step needs tools.read_files: true to open /skills/<id>/SKILL.md.")
    return 0


def cmd_workflows(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    print("id | launchable | beta | steps | deliverable | chained from")
    for wf_id, row in sorted((cat.get("workflows") or {}).items()):
        d = row.get("deliverable") or {}
        print(f"  {wf_id:30} {'yes' if row.get('user_launchable') else 'no ':4} {'beta' if row.get('is_beta') else '-':5} "
              f"{str(row.get('step_count')):3} {d.get('strategy')} {d.get('name') or ''} | {joined(row.get('chained_from'))}")
    print("Do not reuse one of these ids for a new workflow. They are valid route targets with trigger: workflow "
          "and valid chained_from sources.")
    return 0


def cmd_mcp(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    print("MCP servers (step.tools.mcp: [\"server.tool\"]):")
    for name, row in sorted((cat.get("mcp_servers") or {}).items()):
        flags = ("user trust ok" if row.get("user_allowed") else "trusted only") + (", powerful" if row.get("powerful") else "")
        print(f"  {name:11} {flags:24} tools: {joined(row.get('tools'))}")
    print("Integration scopes (step.tools.integrations), each turns on one server's tools:")
    for scope, row in sorted((cat.get("integration_scopes") or {}).items()):
        row = row if isinstance(row, dict) else {"server": row}
        print(f"  {scope:12} -> server {row.get('server')}")
    print("Powerful servers need gate 'security' plus a 'secrets' grant; the security gate then blocks the step "
          "in this platform build. Put any outbound post (slack.post_message) behind a human or before-human gate.")
    return 0


def cmd_trust(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    trust = trust_or_error(cat, args.level)
    if trust is None:
        return 2
    print(f"Trust '{trust.level}' compiles with the '{trust.profile}' cap.")
    grants = [f"{k} {'yes' if trust.cap.get(k) else 'no'}" for k in ("read_files", "write_files", "exec", "git",
                                                                          "network", "spawn_subagents")]
    print(f"  Grants: {', '.join(grants)}.")
    print(f"  Tool sets kept: {joined(trust.cap.get('tool_sets'))}; any other set is silently dropped.")
    blocked = []
    for kind in MANIFEST_KINDS:
        if kind == "tool":
            continue
        _ok, no = trust.split(kind)
        if no:
            blocked.append(f"{kind}: {joined(no)}")
    if blocked:
        print("  Not allowed:")
        for line in blocked:
            print(f"    {line}")
    else:
        print("  Every registered capability name is allowed at compile time.")
    limits = cat.get("limits") or {}
    if not trust.trusted:
        print("  Limits may only be lowered: " + ", ".join(f"{k} {v}" for k, v in (limits.get('default_ceiling') or {}).items())
              + ". exec, network, secrets and spawn_subagents grants are compile errors.")
    else:
        print("  Limits may be raised; the largest any built-in uses: "
              + ", ".join(f"{k} {v}" for k, v in (limits.get('saved_ceiling') or {}).items()) + ".")
        if trust.level not in trust.exec_trust:
            print(f"  Runtime: the security gate runs exec only at {' or '.join(trust.exec_trust)} trust, so an exec "
                  f"step compiles at '{trust.level}' and then fails when it runs.")
        print("  Runtime: any step that grants network or secrets and declares the security gate is blocked.")
    where = {"user": "Composer Run once and override rows", "db": "saved Composer workflows launched by callers "
             "entitled to the custom pipeline (enterprise tier); anyone else compiles them at user",
             "file": "engineer-shipped workflow.yaml files", "builtin": "the platform's own workflows"}
    if trust.level in where:
        print(f"  Used for: {where[trust.level]}.")
    return 0


def cmd_field(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    node, label, failed, options = resolve_field(schema, args.path)
    if node is None:
        print(f"No field '{failed}' under '{label}'. Fields there: {joined(options)}.{suggest(failed or '', options)}")
        return 2
    node = deref(schema, node)
    if node is False:
        print(f"{label}: not allowed at this level.")
        return 0
    print(f"{label}  ({type_summary(schema, node)})")
    if node.get("description"):
        print(f"  {node['description']}")
    props = children(schema, node)
    comment = node.get("$comment")
    if comment:
        print(f"  Rules: {comment if (args.full or not props) else short(comment, 500)}")
        if props and not args.full and len(comment) > 500:
            print(f"  (full rules: field {label} --full)")
    values = enum_values(schema, node)
    if values:
        print("  Allowed values: " + ", ".join("null" if v is None else str(v) for v in values))
    if "default" in node:
        print(f"  Default: {json.dumps(node['default'])}")
    if node.get("examples"):
        print(f"  Examples: {short(json.dumps(node['examples']), 220)}")
    if props:
        need = required(schema, node) or required(schema, node.get("items") if isinstance(node.get("items"), dict) else {})
        print(f"  Fields (details: field {label}.<name>):")
        for name, sub in props.items():
            sub = deref(schema, sub)
            if sub is False:
                continue
            mark = "*" if name in need else " "
            text = first_sentence(sub.get("description"), 100) if isinstance(sub, dict) else ""
            print(f"    {name:24}{mark} {type_summary(schema, sub)[:36]:36} {text}")
        if need:
            print("    * = required")
    extra = node.get("additionalProperties")
    if isinstance(extra, dict):
        print(f"  Each value: {type_summary(schema, extra)} (details: field {label}.<key>)")
    rules = cross_rules(schema, node)
    if rules:
        print("  Cross-field rules:")
        for rule in rules:
            print(f"    - {rule}")
    return 0


def cmd_search(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    words = [w.lower() for w in args.words]
    hit = matcher(words)
    trust = Trust(cat, "user")
    groups: dict[str, list[str]] = {}

    def add(group: str, line: str) -> None:
        groups.setdefault(group, []).append(line)

    for kind, rows in sorted((cat.get("capabilities") or {}).items()):
        for name, row in sorted(rows.items()):
            if hit(kind, name, row.get("description"), row.get("process")):
                where = KIND_FIELD.get(kind, "not nameable in a manifest").split(" (")[0]
                add("capabilities", f"{kind}:{name} [{where}; user trust {'yes' if trust.allows(kind, name) else 'no'}] "
                                    f"{short(row.get('description'), 100)}")
    for agent_id, row in sorted((cat.get("agents") or {}).items()):
        if hit(agent_id, row.get("name"), row.get("role"), row.get("description")):
            add("agents", f"{agent_id} ({joined(row.get('pipeline_type')) if isinstance(row.get('pipeline_type'), list) else row.get('pipeline_type')}) "
                          f"{short(row.get('description') or row.get('role'), 100)}")
    for sid, row in sorted((cat.get("skills") or {}).items()):
        if hit(sid, row.get("description")):
            add("step skills", f"{sid} {short(row.get('description'), 100)}")
    for wf_id, row in sorted((cat.get("workflows") or {}).items()):
        if hit(wf_id, row.get("name"), row.get("display_name"), row.get("description")):
            add("workflows", f"{wf_id} {short(row.get('display_name') or row.get('description'), 100)}")
    for m in cat.get("models") or []:
        if hit(m.get("id"), m.get("label"), m.get("description")):
            add("models", f"{m.get('id')} ({m.get('cost_class')}) {short(m.get('label'), 60)}")
    for server, row in sorted((cat.get("mcp_servers") or {}).items()):
        for tool in row.get("tools") or []:
            if hit(server, tool, f"{server}.{tool}"):
                add("mcp tools", f"{server}.{tool}")
    for path, field in walk_fields(schema):
        if hit(path, field.get("description")):
            add("schema fields", f"{path} - {first_sentence(field.get('description'), 100)}")
    honest = "No validator checks length, word count, tone or facts; put the limit in the prompts of the steps " \
             "that write and edit (quick-reference §7)."
    if not groups:
        print(f"No match for {' '.join(words)!r} in capabilities, agents, step skills, workflows, models, "
              "MCP tools or schema fields.")
        print("No platform capability has this name: build it with custom-agent steps and prompts "
              "(quick-reference §8, docs/prompt-writing.md).")
        if HONEST_LIMIT_WORDS & set(words):
            print(honest)
        return 0
    labels = {"schema fields": "schema fields whose text mentions the words"}
    for group in ("capabilities", "schema fields", "agents", "step skills", "workflows", "models", "mcp tools"):
        lines = groups.get(group)
        if not lines:
            continue
        print(f"{labels.get(group, group)} ({len(lines)}):")
        for line in lines[:MAX_SEARCH_PER_GROUP]:
            print(f"  {line}")
        if len(lines) > MAX_SEARCH_PER_GROUP:
            print(f"  ... {len(lines) - MAX_SEARCH_PER_GROUP} more; add words to narrow it down")
    if HONEST_LIMIT_WORDS & set(words):
        print(honest)
    return 0


def load_examples() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(EXAMPLES_DIR.glob("*.workflow.json")):
        out[path.name.replace(".workflow.json", "")] = load_json(path)
    return out


def step_label(step: dict) -> str:
    return str(step.get("instance_id") or step.get("agent") or "?")


def cmd_example(cat: dict, schema: dict, args: argparse.Namespace) -> int:
    examples = load_examples()
    if not args.id:
        print("Example | Steps | Shows   (the platform's shipped workflows, validated at file trust)")
        for wf_id, manifest in examples.items():
            print(f"  {wf_id:13} {len(manifest.get('steps') or []):3}  {EXAMPLE_SHOWS.get(wf_id, '-')}")
        print("Missing from the examples: a critic loop, a forward branch, a human gate and integrations; "
              "see patterns.md.")
        print("Copy their prompt style and structure, not their trust-only features (ask_user, raised limits, ppt).")
        print("Next: example <id> lists its steps; example <id> <instance_id|index> prints one step.")
        return 0
    manifest = examples.get(args.id)
    if manifest is None:
        print(f"Unknown example '{args.id}'. Examples: {joined(examples)}.{suggest(args.id, list(examples))}")
        return 2
    steps = manifest.get("steps") or []
    if args.step is None:
        print(f"{args.id}: {len(steps)} steps. planner {manifest.get('planner')}, clarify "
              f"{(manifest.get('clarify') or {}).get('mode')}, deliverable "
              f"{(manifest.get('deliverable') or {}).get('strategy')} {(manifest.get('deliverable') or {}).get('name') or ''}")
        print(f"  {'#':>2} {'instance_id or agent':22} {'strategy':15} {'mechanical':19} {'gates':14} "
              f"{'read/write':10} {'tool_sets':14} prompt chars")
        for i, step in enumerate(steps):
            tools = step.get("tools") or {}
            rw = "-" if step.get("mechanical") or not tools else \
                f"{'r' if tools.get('read_files', True) else '-'}{'w' if tools.get('write_files') else '-'}"
            print(f"  {i:>2} {step_label(step):22} {str(step.get('strategy') or '-'):15} "
                  f"{str(step.get('mechanical') or '-'):19} {joined(step.get('gates')):14} {rw:10} "
                  f"{joined(tools.get('tool_sets')):14} {len(step.get('prompt') or '')}")
        print(f"Next: example {args.id} <instance_id|index> prints one step and its prompt.")
        return 0
    labels = [step_label(s) for s in steps]
    if args.step.isdigit() and int(args.step) < len(steps):
        step = steps[int(args.step)]
    elif args.step in labels:
        step = steps[labels.index(args.step)]
    else:
        print(f"Unknown step '{args.step}' in {args.id}. Steps: {joined(labels)}.{suggest(args.step, labels)}")
        return 2
    body = {k: v for k, v in step.items() if k != "prompt"}
    print(json.dumps(body, indent=1, ensure_ascii=False))
    prompt = step.get("prompt")
    if prompt:
        print(f"--- prompt ({len(prompt)} characters) ---")
        print(prompt)
    else:
        print("--- no prompt: a catalog agent (its AGENT.md is fixed) or a mechanical step ---")
    return 0


# ───────────────────────────────────────────────────────────────── main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, epilog=LAUNCHER_NOTE,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    p = sub.add_parser("overview", help="start here: the names most workflows need")
    p.add_argument("--trust", default="user")
    p = sub.add_parser("models", help="every model id")
    p.add_argument("--eu", action="store_true", help="only eu.* ids")
    sub.add_parser("icons", help="icon names the catalog card renders")
    p = sub.add_parser("kind", help="every name of one capability kind")
    p.add_argument("kind")
    p.add_argument("--trust", default="user")
    p = sub.add_parser("agents", help="catalog agents")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("agent", help="one agent's contract")
    p.add_argument("id")
    p = sub.add_parser("skills", help="search step skills")
    p.add_argument("words", nargs="*")
    sub.add_parser("workflows", help="predefined workflow ids")
    sub.add_parser("mcp", help="MCP servers, tools and integration scopes")
    p = sub.add_parser("trust", help="what a trust level allows and forbids")
    p.add_argument("level")
    p = sub.add_parser("field", help="schema rules for one field")
    p.add_argument("path", nargs="?", default="top")
    p.add_argument("--full", action="store_true", help="print long rule text in full")
    p = sub.add_parser("search", help="search every name, description and schema field")
    p.add_argument("words", nargs="+")
    p = sub.add_parser("example", help="the shipped example workflows, one step at a time")
    p.add_argument("id", nargs="?")
    p.add_argument("step", nargs="?")
    return parser


COMMANDS = {
    "overview": cmd_overview, "models": cmd_models, "icons": cmd_icons, "kind": cmd_kind,
    "agents": cmd_agents, "agent": cmd_agent, "skills": cmd_skills, "workflows": cmd_workflows,
    "mcp": cmd_mcp, "trust": cmd_trust, "field": cmd_field, "search": cmd_search, "example": cmd_example,
}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    cat = load_json(args.catalog)
    schema = load_json(args.schema)
    return COMMANDS[args.command](cat, schema, args)


if __name__ == "__main__":
    sys.exit(main())
