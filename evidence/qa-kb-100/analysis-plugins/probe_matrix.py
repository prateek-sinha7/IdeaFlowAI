"""READ-ONLY probe (QA-KB-100 analysis): what can an override step carry at trust="db" (what
merge_override_steps does today) vs trust="user" (the stricter level the inline launch path and
the selections overlay already use)?

No server, no DB, no model call. Imports the real compiler/registry and the real
merge_override_steps; compile_at() copies overrides.py:87-100 line for line, changing only the
trust argument, so "db" here IS the shipped behaviour.
"""
import copy
from agents.execution_engine.engine import compile_for_run, _CAPABILITY_REGISTRY as R
from agents.execution_engine.overrides import (
    merge_override_steps, _PLACEHOLDER_DELIVERABLE, _PLACEHOLDER_CLARIFY,
)
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import ManifestValidationError, build_manifest_from_dict

ppt = compile_for_run("ppt")


def compile_at(trust, steps):
    raw = {"id": ppt.id, "steps": steps, "deliverable": _PLACEHOLDER_DELIVERABLE,
           "planner": "skip", "clarify": _PLACEHOLDER_CLARIFY}
    try:
        parsed = build_manifest_from_dict(raw, f"override:{ppt.id}")
        return WorkflowCompiler().compile(parsed, R, trust=trust), None
    except (ManifestValidationError, CompilerError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def base(**over):
    s = {"agent": "custom-agent", "instance_id": "mine", "name": "mine", "prompt": "You are mine.",
         "tools": {"read_files": False, "write_files": False, "exec": False}}
    s.update(over)
    return s


def tools(**t):
    d = {"read_files": False, "write_files": False, "exec": False}
    d.update(t)
    return d


CASES = [
    ("CONTROL benign step", base()),
    ("CONTROL gates=[human] (user_allowed)", base(gates=["human"])),
    ("gate security (the reported case)", base(gates=["security"])),
    ("gate approval", base(gates=["approval"])),
    ("exec grant + gates security,approval", base(gates=["security", "approval"], tools=tools(exec=True))),
    ("exec grant, NO gates (D-01 needs both)", base(tools=tools(exec=True))),
    ("spawn_subagents grant", base(tools=tools(spawn_subagents=True))),
    ("tool_sets [spawn_subagents]", base(tools=tools(tool_sets=["spawn_subagents"]))),
    ("tool_sets [pptx]", base(tools=tools(tool_sets=["pptx"]))),
    ("tool_sets [ask_user]", base(tools=tools(tool_sets=["ask_user"]))),
    ("tool_sets [playwright] (in untrusted cap list)", base(tools=tools(tool_sets=["playwright"]))),
    ("hooks [provenance_audit]", base(hooks=["provenance_audit"])),
    ("compaction html_skeleton", base(compaction="html_skeleton")),
    ("post_step revision_validation", base(post_step="revision_validation")),
    ("validators [code_test] only (user_allowed)", base(validators=["code_test"])),
    ("exec + validators [code_test,code_lint] + gates security,approval",
     base(gates=["security", "approval"], validators=["code_test", "code_lint"], tools=tools(exec=True, write_files=True))),
    ("mcp postgres (powerful) + security gate + secrets grant",
     base(gates=["security"], tools=tools(mcp=["postgres.query"], secrets=["PGURL"]))),
    ("mcp filesystem.read_file no gate", base(tools=tools(mcp=["filesystem.read_file"]))),
    ("network grant", base(tools=tools(network=True))),
    ("secrets grant", base(tools=tools(secrets=["X"]))),
]


def eff(step):
    t = step.tools
    return (f"exec={t.exec} spawn={t.spawn_subagents} git={t.git} net={t.network} "
            f"tool_sets={list(t.tool_sets or [])} mcp={list(getattr(t,'mcp',[]) or [])} "
            f"gates={list(step.gates)} hooks={list(step.hooks)} post_step={step.post_step} compaction={step.compaction}")


print("=" * 100)
print("A. shipped behaviour = merge_override_steps(ppt, [step], registry)  [trust=db]")
print("   'applied' means the function returned a NEW plan carrying the override step;")
print("   'refused' means it returned the file plan unchanged.")
print("=" * 100)
for label, step in CASES:
    merged = merge_override_steps(ppt, [copy.deepcopy(step)], R)
    if merged is ppt:
        print(f"[refused] {label}")
    else:
        print(f"[APPLIED] {label}\n          -> {eff(merged.steps[0])}")

print()
print("=" * 100)
print('B. same step list compiled at trust="user" (what option A would do)')
print("=" * 100)
for label, step in CASES:
    plan, err = compile_at("user", [copy.deepcopy(step)])
    if err:
        print(f"[refused] {label}\n          -> {err[:230]}")
    else:
        print(f"[accepted] {label}\n          -> {eff(plan.steps[0])}")

print()
print("=" * 100)
print("C. trust=db vs trust=user, agree/disagree per case (a DISAGREE row is a case the shipped trust=db lets through)")
print("=" * 100)
for label, step in CASES:
    db_ok = merge_override_steps(ppt, [copy.deepcopy(step)], R) is not ppt
    user_plan, _ = compile_at("user", [copy.deepcopy(step)])
    user_ok = user_plan is not None
    print(f"{'DISAGREE' if db_ok != user_ok else 'same    '}  db={'applied' if db_ok else 'refused':8s} user={'accepted' if user_ok else 'refused':8s}  {label}")
