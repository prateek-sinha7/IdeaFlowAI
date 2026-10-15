"""READ-ONLY: the dev-DB rows the resumability survey flagged (type user_stories_v2)."""
import datetime
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

OUT = sys.argv[1]
eng = create_engine(settings.DATABASE_URL)
Q = [
    (
        "runs of type user_stories_v2 (the id no checkout of this repo carries a workflow.yaml for)",
        "SELECT left(id::text,8) AS run, type, status, created_at::timestamp(0) AS created, left(coalesce(error,'<NULL>'),90) AS error, "
        "(SELECT count(*) FROM run_events e WHERE e.run_id = w.id) AS durable_events, "
        "(manifest_json IS NOT NULL) AS has_manifest FROM workflow_runs w WHERE type = 'user_stories_v2' ORDER BY created_at",
    ),
    (
        "all distinct run types in the DB with counts (to see which ids a checkout may not carry)",
        "SELECT type, count(*) AS n, max(created_at)::date AS last FROM workflow_runs GROUP BY type ORDER BY n DESC",
    ),
]
with eng.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    with open(OUT, "w") as fh:
        fh.write(f"# local dev DB, read-only transaction, run {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        for title, sql in Q:
            fh.write(f"\n-- {title}\nSQL> {' '.join(sql.split())}\n")
            res = conn.execute(text(sql))
            fh.write(f"     {list(res.keys())}\n")
            for row in res.fetchall():
                fh.write(f"     {tuple(row)}\n")
    conn.rollback()
print("wrote", OUT)
