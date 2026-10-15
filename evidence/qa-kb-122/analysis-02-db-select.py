"""QA-KB-122 analysis (3-analyzer, 2026-10-09): SELECT-only look at the dev database.

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-122/analysis-02-db-select.py

Question: do the run / saved-workflow ids the e2e suites pin as literals still exist, and is the
"genuine 2-member revision family" the ISS-230 / ISS-606 / ISS-607 tests rely on still there?

Every statement is a SELECT inside a READ ONLY transaction (default_transaction_read_only=on).
DATABASE_URL is read from backend/.env and never printed.
"""
import re
from pathlib import Path

from sqlalchemy import create_engine, text

env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
url = next(
    m.group(1).strip().strip("'\"")
    for m in (re.match(r"\s*DATABASE_URL\s*=\s*(.+?)\s*$", ln) for ln in env_path.read_text(encoding="utf-8").splitlines())
    if m
)
eng = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})

# (prefix, where the e2e tree pins it)
PINNED_RUNS = [
    ("2708dbf1", "ISS-230 / ISS-606 / ISS-607 ROOT_RUN_ID + MID_FAMILY_ROOT_ID (suites/21_*)"),
    ("23bd9c67", "ISS-230 / ISS-606 V2_RUN_ID (suites/21_*)"),
    ("3839720c", "ISS-607 MID_FAMILY_LATEST_ID (suites/21_*)"),
    ("a40d0f2b", "test_iss285 FAILED_RUN_NO_DELIVERABLE (suites/07_*)"),
    ("edba51b5", "test_iss313 RUN_WITH_NULL_DELIVERABLE_FILENAME (suites/07_*)"),
    ("28a318c9", "test_iss390 DIVERTED_RUN (suites/07_*)"),
    ("77f74563", "ISS-618 card says this is the ISS-230 fixture root"),
]
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


Q1 = (
    "select id, type, status, left(coalesce(parent_run_id,''),8) as parent, left(coalesce(source_run_id,''),8) as source, "
    "created_at::date, coalesce(deliverable_filename,'') from workflow_runs where id like :p"
)
Q2 = (
    "select id, type, status, left(parent_run_id,8), left(source_run_id,8), created_at::date from workflow_runs "
    "where parent_run_id like :p or source_run_id like :p order by created_at"
)
Q3 = "select id, name, source from workflows where id like :p"
Q4 = (
    "select count(*) filter (where parent_run_id is not null) as with_parent, "
    "count(*) filter (where source_run_id is not null) as with_source, count(*) as total from workflow_runs"
)
Q5 = (
    "select coalesce(source_run_id, parent_run_id) as root, count(*) as children from workflow_runs "
    "where coalesce(source_run_id, parent_run_id) is not null group by 1 order by 2 desc limit 8"
)
Q6 = "select type, count(*) from workflow_runs group by 1 order by 2 desc"

with eng.connect() as c:
    say("Q1 " + Q1)
    say("(id, type, status, parent, source, created, deliverable_filename)")
    for p, why in PINNED_RUNS:
        rows = c.execute(text(Q1), {"p": p + "%"}).all()
        say(f"-- {p}  [{why}]  -> {len(rows)} row(s)")
        for r in rows:
            say("   " + str(tuple(r)))
    say()
    say("Q2 " + Q2)
    say("(children of the ISS-230 family root, by parent_run_id or source_run_id)")
    for p in ("2708dbf1", "77f74563"):
        rows = c.execute(text(Q2), {"p": p + "%"}).all()
        say(f"-- members pointing at {p}: {len(rows)}")
        for r in rows:
            say("   " + str(tuple(r)))
    say()
    say("Q3 " + Q3)
    for p in ("656ca387",):
        rows = c.execute(text(Q3), {"p": p + "%"}).all()
        say(f"-- saved workflow {p} (test_iss228 PROTO_ID): {len(rows)} row(s)")
        for r in rows:
            say("   " + str(tuple(r)))
    say()
    say("Q4 " + Q4)
    say("   " + str(tuple(c.execute(text(Q4)).one())) + "   (with_parent, with_source, total)")
    say()
    say("Q5 " + Q5)
    say("(root, number of revision rows that point at it)")
    for r in c.execute(text(Q5)).all():
        say("   " + str((str(r[0])[:8], r[1])))
    say()
    say("Q6 " + Q6)
    for r in c.execute(text(Q6)).all():
        say("   " + str(tuple(r)))


Q7 = "select min(created_at), max(created_at), count(*) from workflow_runs"
Q8 = "select left(id,8), name, source, overrides_pipeline_type from workflows where name ilike 'My prototype%'"
Q9 = (
    "select left(id,8), type, status, created_at::date from workflow_runs "
    "where type in ('ex_A4_human_divert','ex_A4_human_gate','user_stories','ex_A3_c_dutch') order by created_at"
)
with eng.connect() as c:
    say()
    say("Q7 " + Q7)
    say("   " + str(tuple(c.execute(text(Q7)).one())) + "   (oldest run, newest run, total): every id the suites pinned on 2026-09-21 predates the oldest row")
    say()
    say("Q8 " + Q8)
    say("   " + str([tuple(r) for r in c.execute(text(Q8)).all()]) + "   (the saved workflow test_iss228 calls 'My prototype' exists under a different id than its PROTO_ID 656ca387)")
    say()
    say("Q9 " + Q9)
    for r in c.execute(text(Q9)).all():
        say("   " + str(tuple(r)))

Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
