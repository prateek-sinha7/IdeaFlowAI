"""QA-KB-120 analysis (3-analyzer, 2026-10-09): SELECT-only look at the dev database.

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-120/analysis-03-db-select.py

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

CITED = ["eb1d7551", "c10a03ed", "caa766dc", "1260b7ba", "9a931a7a"]
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


Q1 = (
    "select rf.run_id, wr.type, wr.status, rf.candidate_status, rf.published_status, rf.payload_built, "
    "rf.payload_materialized, rf.payload_chainable, rf.non_chainable_reason, rf.git_tag, left(coalesce(rf.commit_sha,''),10) "
    "from run_finalizations rf join workflow_runs wr on wr.id = rf.run_id where rf.run_id::text like :p"
)
Q2 = (
    "select candidate_status, published_status, payload_materialized, coalesce(non_chainable_reason,''), count(*) "
    "from run_finalizations group by 1,2,3,4 order by 5 desc"
)
Q3 = (
    "select wr.type, rf.candidate_status, rf.published_status, count(*) as n, min(wr.created_at)::date, max(wr.created_at)::date "
    "from run_finalizations rf join workflow_runs wr on wr.id = rf.run_id "
    "where rf.non_chainable_reason = 'output_unmaterializable' group by 1,2,3 order by n desc"
)
Q4 = (
    "select left(coalesce(error,''),110), count(*) from workflow_runs wr join run_finalizations rf on rf.run_id = wr.id "
    "where rf.non_chainable_reason = 'output_unmaterializable' group by 1 order by 2 desc"
)

with eng.connect() as c:
    say("Q1 " + Q1)
    say("(run_id, type, workflow_runs.status, candidate, published, payload_built, payload_materialized, payload_chainable, reason, git_tag, commit)")
    for p in CITED:
        for r in c.execute(text(Q1), {"p": p + "%"}).all():
            say("   " + str(tuple(r)))
    say()
    say("Q2 " + Q2)
    say("(candidate_status, published_status, payload_materialized, non_chainable_reason, n)")
    for r in c.execute(text(Q2)).all():
        say("   " + str(tuple(r)))
    say()
    say("Q3 " + Q3)
    say("(type, candidate_status, published_status, n, first_seen, last_seen)")
    for r in c.execute(text(Q3)).all():
        say("   " + str(tuple(r)))
    say()
    say("Q4 " + Q4)
    say("(workflow_runs.error prefix, n)")
    for r in c.execute(text(Q4)).all():
        say("   " + str(tuple(r)))

Path(__file__).with_name("analysis-03-db-select.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
