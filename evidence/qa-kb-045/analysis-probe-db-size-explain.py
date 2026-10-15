"""Read-only size probe for QA-KB-045 (SELECT only; session forced READ ONLY; 20 s timeout)."""
import sys

sys.path.insert(0, ".")

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

eng = create_engine(
    settings.DATABASE_URL,
    connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=20000"},
)
with eng.connect() as c:
    print("read_only:", c.execute(text("SHOW transaction_read_only")).scalar())
    rows = c.execute(
        text(
            "SELECT run_id, owner_id, workspace_id, count(*) AS n, max(seq) AS max_seq, "
            "pg_size_pretty(sum(length(payload_json::text))::bigint) AS payload_bytes "
            "FROM run_events GROUP BY run_id, owner_id, workspace_id ORDER BY n DESC LIMIT 5"
        )
    ).all()
    for r in rows:
        print("  run=%s... n=%s max_seq=%s payload=%s" % (str(r[0])[:8], r[3], r[4], r[5]))
    total_runs = c.execute(text("SELECT count(DISTINCT run_id) FROM run_events")).scalar()
    total = c.execute(text("SELECT count(*) FROM run_events")).scalar()
    print("  total run_events rows:", total, " distinct runs:", total_runs)
    if rows:
        top = rows[0]
        plan = c.execute(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT max(seq) FROM run_events "
                "WHERE run_id=:r AND owner_id=:o AND workspace_id=:w"
            ),
            {"r": top[0], "o": top[1], "w": top[2]},
        ).all()
        print("  EXPLAIN ANALYZE max(seq) on the biggest run:")
        for p in plan:
            print("    " + p[0])
        plan2 = c.execute(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT * FROM run_events "
                "WHERE run_id=:r AND seq>0 AND owner_id=:o AND workspace_id=:w ORDER BY seq ASC"
            ),
            {"r": top[0], "o": top[1], "w": top[2]},
        ).all()
        print("  EXPLAIN ANALYZE read_events-equivalent on the biggest run:")
        for p in plan2:
            print("    " + p[0])
    nt = c.execute(
        text(
            "SELECT status, count(*) FROM workflow_runs WHERE status IN "
            "('running','planning','clarifying','waiting_for_user','generating','analyzing','revising') "
            "GROUP BY status"
        )
    ).all()
    print("  non-terminal workflow_runs by status (boot-restore population):", [tuple(x) for x in nt])
