"""QA-KB-122 analysis (3-analyzer, 2026-10-09): does the ISS-213 XPASS reflect the app or the data?

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-122/analysis-03-iss213-arithmetic.py

test_a_type_chips_count_reflects_the_true_account_total (06_run_history/test_run_history_pagination.py:186-216)
asserts   shown >= extra_beyond_page_one   where
  extra_beyond_page_one = max over buckets of (runs of that bucket at offset >= 50)       [API, newest first]
  shown                 = the bucket chip in the UI = families of that bucket in the FIRST 50 runs
                          (WorkflowHistory.tsx:1200-1206 builds typeCounts from the loaded families only)

This script replays that arithmetic against the dev database for the admin account, SELECT only
(READ ONLY transaction). It prints the numbers; it does not print DATABASE_URL.
"""
import re
from collections import Counter
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


def bucket(t: str) -> str:  # mirrors the test's _bucket_of and filterBucketFor
    base = t.replace("_revision", "")
    return base if base in {"user_stories", "ppt", "prototype", "app_builder"} else "custom"


Q = (
    "select r.id, r.type, r.parent_run_id from workflow_runs r join users u on u.id = r.user_id "
    "where u.email = 'admin@velocity.ai' order by r.created_at desc"
)
with eng.connect() as c:
    rows = [tuple(r) for r in c.execute(text(Q)).all()]
say("Q " + Q)
say(f"admin runs total (X-Total-Count): {len(rows)}")
first, older = rows[:50], rows[50:]
say(f"first page: {len(first)} runs   older (offset>=50): {len(older)} runs")

older_by = Counter(bucket(t) for _, t, _ in older)
say(f"older runs by bucket -> {dict(older_by)}")
param, extra = max(older_by.items(), key=lambda kv: kv[1]) if older_by else (None, 0)
say(f"extra_beyond_page_one = {extra}  (bucket {param!r})")

# families inside the first page: a run whose parent is also in the page collapses into the parent's card
ids_first = {i for i, _, _ in first}
roots_first = [(i, t) for i, t, p in first if p is None or p not in ids_first]
shown_by = Counter(bucket(t) for _, t in roots_first)
say(f"first-page family cards by bucket (approximates the chip counts) -> {dict(shown_by)}")
shown = shown_by.get(param, 0)
say(f"shown (chip for bucket {param!r}) ~= {shown}")
say(f"assertion  shown >= extra_beyond_page_one  ->  {shown} >= {extra}  ->  {shown >= extra}")
true_total = Counter(bucket(t) for _, t, _ in rows)
say(f"TRUE per-bucket run totals (what the test title says the chip should show) -> {dict(true_total)}")
say(f"the chip for {param!r} undercounts the true run total by {true_total[param] - shown}, and the test still passes: {shown >= extra}")

Path(__file__).with_suffix(".txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
