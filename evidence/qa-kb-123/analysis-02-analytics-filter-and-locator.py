"""QA-KB-123 analysis (3-analyzer, 2026-10-12): the analytics half, and the candidate runs.

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-123/analysis-02-analytics-filter-and-locator.py

Part A (SELECT only, READ ONLY transaction): what the Analytics "Prototype" pipeline filter selects for admin.
    backend/app/api/analytics.py:524-529   if pipeline: query.filter(WorkflowRun.type.in_((pipeline, f"{pipeline}_revision")))
    backend/app/api/analytics.py:437-446   one PipelineRollup per distinct r.type (no row is dropped for zero tokens)
    frontend AnalyticsPage.tsx:319         label = PIPELINE_LABELS[normalizeType(p.type)] ?? normalizeType(p.type)

Part B (SELECT only): which completed runs render through the first-party PrototypePreview, i.e. the six types the
    two routing sites send to setPrototypeContent (frontend/src/app/[...view]/page.tsx:1719-1724 live, :3303-3308 reopen)
    and PreviewPanel.tsx:1088-1092 maps to renderType "prototype". Plain prototype_v2 is in NEITHER list.

Part C (no database): an offline replay of the exact regex in tests/integration/e2e/framework/locators/analytics.py:125-128
    on (1) the recorded By Pipeline Type text in tests/integration/capture/35-analytics.json, (2) the one-row text the
    "Prototype" filter produces on today's data, (3) the two-row text it produced when a v1 `prototype` run existed,
    (4) a merged single row. The row layout is label, "<n> runs", dot, tokens, cost (AnalyticsPage.tsx:560-566).

DATABASE_URL is read from backend/.env and never printed. Nothing is written to the database.
"""
import json
import re
from pathlib import Path

from sqlalchemy import create_engine, text

repo = Path(__file__).resolve().parents[2]
env_path = repo / "backend" / ".env"
url = next(
    m.group(1).strip().strip("'\"")
    for m in (re.match(r"\s*DATABASE_URL\s*=\s*(.+?)\s*$", ln) for ln in env_path.read_text(encoding="utf-8").splitlines())
    if m
)
eng = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


Q_FILTER = (
    "select r.type, count(*), sum(case when r.status='completed' then 1 else 0 end) as completed "
    "from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' and r.type in ('prototype', 'prototype_revision') group by r.type order by r.type"
)
Q_MODELS = (
    "select coalesce(r.model_id,'(null)'), count(*) from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' and r.type in ('prototype', 'prototype_revision') group by 1 order by 2 desc"
)
Q_AGENT_MODELS = (
    "select left(r.id,8), r.status, r.agent_outputs from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' and r.type in ('prototype', 'prototype_revision') order by r.created_at"
)
Q_UNFILTERED = (
    "select r.type, count(*) from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' group by r.type order by 2 desc, 1"
)
PROTO_RENDERED = (
    "prototype", "prototype_revision", "prototype_large_revision", "prototype_feature_revision",
    "prototype_v2_revision", "prototype_v2_feature_revision",
)
Q_CAND = (
    "select left(r.id,8), r.type, r.status, coalesce(r.deliverable_filename,''), coalesce(r.deliverable_mimetype,''), "
    "left(coalesce(r.parent_run_id,''),8), r.created_at::date "
    "from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' and r.status = 'completed' and r.type = any(:types) order by r.created_at desc"
)
Q_V2_PLAIN = (
    "select left(r.id,8), r.type, r.status, coalesce(r.deliverable_filename,''), coalesce(r.deliverable_mimetype,'') "
    "from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' and r.status = 'completed' and r.type = 'prototype_v2' order by r.created_at desc limit 3"
)

