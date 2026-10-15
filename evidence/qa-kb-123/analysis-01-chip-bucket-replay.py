"""QA-KB-123 analysis (3-analyzer, 2026-10-12): SELECT-only replay of the Run History chip logic.

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-123/analysis-01-chip-bucket-replay.py

Question: the three chip-clicking e2e tests time out waiting for a "Prototype <n>" chip. Which runs does the
dev database hold for the prototype family, which chip bucket does the app put each one in, and would ANY
of them make the Prototype chip render?

Every statement is a SELECT inside a READ ONLY transaction (default_transaction_read_only=on).
DATABASE_URL is read from backend/.env and never printed. Nothing is written to the database.

The JS being replayed (read, not guessed):
  RevisionFamilyView.tsx:86-88    baseWorkflowType(t)  = t.replace("_revision", "")      (first occurrence only)
  RevisionFamilyView.tsx:90       KNOWN_FRAMEWORK_BASE_TYPES = {user_stories, ppt, prototype, app_builder}
  RevisionFamilyView.tsx:101-104  filterBucketFor(t)   = base if base in the set else "custom"
  RevisionFamilyView.tsx:183-192  familyRootFor(run, byId)
  RevisionFamilyView.tsx:194-229  groupRunsByFamily(runs): root = member whose id IS the key, else earliest member
  WorkflowHistory.tsx:231         getWorkflows(token, {limit: 50})   -> the window the chips are computed from
  WorkflowHistory.tsx:1193-1206   typeCounts[filterBucketFor(g.root.type)] += 1 per FAMILY (not per run)
  WorkflowHistory.tsx:1284        if (type !== "all" && count === 0) return null   -> a zero chip is not rendered
  backend/app/api/runs.py:790-792 order_by(created_at.desc()).offset(offset).limit(limit)
  backend/app/api/runs.py:410-470 _compute_root_ids: root_run_id = last OWNED ancestor via parent_run_id
"""
import re
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
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


FRAMEWORK = {"user_stories", "ppt", "prototype", "app_builder"}


def base_type(t):
    return t.replace("_revision", "", 1)  # JS String.replace with a string pattern replaces the first match only


def bucket(t):
    b = base_type(t)
    return b if b in FRAMEWORK else "custom"


Q_ACCTS = (
    "select u.email, r.type, r.status, count(*) from workflow_runs r join users u on u.id = r.user_id "
    "where r.type like 'prototype%' group by 1, 2, 3 order by 1, 2, 3"
)
Q_EXACT = "select count(*) from workflow_runs where type = 'prototype'"
Q_TYPES = "select type, count(*) from workflow_runs group by 1 order by 2 desc, 1"
Q_OTHER_FRAMEWORKS = (
    "select left(id,8), type, status, created_at from workflow_runs "
    "where type in ('user_stories','user_stories_v2','ppt','ppt_revision','ppt_v2','app_builder','app_builder_revision') order by created_at"
)
Q_ADMIN = (
    "select r.id, r.type, r.status, r.parent_run_id, r.created_at, coalesce(r.deliverable_filename,'') "
    "from workflow_runs r join users u on u.id = r.user_id where u.email = :email order by r.created_at desc, r.id"
)
Q_RANGE = "select min(created_at), max(created_at), count(*) from workflow_runs"

