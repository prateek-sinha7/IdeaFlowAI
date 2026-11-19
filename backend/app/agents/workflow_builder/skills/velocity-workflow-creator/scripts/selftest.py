#!/usr/bin/env python3
"""Self-test for validate_manifest.py.

Checks that every bundled example validates at its target trust, and that a set of
known-bad manifests produces the expected findings. With `--compiler BACKEND_DIR`
it also asks the platform's real compiler for its verdict on each case, so drift
between this skill and the platform shows up as a failure.

Usage:
  python selftest.py                     # skill checks only (stdlib)
  uv run python selftest.py --compiler . # from a Velocity backend folder: parity too
Exit code 0 when every check passes.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_manifest as vm  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
# The examples are the platform's shipped workflows (backend/agents/workflows/<id>/workflow.yaml,
# converted to JSON), so they all validate at file trust.
EXAMPLE_TRUST = {
    "prototype": "file",
    "prototype_v2": "file",
    "backlog": "file",
    "ppt": "file",
    "user_stories": "file",
}
# Warning codes the validator rightly raises on a shipped workflow. A warning not listed here
# for that example fails the self-test, so a new finding on an example is never ignored.
EXAMPLE_ALLOWED_WARNINGS = {
    # catalog agents with no custom step: nothing for the validator to judge on clarify answers
    "prototype": set(),
    # fi-planner's prompt says the request is "in your message", but the first step is a conditional one
    "prototype_v2": {"brief"},
    # 21 root steps (the Composer canvas holds 16); consumes labels that are file paths, not paste labels;
    # us-planner's prompt says the request is "in your message" and it is not the first step
    "backlog": {"composer", "paste-flow", "brief"},
    # accepts chains (chained_from) but declares neither chains_from nor the chain_context provider
    "ppt": {"chain"},
    "user_stories": set(),
}


def base(steps: list, **top) -> dict:
    manifest = {
        "id": "selftest",
        "planner": "skip",
        "clarify": {"mode": "skip", "defaults": []},
        "deliverable": {"strategy": "single_file", "name": "out.md"},
        "steps": steps,
    }
    manifest.update(top)
    return manifest


def ca(iid: str, **fields) -> dict:
    step = {"agent": "custom-agent", "instance_id": iid, "name": iid.title(), "prompt": f"Do the {iid} work.", "gates": []}
    step.update(fields)
    return step


def decision(iid: str, outcomes: dict, **fields) -> dict:
    keys = " or ".join('{"decision": "%s"}' % k for k in outcomes)
    return ca(iid, produces=["route_decision"], gates=["conditional"], route={"outcomes": outcomes},
              prompt=f"Reply with exactly one line: {keys}.", **fields)


GOTO = lambda target: {"trigger": "step", "target": target}  # noqa: E731


def standard_prompt(role: str, receives: str) -> str:
    """A prompt with every section of the standard (quick-reference section 8), over 2,000 characters."""
    rules = "\n".join(f"- Rule {i} for the {role}: keep each item specific, sourced and in the agreed order." for i in range(1, 7))
    return (
        f"You are the {role}. You turn your input into the facts or text the next step needs, and nothing else.\n"
        "2 phases, in order. Each has Rules and Steps.\n  Phase 1 - Gather   collect what you need\n"
        "  Phase 2 - Report   write the output below\n"
        f"WHAT YOU RECEIVE\n- {receives}\n- You have no file tools. Ignore any line telling you to read files.\n"
        "WHAT YOU NEVER DO\n- Never do the next step's job. Never invent a fact you did not receive.\n"
        "IF INPUT IS MISSING\n- If a required fact is missing, reply with the one line NEEDS_INPUT: <the missing facts>.\n"
        f"Phase 1 - Gather\nRules\n{rules}\nSteps\n1. Read every input.\n2. List each fact with its source.\n"
        f"Phase 2 - Report\nRules\n{rules}\nSteps\n1. Write the output in the structure below.\n2. Check it.\n"
        "OUTPUT\nSTATUS: READY or STATUS: NEEDS_INPUT, then a Facts table with columns Fact, Value, Source.\n"
        "CHECK BEFORE YOU REPLY\n- Is every value copied from the input, never invented?\n- Is every required fact present?\n"
        "HOW TO DELIVER\nReply with the output above only, nothing before or after it."
    )


INTAKE_STEPS = [
    ca("intake", name="Intake", produces=["facts"], gates=["human"], redoable=True, reply="last_message",
       model={"model": "eu.anthropic.claude-haiku-5-5", "effort": "medium"},
       tools={"read_files": False, "write_files": False},
       prompt=standard_prompt("Intake", 'The request under "=== ORIGINAL USER REQUEST ===", and on a re-run '
                                        '"=== USER GUIDANCE ===" with the user\'s answers.')),
    ca("write", name="Writer", depends_on=["custom-agent:intake"], consumes=["facts"], produces=["draft"],
       tools={"read_files": False, "write_files": False},
       prompt=standard_prompt("Writer", 'The facts under "--- Output from Intake (A user-defined workflow agent) ---".')),
    ca("edit", name="Editor", depends_on=["custom-agent:write"], consumes=["facts", "draft"],
       tools={"read_files": False, "write_files": False},
       prompt=standard_prompt("Editor", 'The facts under "--- Output from Intake (A user-defined workflow agent) ---" '
                                        'and the draft under "--- Output from Writer (A user-defined workflow agent) ---".')),
]

# the shape of the manifest behind run 6d4ebb3b: facts only from clarify, short prompts, a paste writer
JD_SHAPE = base([
    ca("role-facts", name="Role Analyst", produces=["role-facts"], tools={"read_files": True, "write_files": False},
       prompt="You are the Role Analyst. Read PLANNER.md and copy the clarify answers for role, seniority, location "
              "and must-have skills. Use the answers only. Write 'Not provided' for a missing answer."),
    ca("write-jd", name="JD Writer", depends_on=["custom-agent:role-facts"], consumes=["role-facts"],
       tools={"read_files": False, "write_files": False},
       prompt="You are the JD Writer. The role facts are shown above. Write the job description. Use a bracketed "
              "placeholder for every fact marked Not provided."),
], planner="run", clarify={"mode": "auto", "rounds": 1, "defaults": ["role", "seniority", "location", "skills"]},
   deliverable={"strategy": "single_file", "name": "job-description.md", "mimetype": "text/markdown"})

PLANNER_READER = ca("a", tools={"read_files": True, "write_files": False},
                    prompt="Read PLANNER.md and list the Explicit Constraints.")

# (name, manifest, trust, expected findings [(level, code)], real-compiler verdict)
CASES = [
    ("unknown top-level key", base([ca("a")], notes="x"), "user", [("error", "unknown-key")], "reject"),
    ("unknown step key", base([ca("a", when="x")]), "user", [("error", "unknown-key")], "reject"),
    ("bad instance_id", base([ca("Bad_Id")]), "user", [("error", "instance-id")], "reject"),
    ("duplicate instance_id across nesting",
     base([ca("a", subagents={"mode": "sequential", "steps": [ca("a")]})]), "user", [("error", "instance-id")], "reject"),
    ("prompt on a catalog agent", base([{"agent": "swot-analyst", "prompt": "x", "gates": []}]), "user",
     [("error", "prompt")], "reject"),
    ("three subagent levels",
     base([ca("a", subagents={"mode": "sequential", "steps": [ca("b", subagents={"mode": "sequential", "steps": [
         ca("c", subagents={"mode": "sequential", "steps": [ca("d")]})]})]})]), "user", [("error", "subagents")], "reject"),
    ("fanout group with two children",
     base([ca("plan"), ca("agg", subagents={"mode": "fanout", "task_source": {"kind": "parsed", "parser": "json_tasks",
          "source_step": "custom-agent:plan"}, "steps": [ca("w1"), ca("w2")]})]), "user", [("error", "subagents")], "reject"),
    ("unknown strategy", base([ca("a", strategy="magic")]), "user", [("error", "capability")], "reject"),
    ("approval gate at user trust", base([ca("a", gates=["approval"])]), "user", [("error", "trust")], "reject"),
    ("two human-family gates", base([ca("a"), ca("b", gates=["human", "before-human"], depends_on=["custom-agent:a"])]),
     "user", [("error", "hitl")], "reject"),
    ("conditional without route", base([ca("a", gates=["conditional"])]), "user", [("error", "route")], "reject"),
    ("route without conditional", base([ca("a", produces=["route_decision"], route={"outcomes": {"x": GOTO("b")}}), ca("b")]),
     "user", [("error", "route")], "reject"),
    ("exec without gates", base([ca("a", tools={"exec": True})]), "file", [("error", "exec-gates")], "reject"),
    ("exec at user trust", base([ca("a", tools={"exec": True}, gates=["security", "approval"])]), "user",
     [("error", "trust")], "reject"),
    ("unexposed MCP tool", base([ca("a", tools={"mcp": ["github.delete_repo"]})]), "user", [("error", "mcp")], "reject"),
    ("powerful MCP without security", base([ca("a", tools={"mcp": ["postgres.query"]})]), "file", [("error", "mcp")], "reject"),
    ("route to a missing step", base([decision("a", {"x": GOTO("ghost")})]), "user", [("error", "route")], "reject"),
    # the shape behind run 725474ee: the only outcome loops back, so the "pass" decision matches nothing and the run fails.
    # The compiler now rejects it too (WorkflowCompiler._validate_route_has_exit), so the real verdict is "reject".
    ("loop-only route with no exit",
     base([ca("draft"), decision("review", {"revise": GOTO("draft")}, depends_on=["custom-agent:draft"])]),
     "user", [("error", "route-no-exit")], "reject"),
    ("end outcome with a target",
     base([ca("draft"), decision("review", {"revise": GOTO("draft"), "pass": {"trigger": "end", "target": "draft"}},
                                 depends_on=["custom-agent:draft"])]),
     "user", [("error", "route")], "reject"),
    ("decision source without route_decision",
     base([ca("a", gates=["conditional"], route={"outcomes": {"x": GOTO("b")}}), ca("b", depends_on=["custom-agent:a"])]),
     "user", [("error", "route")], "reject"),
    ("trigger_max_depth other than 5",
     base([ca("a", produces=["route_decision"], gates=["conditional"],
              route={"outcomes": {"x": {"trigger": "workflow", "target": "self", "feedback": "f"}}, "trigger_max_depth": 3})]),
     "user", [("error", "route")], "reject"),
    ("depends_on cycle", base([ca("a", depends_on=["custom-agent:b"]), ca("b", depends_on=["custom-agent:a"])]), "user",
     [("error", "cycle")], "reject"),
    ("fan-out source after the fan-out",
     base([ca("w", strategy="fanout_batch", fanout={"mode": "parallel", "agent": "self"},
              task_source={"kind": "parsed", "parser": "json_tasks", "source_step": "custom-agent:plan"}), ca("plan")]),
     "user", [("error", "fanout-source")], "reject"),
    ("raised limits at user trust", base([ca("a")], limits={"max_subagents": 20}), "user", [("error", "trust")], "reject"),
    ("deliverable name with a path", base([ca("a")], deliverable={"strategy": "single_file", "name": "out/x.md"}), "user",
     [("error", "deliverable")], "reject"),
    ("chains_from without a name", base([ca("a")], deliverable={"strategy": "single_file", "chains_from": True}), "user",
     [("error", "deliverable")], "reject"),
    ("effort the model does not accept",
     base([ca("a", model={"model": "eu.anthropic.claude-opus-4-6-v1", "effort": "xhigh"})]), "user", [("error", "effort")],
     "reject"),
    ("mechanical step with tools", base([ca("a"), ca("pub", mechanical="publish", tools={"read_files": True})],
                                         deliverable={"strategy": "single_file", "name": "x.html", "publish_from_glob": "d.v*.html"}),
     "user", [("error", "mechanical")], "reject"),
    ("catalog agent used twice", base([{"agent": "swot-analyst", "gates": []}, {"agent": "swot-analyst", "gates": []}]), "user",
     [("error", "duplicate-id")], "reject"),
    # compile fine, fail or misbehave at run time: the skill must still flag them
    ("unreachable step", base([decision("a", {"x": GOTO("c")}), ca("b", depends_on=["custom-agent:a"]),
                               ca("c", depends_on=["custom-agent:a"])]), "user", [("error", "unreachable")], "accept"),
    ("bare depends_on id", base([ca("a"), ca("b", depends_on=["a"])]), "user", [("warning", "depends-on")], "accept"),
    ("unknown model id", base([ca("a", model={"model": "eu.anthropic.claude-sonnet-9"})]), "user", [("error", "model")], "accept"),
    # compiles, but launch fails building the roster (the parity check loads AGENT.md like launch does)
    ("unknown agent", base([{"agent": "made-up-agent", "gates": []}]), "user", [("error", "agent")], "reject"),
    ("exec at db trust", base([ca("a", tools={"exec": True}, gates=["security", "approval"])]), "db",
     [("error", "runtime-block")], "accept"),
    ("validators without validation gate", base([ca("a", validators=["design_quality"])]), "user",
     [("warning", "validators")], "accept"),
    ("streamed_text final step that writes", base([ca("a", tools={"read_files": True, "write_files": True})],
                                                   deliverable={"strategy": "streamed_text", "name": "a.md"}),
     "user", [("warning", "deliverable")], "accept"),
    ("tool set dropped at user trust", base([ca("a", tools={"tool_sets": ["ask_user"]})]), "user",
     [("warning", "tool-sets")], "accept"),
    ("static fan-out over budget",
     base([ca("p", subagents={"mode": "parallel", "steps": [ca(f"c{i}") for i in range(9)]})]), "user",
     [("error", "budget")], "accept"),
    ("secret in a prompt", base([ca("a", prompt="Use api_key = sk-ABCDEFGHIJKLMNOPQRSTUVWX to call it.")]), "user",
     [("error", "secret")], "accept"),
    # hand-off mistakes a smaller model makes when it copies a paste chain
    ("consumes on a step that reads files, producer not in depends_on",
     base([ca("a", produces=["notes"], tools={"read_files": False, "write_files": False}),
           ca("b", consumes=["notes"], tools={"read_files": True, "write_files": False})]), "user",
     [("warning", "paste-flow")], "accept"),
    ("prompt expects pasted output that never arrives",
     base([ca("a", tools={"read_files": False, "write_files": False}),
           ca("b", depends_on=["custom-agent:a"], tools={"read_files": True, "write_files": False},
              prompt="The outline is shown above. Write the full draft.")]), "user",
     [("warning", "paste-flow")], "accept"),
    ("custom step without a tools block", base([ca("a")]), "user", [("info", "tools")], "accept"),
    # what reaches a step at run time: only the first step gets the brief; clarify needs the planner
    ("clarify auto with planner skip", base([ca("a")], clarify={"mode": "auto", "defaults": ["scope"]}), "user",
     [("warning", "clarify")], "accept"),
    ("clarify answers no step reads", base([ca("a")], planner="run", clarify={"mode": "auto", "defaults": ["scope"]}),
     "user", [("warning", "clarify")], "accept"),
    ("later step that receives nothing",
     base([ca("a", tools={"read_files": False, "write_files": False}),
           ca("b", depends_on=["custom-agent:a"], tools={"read_files": False, "write_files": False})]), "user",
     [("warning", "input")], "accept"),
    ("later step that expects the brief in its message",
     base([ca("a", produces=["notes"], tools={"read_files": False, "write_files": False}),
           ca("b", depends_on=["custom-agent:a"], consumes=["notes"], tools={"read_files": False, "write_files": False},
              prompt="The notes are shown above. Match the tone in the original brief.")]), "user",
     [("warning", "brief")], "accept"),
    # run 6d4ebb3b: a Composer launch forces clarify to skip, and thin prompts wrote a placeholder document
    ("clarify auto launched from the Composer",
     base([PLANNER_READER], planner="run", clarify={"mode": "auto", "defaults": ["scope"]}), "user",
     [("warning", "clarify-launch")], "accept"),
    ("clarify auto launched from the Composer at db trust",
     base([PLANNER_READER], planner="run", clarify={"mode": "auto", "defaults": ["scope"]}), "db",
     [("warning", "clarify-launch")], "accept"),
    ("thin custom-agent prompt", base([ca("a", tools={"read_files": False, "write_files": False})]), "user",
     [("warning", "prompt-depth")], "accept"),
    ("the job_description_writer shape", JD_SHAPE, "user",
     [("warning", "clarify-launch"), ("warning", "prompt-depth")], "accept"),
]

# (name, manifest, trust, forbidden finding codes, real-compiler verdict). "*warning" forbids every warning.
CLEAN_CASES = [
    ("clarify auto at file trust",
     base([PLANNER_READER], planner="run", clarify={"mode": "auto", "defaults": ["scope"]}), "file",
     {"clarify-launch"}, "accept"),
    ("short decision prompt",
     base([decision("kind", {"long": GOTO("long"), "short": GOTO("short")},
                    tools={"read_files": False, "write_files": False}),
           ca("long", depends_on=["custom-agent:kind"], tools={"read_files": True, "write_files": False},
              prompt=standard_prompt("Long Writer", "The request at .context/user-prompt.md.")),
           ca("short", depends_on=["custom-agent:kind"], tools={"read_files": True, "write_files": False},
              prompt=standard_prompt("Short Writer", "The request at .context/user-prompt.md."))]), "user",
     {"prompt-depth"}, "accept"),
    ("intake step with a human gate",
     base(INTAKE_STEPS, deliverable={"strategy": "single_file", "name": "out.md", "mimetype": "text/markdown"}),
     "user", {"*warning"}, "accept"),
    ("later step that says the request is not in its message",
     base([ca("a", produces=["notes"], tools={"read_files": False, "write_files": False}),
           ca("b", depends_on=["custom-agent:a"], consumes=["notes"], tools={"read_files": False, "write_files": False},
              prompt=standard_prompt("Writer", "The notes are pasted in your message. The original request is "
                                               "not in your message; the notes carry what you need."))]), "user",
     {"brief"}, "accept"),
]


def run_checker(manifest: dict, trust: str, catalog: vm.Catalog) -> list[vm.Finding]:
    checker = vm.Checker(copy.deepcopy(manifest), catalog, trust)
    checker.run()
    return checker.findings


# ───────────────────────────────────────────────── catalog / schema sync checks


def _enum(schema: dict, *path: str) -> list:
    node = schema
    for part in path:
        node = node[part]
    return node["enum"]


def sync_checks(catalog_path: Path) -> list[tuple[str, list[str]]]:
    """Each item is (name, problems). Uses temp copies; nothing in the skill folder changes."""
    import tempfile
    import types

    import refresh_catalog as rc
    import schema_sync as ss

    results: list[tuple[str, list[str]]] = []
    real = json.loads(catalog_path.read_text(encoding="utf-8"))
    schema_real = json.loads(vm.DEFAULT_SCHEMA.read_text(encoding="utf-8"))

    # 1. the shipped files agree with each other
    problems = []
    if rc.render_markdown(real) != rc._read_norm(rc.DEFAULT_MD):
        problems.append("docs/catalog.md differs from catalog.json: run refresh_catalog.py --render")
    new, changes, _warn = ss.sync_schema(schema_real, real)
    if new != schema_real:
        problems.append("schema is out of date: " + "; ".join(changes))
    if ss.dump_schema(schema_real) != rc._read_norm(vm.DEFAULT_SCHEMA):
        problems.append("schema file is not in the canonical format: run refresh_catalog.py --render")
    results.append(("catalog.md and schema match catalog.json", problems))

    # 2. a new tool set, validator, MCP tool and scope reach the schema; removals too; comments follow
    edited = copy.deepcopy(real)
    edited["capabilities"]["tool"]["my_tool"] = {"user_allowed": False, "saved_workflow_allowed": False, "bound": True,
                                                  "description": "Test tool.", "process": "", "reads": [], "writes": [],
                                                  "config_schema": {}}
    edited["trust"]["caps"]["trusted"]["tool_sets"].append("my_tool")
    edited["capabilities"]["validator"]["my_check"] = {"user_allowed": True, "saved_workflow_allowed": True, "bound": True,
                                                       "description": "Test validator.", "process": "", "reads": [],
                                                       "writes": [], "config_schema": {}}
    edited["mcp_servers"]["jira"]["tools"] = sorted(edited["mcp_servers"]["jira"]["tools"] + ["add_comment"])
    edited["integration_scopes"]["jira_write"] = {"provider": "jira", "server": "jira", "powerful": False, "user_allowed": True}
    del edited["capabilities"]["hook"]["behavioral"]
    new, changes, warnings = ss.sync_schema(schema_real, edited)
    problems = []
    if "my_tool" not in new["$defs"]["toolPermissions"]["properties"]["tool_sets"]["items"]["enum"]:
        problems.append("new tool set missing from tool_sets enum")
    if "my_check" not in new["$defs"]["stepBase"]["properties"]["validators"]["items"]["enum"]:
        problems.append("new validator missing from validators enum")
    if "jira.add_comment" not in new["$defs"]["toolPermissions"]["properties"]["mcp"]["items"]["enum"]:
        problems.append("new MCP tool missing from mcp enum")
    if "jira_write" not in new["$defs"]["toolPermissions"]["properties"]["integrations"]["items"]["enum"]:
        problems.append("new integration scope missing from integrations enum")
    if "behavioral" in new["$defs"]["stepBase"]["properties"]["hooks"]["items"]["enum"]:
        problems.append("removed hook still in hooks enum")
    comment = new["$defs"]["toolPermissions"]["properties"]["tool_sets"]["$comment"]
    if "(11 sets)" not in comment:
        problems.append(f"tool_sets comment count not updated: {comment[:90]}")
    if new["$defs"]["stepBase"]["properties"]["validators"]["$comment"].count("(15 names)") != 1:
        problems.append("validators comment count not updated")
    first = ss.dump_schema(new)
    again, again_changes, _w = ss.sync_schema(json.loads(first), edited)
    if again_changes or ss.dump_schema(again) != first:
        problems.append("sync is not idempotent")
    results.append(("schema sync adds and removes names and updates counts", problems))

    # 3. an empty list never wipes an enum
    step = ("$defs", "stepBase", "properties")
    emptied = copy.deepcopy(real)
    emptied["capabilities"]["gate"] = {}
    new, _changes, warnings = ss.sync_schema(schema_real, emptied)
    problems = []
    if _enum(new, *step, "gates", "items") != _enum(schema_real, *step, "gates", "items"):
        problems.append("gates enum changed although the catalog had no gates")
    if not any("gates" in w for w in warnings):
        problems.append("no warning for the empty gate list")
    results.append(("schema sync skips an empty list with a warning", problems))

    # 4. the schema accepts a manifest that uses the new tool only after the sync
    problems = []
    try:
        import jsonschema  # type: ignore
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        manifest = {"id": "t", "planner": "skip", "clarify": {"mode": "skip"},
                    "deliverable": {"strategy": "single_file", "name": "a.md"},
                    "steps": [{"agent": "custom-agent", "instance_id": "a", "prompt": "x", "gates": [],
                               "tools": {"tool_sets": ["my_tool"]}}]}
        before = list(jsonschema.Draft202012Validator(schema_real).iter_errors(manifest))
        synced = ss.sync_schema(schema_real, edited)[0]
        after = list(jsonschema.Draft202012Validator(synced).iter_errors(manifest))
        if not before:
            problems.append("schema accepted an unknown tool set before the sync")
        if after:
            problems.append("schema still rejects the new tool set after the sync: " + after[0].message)
    results.append(("schema accepts a new tool set only after the sync" + ("" if jsonschema else " (skipped: no jsonschema)"), problems))

    # 5. integration scopes are read from the provider table, not from MCP server scopes
    names = ["agents", "agents.capabilities", "agents.capabilities.integration_providers",
             "agents.capabilities.integration_providers.providers"]
    saved = {name: sys.modules.get(name) for name in names}
    try:
        for name in names[:-1]:
            sys.modules[name] = types.ModuleType(name)
        fake = types.ModuleType(names[-1])

        class Provider:  # noqa: D401 - minimal stand-in
            def __init__(self, name):
                self.name = name

        fake.PROVIDERS = {"wiki_read": Provider("wiki"), "orphan_read": Provider("ghost")}
        fake.SCOPE_TO_SERVER = {"wiki_read": "wiki", "orphan_read": "ghost"}
        sys.modules[names[-1]] = fake
        cat = {"warnings": [], "integration_scopes": {},
               "capabilities": {"integration_provider": {"wiki": {"user_allowed": True}}},
               "mcp_servers": {"wiki": {"tools": ["get_page"], "powerful": False, "scope": "wiki_view"}}}
        rc._scopes_from_source(cat)
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    problems = []
    if set(cat["integration_scopes"]) != {"wiki_read", "orphan_read"}:
        problems.append(f"scopes read: {sorted(cat['integration_scopes'])} (expected both provider scopes)")
    if not any("whose own scope is 'wiki_view'" in w for w in cat["warnings"]):
        problems.append("no warning for a scope that differs from its server's scope")
    if not any("'ghost'" in w and "not in the MCP catalog" in w for w in cat["warnings"]):
        problems.append("no warning for a scope bridging an unknown server")
    results.append(("integration scopes come from the provider table", problems))

    # 6. --render rebuilds catalog.md and the schema after a hand edit; --check notices drift
    problems = []
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        (tmp / "catalog.json").write_text(json.dumps(edited, indent=2), encoding="utf-8")
        (tmp / "schema.json").write_text(vm.DEFAULT_SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
        args = ["--out-json", str(tmp / "catalog.json"), "--out-md", str(tmp / "catalog.md"), "--schema", str(tmp / "schema.json")]
        import contextlib
        import io

        def run(*extra: str) -> tuple[int, str]:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                code = rc.main(list(extra) + args)
            return code, buffer.getvalue()

        code, out = run("--check")
        if code != 1:
            problems.append("--check passed although catalog.md is missing and the schema is stale")
        code, out = run("--render")
        if code != 0:
            problems.append(f"--render failed: {out[-200:]}")
        md = (tmp / "catalog.md").read_text(encoding="utf-8") if (tmp / "catalog.md").exists() else ""
        if "`my_tool`" not in md or "`my_check`" not in md:
            problems.append("--render did not put the hand-added names into catalog.md")
        if "my_tool" not in (tmp / "schema.json").read_text(encoding="utf-8"):
            problems.append("--render did not put the hand-added tool into the schema")
        code, out = run("--check")
        if code != 0:
            problems.append(f"--check fails right after --render: {out[-200:]}")
        (tmp / "catalog.md").write_text(md + "\nstray edit\n", encoding="utf-8")
        code, out = run("--check")
        if code != 1:
            problems.append("--check missed a stray edit to catalog.md")
        broken = copy.deepcopy(edited)
        del broken["models"]
        (tmp / "catalog.json").write_text(json.dumps(broken), encoding="utf-8")
        code, out = run("--render")
        if code != 1 or "missing key 'models'" not in out:
            problems.append("--render accepted a catalog.json without models")
    results.append(("--render and --check handle a hand-edited catalog", problems))

    # 7. the change summary names a new tool
    lines = rc.diff_catalogs(real, edited)
    problems = []
    if not any(line.startswith("+ tool:") and "my_tool" in line for line in lines):
        problems.append("diff did not list the new tool set")
    if not any("mcp tools" in line and "jira.add_comment" in line for line in lines):
        problems.append("diff did not list the new MCP tool")
    if not any(line.startswith("- hook:") and "behavioral" in line for line in lines):
        problems.append("diff did not list the removed hook")
    results.append(("change summary lists new and removed names", problems))
    return results


# ───────────────────────────────────────────────── docs and lookup checks


def docs_checks(catalog_path: Path) -> list[tuple[str, list[str]]]:
    """Names the docs teach must exist: smaller models copy model ids and icons verbatim from them."""
    import contextlib
    import io
    import re

    import catalog_lookup as cl

    results: list[tuple[str, list[str]]] = []
    real = json.loads(catalog_path.read_text(encoding="utf-8"))
    docs = [SKILL_DIR / "SKILL.md"] + [p for p in sorted((SKILL_DIR / "docs").glob("*.md")) if p.name != "catalog.md"]

    # 1. every model id written in SKILL.md or a hand-written doc is in the catalog
    model_ids = {m.get("id") for m in real.get("models") or []}
    model_re = re.compile(r"`((?:eu|us|apac|global)\.[A-Za-z0-9.:\-]+)`")
    problems = [f"{p.name}: `{mid}` is not a catalog model id"
                for p in docs for mid in model_re.findall(p.read_text(encoding="utf-8")) if mid not in model_ids]
    results.append(("model ids in SKILL.md and docs exist in the catalog", problems))

    # 2. icons named in the docs and used by the examples render on the catalog card
    icon_re = re.compile(r"`([A-Z][a-z]+(?:[A-Z][a-z]+)*)`")
    problems = []
    for p in docs:
        for line in p.read_text(encoding="utf-8").splitlines():
            if "icon" in line.lower():
                problems += [f"{p.name}: icon `{name}` does not render" for name in icon_re.findall(line)
                             if name not in vm.CATALOG_ICONS]
    for path in sorted((SKILL_DIR / "examples").glob("*.workflow.json")):
        icon = json.loads(path.read_text(encoding="utf-8")).get("icon")
        if icon and icon not in vm.CATALOG_ICONS:
            problems.append(f"{path.name}: icon {icon!r} does not render")
    results.append(("icons in the docs and examples render", problems))

    # 3. the lookup script answers its main questions from the shipped files
    def run(*args: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                code = cl.main(["--catalog", str(catalog_path), *args])
            except SystemExit as exc:  # argparse rejects an unknown command or argument
                code = exc.code if isinstance(exc.code, int) else 2
        return code, buffer.getvalue()

    problems = []
    for args, must in ((("overview", "--trust", "user"), "ICONS"), (("field", "step"), "instance_id"),
                       (("field", "step.tools.tool_sets"), "Allowed values"), (("field", "step.route.outcomes.pass"), "trigger"),
                       (("kind", "validator"), "html_static"), (("trust", "db"), "trusted"), (("models", "--eu"), "eu."),
                       (("agent", "swot-analyst"), "produces"), (("mcp",), "slack"), (("workflows",), "prototype"),
                       (("skills", "html"), "html-page"), (("icons",), "FileText"), (("search", "route"), "route")):
        code, out = run(*args)
        if code != 0 or must not in out:
            problems.append(f"'{' '.join(args)}' exited {code} or lacks {must!r}")
    code, out = run("kind", "tool", "--trust", "user")
    rows = {line.split()[0]: line.split()[1] for line in out.splitlines() if line.startswith("  ") and len(line.split()) > 1}
    if rows.get("playwright") != "yes" or rows.get("workspace") != "NO":
        problems.append("kind tool --trust user must follow the trust cap (playwright yes, workspace NO)")
    code, out = run("field", "step.tool")
    if code != 2 or "tools" not in out:
        problems.append("an unknown field path must exit 2 and suggest the right name")
    code, out = run("search", "tone")
    if "roadmap-planner" in out:
        problems.append("search must match word starts ('tone' must not match 'milestones')")
    # the answers run 6d4ebb3b showed were wrong or empty
    code, out = run("skills", "writing")
    if code != 0 or "postmortem-writing" not in out or "cpp-coding-standards" in out:
        problems.append("'skills writing' must list postmortem-writing and skip skills that only say 'Use when writing'")
    # Search matches any word and ranks rows; these nonsense words must match nothing.
    for args, must in ((("skills", "quartzlattice", "zyxw"), "no step skill"),
                       (("search", "quartzlattice", "zyxw"), "custom-agent steps and prompts"),
                       (("search", "prototype", "document"), "prototype_v2"),
                       (("search", "word", "count"), "No validator"), (("field", "clarify.mode"), "Composer"),
                       (("overview", "--trust", "user"), "ASKING THE USER"), (("example",), "prototype_v2"),
                       (("example", "prototype_v2"), "fi-close"), (("example", "prototype_v2", "fi-close"), "Phase 1")):
        code, out = run(*args)
        if code != 0 or must.lower() not in out.lower():
            problems.append(f"'{' '.join(args)}' exited {code} or lacks {must!r}")
    code, out = run("example", "nope")
    if code != 2:
        problems.append(f"'example nope' must exit 2, exited {code}")
    results.append(("catalog_lookup.py answers from catalog.json and the schema", problems))

    # 4. SKILL.md and quick-reference.md each fit one file read (the host cuts reads at 30,000 characters)
    problems = [f"{p.name} has {len(p.read_text(encoding='utf-8'))} characters (limit {ONE_READ_LIMIT})"
                for p in (SKILL_DIR / "SKILL.md", SKILL_DIR / "docs" / "quick-reference.md")
                if len(p.read_text(encoding="utf-8")) > ONE_READ_LIMIT]
    results.append(("SKILL.md and quick-reference.md fit one read", problems))

    # 5. every catalog_lookup.py command SKILL.md and the docs tell the agent to run works
    problems = []
    commands = lookup_commands(docs)
    for path, command in commands:
        code, out = run(*command.split())
        if code != 0:
            problems.append(f"{path.name}: 'catalog_lookup.py {command}' exited {code}: {out.strip()[-160:]}")
    if len(commands) < 20:
        problems.append(f"found only {len(commands)} catalog_lookup.py commands in the docs; the extractor is broken")
    results.append((f"every catalog_lookup.py command in SKILL.md and the docs runs ({len(commands)} commands)", problems))

    # 6. python3 is a Microsoft Store alias on Windows (exit 9009): the docs launch Python as python or py -3
    problems = [f"{p.name}:{n}: {line.strip()[:100]}" for p in docs
                for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if re.search(r"\bpython3\b", line) and "9009" not in line]
    results.append(("docs launch Python as python or py -3", problems))

    # 7. step 3 defers to the intake: the old round-limit and skip-the-wait text is gone and
    #    step 4 loads the question bank the intake used
    skill_text = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    problems = [f"SKILL.md still says {phrase!r}" for phrase in REMOVED_SKILL_PHRASES
                if phrase.lower() in skill_text.lower()]
    step4 = skill_text.split("### 4.", 1)[-1].split("### 5.", 1)[0]
    if "docs/requirements-analysis.md` §3-5" not in step4:
        problems.append("SKILL.md step 4 does not load docs/requirements-analysis.md §3-5")
    results.append(("SKILL.md step 3 defers to the intake and step 4 loads the question bank", problems))
    return results


def _intake_slots(**overrides: dict) -> dict:
    """Every intake slot filled from the request, with ``overrides`` by slot name."""
    import intake_readiness as ir

    slots = {name: {"value": f"{name} value", "source": "request", "criticality": "blocking"}
             for name in ir.BLOCKING_SLOTS}
    slots.update({name: {"value": None, "source": "unknown", "criticality": "important"}
                  for name in ir.IMPORTANT_SLOTS})
    slots.update(overrides)
    return slots


def intake_checks() -> list[tuple[str, list[str]]]:
    """The intake readiness rule (scripts/intake_readiness.py) and its schema and docs."""
    import re

    import intake_readiness as ir

    results: list[tuple[str, list[str]]] = []
    assumed = {"value": "uploads", "source": "assumed", "criticality": "blocking"}
    na_no_reason = {"value": None, "source": "not_applicable", "criticality": "blocking"}
    na_goal = {"value": None, "source": "not_applicable", "criticality": "blocking", "reason": "x"}
    cases = (
        ("every blocking slot filled -> ready", _intake_slots(), {}, True, "filled"),
        ("an assumed blocking slot -> not ready", _intake_slots(input_source=assumed), {}, False, "gaps"),
        ("explicit defaults -> ready", _intake_slots(input_source=assumed), {"explicit_defaults": True},
         True, "explicit_defaults"),
        ("round limit reached -> ready", _intake_slots(input_source=assumed),
         {"rounds_asked": 2, "max_rounds": 2}, True, "max_rounds"),
        ("not_applicable without a reason -> not ready", _intake_slots(external_systems=na_no_reason), {},
         False, "gaps"),
        ("not_applicable on a slot that forbids it -> not ready", _intake_slots(goal=na_goal), {}, False, "gaps"),
    )
    for name, slots, kwargs, ready, reason in cases:
        got = ir.evaluate(slots, **kwargs)
        problems = [] if (got["ready"], got["reason"]) == (ready, reason) else [
            f"expected {(ready, reason)}, got {(got['ready'], got['reason'])}"]
        results.append((f"intake readiness: {name}", problems))

    problems = []
    slots = _intake_slots(volume_scale={"value": "8 files", "source": "assumed", "criticality": "important"})
    if ir.evaluate(slots)["assumptions"] != ["Assumption: volume_scale = 8 files - correct me if wrong"]:
        problems.append("an assumed important slot is not echoed in the fixed wording")
    question = {"slot": "input_source", "options": [{"label": "Upload", "recommended": True},
                                                    {"label": "Paste"}, {"label": ir.FALLBACK_LABEL, "fallback": True}]}
    if ir.parse_answer_codes("1b", [question]) != {0: 1} or ir.parse_answer_codes("2 apples", [question]):
        problems.append("answer codes are read wrongly")
    if not ir.is_explicit_defaults("defaults") or ir.is_explicit_defaults("1a 2b"):
        problems.append("the explicit-defaults reply is not recognised")
    results.append(("intake readiness: assumptions, answer codes and defaults", problems))

    problems = []
    schema_path = SKILL_DIR / "schema" / "intake-brief.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        names = set(schema["properties"]["slots"]["required"])
        if names != set(ir.ALL_SLOTS):
            problems.append(f"schema slots differ from the readiness rule: {sorted(names ^ set(ir.ALL_SLOTS))}")
    except (OSError, ValueError, KeyError) as exc:
        problems.append(f"schema/intake-brief.schema.json unreadable: {exc}")
    slots_doc = (SKILL_DIR / "docs" / "intake-slots.md").read_text(encoding="utf-8")
    missing = [name for name in ir.ALL_SLOTS if f"`{name}`" not in slots_doc]
    if missing:
        problems.append(f"docs/intake-slots.md does not define: {missing}")
    if ir.REPLY_FOOTER.split(",")[0].replace('"', "") not in slots_doc.replace('"', ""):
        problems.append("docs/intake-slots.md does not show the reply footer")
    dialogue = (SKILL_DIR / "docs" / "examples" / "intake-dialogue.md").read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)\n```", dialogue, re.DOTALL)
    try:
        questions = json.loads(block.group(1)) if block else []
    except ValueError:
        questions = []
    if not 3 <= len(questions) <= 5:
        problems.append("the worked dialogue's questions block is missing or not 3-5 questions")
    for q in questions:
        options = q.get("options") or []
        real = [o for o in options if not o.get("fallback")]
        if sum(1 for o in real if o.get("recommended")) != 1 or not options or not options[-1].get("fallback"):
            problems.append(f"dialogue question on {q.get('slot')} breaks the option rules")
    results.append(("intake schema, slot docs and worked dialogue agree with the rule", problems))
    return results


ONE_READ_LIMIT = 24000
# SKILL.md step 3 text replaced by the intake handoff (whitespace-normalised, case-insensitive)
REMOVED_SKILL_PHRASES = ("two is the limit", "one round is normal", "skip the wait",
                         "a third means step 0 was wrong")
# placeholder -> a real value, so a documented command can be run as written
PLACEHOLDERS = (("<user|db|file>", "user"), ("<trust>", "user"), ("<level>", "db"), ("<words>", "route"),
                ("WORDS...", "route"), ("<path>", "step"), ("step.<name>", "step.tools"), ("<id>", "prototype_v2"),
                ("<step>", "fi-close"), ("<kind>", "validator"), ("<instance_id|index>", "fi-close"))


def lookup_commands(docs: list[Path]) -> list[tuple[Path, str]]:
    """Every `catalog_lookup.py <command>` written in SKILL.md and the hand-written docs, placeholders filled in."""
    import re

    found: list[tuple[Path, str]] = []
    for path in docs:
        for match in re.finditer(r"catalog_lookup\.py ([^`\n]+)", path.read_text(encoding="utf-8")):
            text = match.group(1)
            for alternative in text.split("|") if "|" in text and "<user|db|file>" not in text else [text]:
                command = alternative.strip().rstrip(".,;:)")
                # a generic "<command>" slot or a "(overview, example, ...)" list names no single command
                if not command or command.startswith(("<", "(")):
                    continue
                command = command.replace("agent <id>", "agent custom-agent")
                for old, new in PLACEHOLDERS:
                    command = command.replace(old, new)
                command = re.sub(r"(--trust) T\b", r"\1 user", command)
                found.append((path, command))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compiler", type=Path, metavar="BACKEND_DIR", help="also check the real compiler's verdict")
    parser.add_argument("--catalog", type=Path, default=vm.DEFAULT_CATALOG)
    args = parser.parse_args(argv)

    catalog = vm.Catalog(json.loads(args.catalog.read_text(encoding="utf-8")) if args.catalog.is_file() else {})
    failures = 0

    print("Examples")
    for path in sorted((SKILL_DIR / "examples").glob("*.workflow.json")):
        key = path.name.replace(".workflow.json", "")
        trust = EXAMPLE_TRUST.get(key, "user")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        findings = run_checker(manifest, trust, catalog)
        schema, _status = vm.schema_findings(manifest, vm.DEFAULT_SCHEMA)
        allowed = EXAMPLE_ALLOWED_WARNINGS.get(key, set())
        bad = [f for f in findings + schema
               if f.level == "error" or (f.level == "warning" and f.code not in allowed)]
        if args.compiler:
            bad += [f for f in vm.compiler_findings(manifest, args.compiler, trust) if f.level == "error"]
        status = "ok" if not bad else "FAIL"
        failures += bool(bad)
        print(f"  {status:4} {path.name} (trust={trust})")
        for f in bad:
            print(f"       {f.level} [{f.code}] {f.where}: {f.message}")

    print("Known-bad cases")
    for name, manifest, trust, expected, verdict in CASES:
        findings = run_checker(manifest, trust, catalog)
        got = {(f.level, f.code) for f in findings}
        missing = [e for e in expected if e not in got]
        problems = [f"missing {missing}"] if missing else []
        if args.compiler:
            real = vm.compiler_findings(manifest, args.compiler, trust)
            rejected = any(f.level == "error" for f in real)
            if (verdict == "reject") != rejected:
                problems.append(f"real compiler {'rejected' if rejected else 'accepted'} (expected {verdict}): "
                                + "; ".join(f.message for f in real))
        status = "ok" if not problems else "FAIL"
        failures += bool(problems)
        print(f"  {status:4} {name}")
        for problem in problems:
            print(f"       {problem}")

    print("Clean cases (a finding here is a false positive)")
    for name, manifest, trust, forbidden, verdict in CLEAN_CASES:
        findings = run_checker(manifest, trust, catalog)
        hits = [f for f in findings
                if f.code in forbidden or ("*warning" in forbidden and f.level in ("warning", "error"))]
        problems = [f"{f.level} [{f.code}] {f.where}: {f.message}" for f in hits]
        if args.compiler:
            real = vm.compiler_findings(manifest, args.compiler, trust)
            rejected = any(f.level == "error" for f in real)
            if (verdict == "reject") != rejected:
                problems.append(f"real compiler {'rejected' if rejected else 'accepted'} (expected {verdict}): "
                                + "; ".join(f.message for f in real))
        failures += bool(problems)
        print(f"  {'ok' if not problems else 'FAIL':4} {name}")
        for problem in problems:
            print(f"       {problem}")

    print("Catalog and schema sync")
    sync_results = sync_checks(args.catalog)
    for name, problems in sync_results:
        failures += bool(problems)
        print(f"  {'ok' if not problems else 'FAIL':4} {name}")
        for problem in problems:
            print(f"       {problem}")

    print("Docs and lookup")
    doc_results = docs_checks(args.catalog)
    for name, problems in doc_results:
        failures += bool(problems)
        print(f"  {'ok' if not problems else 'FAIL':4} {name}")
        for problem in problems:
            print(f"       {problem}")

    print("Intake readiness")
    intake_results = intake_checks()
    for name, problems in intake_results:
        failures += bool(problems)
        print(f"  {'ok' if not problems else 'FAIL':4} {name}")
        for problem in problems:
            print(f"       {problem}")

    total = (len(CASES) + len(CLEAN_CASES) + len(EXAMPLE_TRUST) + len(sync_results) + len(doc_results)
             + len(intake_results))
    print(f"\n{total - failures}/{total} checks passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