with eng.connect() as c:
    say("PART A - Analytics pipeline=prototype selects type IN ('prototype','prototype_revision')")
    say("Q1 " + Q_FILTER)
    say("(type, runs, completed) -> each distinct type becomes ONE row in By Pipeline Type")
    rows = c.execute(text(Q_FILTER)).all()
    for r in rows:
        say("   " + str(tuple(r)))
    say(f"   => {len(rows)} row(s) in the filtered breakdown; label of each = PIPELINE_LABELS[normalizeType(type)] = 'Prototype' -> 'PROTOTYPE'")
    say()
    say("Q1b " + Q_MODELS)
    say("(run-row model_id, runs) for the same filter. The model <select> renders only when the filtered summary lists MORE than one model")
    say("(AnalyticsPage.tsx:425 availableModelIds.length > 1); the By Model panel also merges per-agent model ids from agent_outputs, which this")
    say("column does not show, so this is a lower bound on the model count, not the count itself")
    for r in c.execute(text(Q_MODELS)).all():
        say("   " + str(tuple(r)))
    say()
    say("Q1c " + Q_AGENT_MODELS)
    say("(run id8, status, distinct per-agent model_id values found in agent_outputs): the model <select> lists these, minus 'unknown'")
    seen = set()
    for rid, status, ao in c.execute(text(Q_AGENT_MODELS)).all():
        ids = set()
        try:
            for a in json.loads(ao or "[]"):
                if isinstance(a, dict) and a.get("model_id"):
                    ids.add(a["model_id"])
        except Exception as e:  # keep the probe read-only and total
            ids.add("<unparseable " + type(e).__name__ + ">")
        seen |= ids
        say("   " + str((rid, status, sorted(ids))))
    say(f"   => {len(seen)} distinct model id(s) across the filtered runs: {sorted(seen)}")
    say("   => AnalyticsPage.tsx:425 renders the model <select> only for MORE than one, so ISS-289 skips at test_analytics.py:392-393 once the parser works")
    say()
    say("Q2 " + Q_UNFILTERED)
    say("(admin's whole history, by type: what the UNFILTERED breakdown has one row for)")
    for r in c.execute(text(Q_UNFILTERED)).all():
        say("   " + str(tuple(r)))
    say("   => PIPELINE_LABELS has no key for prototype_v2, prototype_v2_revision (normalizes to prototype_v2), backlog, user_stories_v2:")
    say("      those rows show the raw id uppercased (PROTOTYPE_V2 ...), which is also why S-10-12's  text.count('PROTOTYPE') > 1  is true today")
    say()
    say("PART B - completed runs whose type renders through the first-party PrototypePreview")
    say("Q3 " + Q_CAND.replace(":types", str(PROTO_RENDERED)))
    say("(id8, type, status, deliverable_filename, deliverable_mimetype, parent8, created)")
    cand = c.execute(text(Q_CAND), {"types": list(PROTO_RENDERED)}).all()
    for r in cand:
        say("   " + str(tuple(r)))
    say(f"   => {len(cand)} completed run(s) of those six types; NONE is a v1 `prototype`, all are revision members of prototype_v2 families")
    say()
    say("Q4 " + Q_V2_PLAIN)
    say("(plain prototype_v2, completed: newest 3; its type is in neither routing list above)")
    for r in c.execute(text(Q_V2_PLAIN)).all():
        say("   " + str(tuple(r)))

say()
say("PART C - the locator regex (framework/locators/analytics.py:125-128), replayed offline")


def number(s):
    return float(str(s).replace(",", ""))


def parse(t):
    out = {}
    for runs, label in re.findall(
        r"(\d[\d,]*)\s+runs?\b[^\n]*\n(?:[^\n]*\n){0,3}?([A-Z][A-Z0-9 ._&-]{2,40})\n", t
    ):
        out.setdefault(label.strip(), number(runs))
    return out


cap = json.load(open(repo / "tests" / "integration" / "capture" / "35-analytics.json"))["text"]
card = cap[cap.index("By Pipeline Type"):].split("By Model")[0]
# the slice up to "By Model" also holds four rows of a neighbouring panel (APP BUILDER 6 runs, PRESENTATION 6 runs, ...);
# the By Pipeline Type card itself ends with its 19th row, EX_A3_TARGET ... <$0.01
card = card[: card.index("<$0.01\n") + len("<$0.01\n")]
say("(1) recorded capture/35, the 19 By Pipeline Type rows (label first). TRUE counts: APP BUILDER 3, PROTOTYPE 12, CUSTOM 24, ... PROTOTYPE 8")
parsed = parse(card)
say("    parse -> " + str({k: parsed[k] for k in list(parsed)[:5]}) + " ...  (" + str(len(parsed)) + " labels read; 19 rows, the last never read)")
say("    => 'PROTOTYPE' reads 3.0 (APP BUILDER's count): each count is paired with the label of the NEXT row; the last row is never read")
true_rows = re.findall(r"\n([^\n]+)\n(\d[\d,]*) runs?\n", card)
say(f"    true rows: {len(true_rows)}, summing to {sum(number(n) for _, n in true_rows):.0f}; parsed: {len(parsed)} labels, summing to {sum(parsed.values()):.0f}")
say(f"    CUSTOM's true count (24) among the parsed values: {24.0 in parsed.values()}; '.NET MIGRATION' among the parsed labels: {'.NET MIGRATION' in parsed}  (a label that does not start with A-Z never matches [A-Z][A-Z0-9 ._&-]{{2,40}})")
say()
one = "By Pipeline Type\nPROTOTYPE\n6 runs\n·\n1.0M\n$0.20"
two = "By Pipeline Type\nPROTOTYPE\n12 runs\n·\n11.4M\n$4.49\nPROTOTYPE\n8 runs\n·\n2.4M\n$0.86"
merged = "By Pipeline Type\nPROTOTYPE\n20 runs\n·\n13.8M\n$5.35"
say("(2) today, filter=Prototype -> one prototype_revision row:   " + repr(parse(one)) + "   <- .get('PROTOTYPE') is None -> 'Prototype not found in the By Pipeline Type breakdown'")
say("(3) when a v1 `prototype` run existed (two rows, one label): " + repr(parse(two)) + "   <- truthy, only because the label repeats (D-11)")
say("(4) if D-11 were fixed (one merged row):                      " + repr(parse(merged)) + "   <- None again")

Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
