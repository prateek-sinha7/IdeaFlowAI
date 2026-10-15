"""READ-ONLY: does any dev-DB run carry a persisted composed manifest (the shape resume_run recompiles)?"""
import datetime
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

OUT = sys.argv[1]
eng = create_engine(settings.DATABASE_URL)
Q = [
    (
        "manifest_json by JSON type and presence of a 'steps' key (resume_run recompiles only a dict with steps, engine.py:15628)",
        "SELECT CASE WHEN manifest_json IS NULL THEN 'SQL NULL' ELSE json_typeof(manifest_json::json) END AS stored, "
        "COALESCE((manifest_json::jsonb ? 'steps'), false) AS has_steps_key, count(*) AS runs "
        "FROM workflow_runs GROUP BY 1, 2 ORDER BY 3 DESC",
    ),
    (
        "runs in a resumable status (failed | cancelled | degraded) that carry a composed manifest",
        "SELECT count(*) AS runs FROM workflow_runs WHERE status IN ('failed','cancelled','degraded') "
        "AND manifest_json IS NOT NULL AND json_typeof(manifest_json::json) = 'object'",
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