with eng.connect() as c:
    say("Q1 " + Q_RANGE)
    say("   " + str(tuple(c.execute(text(Q_RANGE)).one())) + "   (oldest run, newest run, total rows, all accounts)")
    say()
    say("Q2 " + Q_EXACT)
    say("   " + str(c.execute(text(Q_EXACT)).scalar_one()) + "   <- runs whose type is EXACTLY 'prototype', all accounts")
    say()
    say("Q3 " + Q_ACCTS)
    say("(email, type, status, count) for every prototype-family run, every account")
    for r in c.execute(text(Q_ACCTS)).all():
        say("   " + str(tuple(r)))
    say()
    say("Q4 " + Q_TYPES)
    say("(type, count) over every account")
    for r in c.execute(text(Q_TYPES)).all():
        say("   " + str(tuple(r)))
    say()
    say("Q4b " + Q_OTHER_FRAMEWORKS)
    say("(id8, type, status, created) for the other framework families, all accounts: the only rows there are")
    for r in c.execute(text(Q_OTHER_FRAMEWORKS)).all():
        say("   " + str(tuple(r)))
    say()

    rows = c.execute(text(Q_ADMIN), {"email": "admin@velocity.ai"}).all()
    runs = [
        {"id": r[0], "type": r[1], "status": r[2], "parent": r[3], "created": r[4], "file": r[5]} for r in rows
    ]
    by_all = {r["id"]: r for r in runs}

    # backend/app/api/runs.py:_compute_root_ids over the admin's own runs (owned-only walk, cycle guard)
    def server_root(rid):
        seen, cur = set(), rid
        while True:
            p = by_all[cur]["parent"]
            if p is None or p not in by_all or cur in seen:
                return cur
            seen.add(cur)
            cur = p

    for r in runs:
        r["root"] = server_root(r["id"])

    def family_root_for(run, by_id):
        cur = run
        while cur["id"] != cur["root"]:
            parent = by_id.get(cur["parent"]) if cur["parent"] else None
            if parent is None:
                return cur["root"]
            if parent["status"] == "diverted":
                return cur["id"]
            cur = parent
        return cur["id"]

    def chips(window):
        by_id = {r["id"]: r for r in window}
        buckets = defaultdict(list)
        for r in window:
            buckets[family_root_for(r, by_id)].append(r)
        counts = Counter()
        fam_root_of = {}
        for key, members in buckets.items():
            members.sort(key=lambda m: (m["created"], m["id"]))
            root = next((m for m in members if m["id"] == key), members[0])
            counts[bucket(root["type"])] += 1
            for m in members:
                fam_root_of[m["id"]] = root
        return counts, fam_root_of

    say("Q5 " + Q_ADMIN.replace(":email", "'admin@velocity.ai'"))
    say(f"   admin@velocity.ai holds {len(runs)} runs (the account every chip test signs in as)")
    say()

    for title, window in (
        ("UI window: the first 50 runs (WorkflowHistory.tsx:231 limit=50)", runs[:50]),
        ("every run loaded (what scrolling to the end would give)", runs),
    ):
        counts, fam_root_of = chips(window)
        say(f"== {title}")
        say(f"   runs in window: {len(window)}   families: {sum(counts.values())}")
        for b in ("user_stories", "ppt", "prototype", "app_builder", "custom"):
            shown = "rendered" if counts.get(b, 0) > 0 else "NOT rendered (count 0, WorkflowHistory.tsx:1284)"
            say(f"   chip {b:<13} count {counts.get(b, 0):>3}   {shown}")
        say()
        say("   prototype-family runs in this window: id8  type  status  parent8  root8  family-root-type  -> bucket")
        for r in window:
            if r["type"].startswith("prototype"):
                fr = fam_root_of[r["id"]]
                say(
                    f"      {r['id'][:8]}  {r['type']:<32} {r['status']:<10} {(r['parent'] or '-')[:8]:<9} "
                    f"{r['root'][:8]:<9} {fr['type']:<32} -> {bucket(fr['type'])}"
                )
        say()

    pos = {r["id"]: i for i, r in enumerate(runs)}
    say("== where each prototype_revision run sits in the created_at-desc list (index 0 = newest; window is 0..49)")
    for r in runs:
        if r["type"] == "prototype_revision":
            say(f"      {r['id'][:8]} status={r['status']:<10} index={pos[r['id']]:>2}  parent={(r['parent'] or '-')[:8]}  root={r['root'][:8]}  root-type={by_all[r['root']]['type']}")

Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
