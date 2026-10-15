"""READ-ONLY survey of the local dev DB for resume attempts that never reached a dispatch.

Every statement runs inside `SET TRANSACTION READ ONLY`; nothing is written. The DATABASE_URL
is taken from the app settings and is never printed.
"""
import datetime
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

OUT = sys.argv[1]
eng = create_engine(settings.DATABASE_URL)

QUERIES = [
    (
        "total run_resuming markers and their prior_status / reason payload values",
        """SELECT payload_json->>'prior_status' AS prior_status, payload_json->>'reason' AS reason, count(*) AS n
           FROM run_events WHERE type = 'run_resuming' GROUP BY 1, 2 ORDER BY n DESC""",
    ),
    (
        "attempts (run_resuming markers) with NO pipeline_start between the marker and the next marker / end of log",
        """WITH m AS (
             SELECT run_id, seq, created_at,
                    lead(seq) OVER (PARTITION BY run_id ORDER BY seq) AS next_marker_seq
             FROM run_events WHERE type = 'run_resuming'
           )
           SELECT count(*) AS markers,
                  count(*) FILTER (WHERE NOT EXISTS (
                      SELECT 1 FROM run_events e
                      WHERE e.run_id = m.run_id AND e.seq > m.seq
                        AND (m.next_marker_seq IS NULL OR e.seq < m.next_marker_seq)
                        AND e.type = 'pipeline_start')) AS never_dispatched
           FROM m""",
    ),
    (
        "the never-dispatched attempts: run, marker seq, events that follow (types), run status/error today",
        """WITH m AS (
             SELECT run_id, seq, created_at,
                    lead(seq) OVER (PARTITION BY run_id ORDER BY seq) AS next_marker_seq
             FROM run_events WHERE type = 'run_resuming'
           ), nd AS (
             SELECT * FROM m WHERE NOT EXISTS (
                 SELECT 1 FROM run_events e
                 WHERE e.run_id = m.run_id AND e.seq > m.seq
                   AND (m.next_marker_seq IS NULL OR e.seq < m.next_marker_seq)
                   AND e.type = 'pipeline_start')
           )
           SELECT left(nd.run_id::text, 8) AS run, nd.seq AS marker_seq, nd.created_at::timestamp(0) AS marked_at,
                  (SELECT string_agg(e.seq || ':' || e.type, ', ' ORDER BY e.seq)
                     FROM run_events e
                    WHERE e.run_id = nd.run_id AND e.seq > nd.seq
                      AND (nd.next_marker_seq IS NULL OR e.seq < nd.next_marker_seq)) AS after_marker,
                  w.type AS run_type, w.status AS run_status, left(coalesce(w.error, '<NULL>'), 70) AS run_error
           FROM nd JOIN workflow_runs w ON w.id = nd.run_id
           ORDER BY nd.created_at""",
    ),
]

with eng.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    with open(OUT, "w") as fh:
        fh.write(
            f"# local dev DB, read-only transaction, run {datetime.datetime.now().isoformat(timespec='seconds')}\n"
        )
        for title, sql in QUERIES:
            fh.write(f"\n-- {title}\nSQL> {' '.join(sql.split())}\n")
            res = conn.execute(text(sql))
            fh.write(f"     {list(res.keys())}\n")
            for row in res.fetchall():
                fh.write(f"     {tuple(row)}\n")
    conn.rollback()
print("wrote", OUT)
