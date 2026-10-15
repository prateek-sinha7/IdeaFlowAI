"""QA-KB-122 fix (5-fixer, 2026-10-09): what the new runtime discovery will pick on the dev database.

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-122/fix-01-discovery-dry-run.py

SELECT only, inside a READ ONLY transaction. It emulates, in SQL, the predicates the e2e tests now
use through the API instead of pinned ids (all 67 runs belong to admin@velocity.ai, the `page` role):
  a_revised_family      newest run with a parent -> its root (not a divert root) -> members by created_at
  ISS-285               newest failed run with no output and no deliverable_filename
  ISS-313               newest completed run with deliverable_mimetype set and deliverable_filename null
  ISS-390               newest diverted run
  ISS-228               the saved workflow named "My prototype"
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
Q = {
    "a_revised_family: newest revised runs, with their root (walk up parent_run_id)": """
        with recursive up(id, start, parent, depth) as (
            select id, id, parent_run_id, 0 from workflow_runs where parent_run_id is not null
            union all
            select r.id, up.start, r.parent_run_id, up.depth + 1 from workflow_runs r join up on r.id = up.parent)
        select left(s.id,8) as revised_run, s.created_at, left(u.id,8) as root, coalesce(root.diverted_at_step_id,'') as root_divert
        from up u join workflow_runs s on s.id = u.start join workflow_runs root on root.id = u.id
        where u.parent is null order by s.created_at desc limit 5""",
    "members of family 78e185fb, in revision order (v1 = root)": """
        with recursive fam(id) as (select id from workflow_runs where id like '78e185fb%'
            union all select r.id from workflow_runs r join fam on r.parent_run_id = fam.id)
        select left(r.id,8), r.type, r.status, r.created_at from workflow_runs r join fam using(id) order by r.created_at, r.id""",
    "ISS-285: failed, no output, no deliverable_filename (newest first)": """
        select left(id,8), type, created_at from workflow_runs where status='failed'
        and (output is null or btrim(output)='') and deliverable_filename is null order by created_at desc limit 3""",
    "ISS-313: completed, deliverable_mimetype set, deliverable_filename null": """
        select left(id,8), type from workflow_runs where status='completed'
        and deliverable_mimetype is not null and deliverable_filename is null order by created_at desc""",
    "ISS-390: diverted (newest first)": """
        select left(id,8), type, completed_at is not null as terminal from workflow_runs where status='diverted' order by created_at desc""",
    "ISS-228: saved workflow named My prototype": """
        select left(id,8), name, source, overrides_pipeline_type from workflows where name = 'My prototype' and source = 'user'""",
}
with eng.connect() as c:
    for title, q in Q.items():
        print(f"== {title}")
        rows = c.execute(text(q)).fetchall()
        for row in rows:
            print("  ", tuple(row))
        if not rows:
            print("   (0 rows)")
