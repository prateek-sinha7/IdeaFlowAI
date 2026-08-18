"""ISS-123 — forensic audit of the engine events destroyed by the pre-FIX-240 seq collision.

STRICTLY READ-ONLY. Opens the database with SQLite's ``mode=ro`` URI and issues only
SELECTs. It exists so the historical damage is NAMEABLE and RE-MEASURABLE; it never
repairs anything, and nothing here should ever be turned into a repair.

WHY NOT BACK-FILL — the sharp reason
------------------------------------
For 11 of the 15 destroyed events the CONTENT is exactly recoverable: they are
``agent_chunk`` fragments, and ``artifact_refs.content`` is an independent authoritative
record of the same text written by the artifact graph rather than the event sink. So the
often-repeated "a dropped run_events row has no provenance to reconstruct from" is only
half true, and it is the wrong half to lead with.

The correct reason to refuse is narrower and stronger: the content is recoverable, the
IDENTITY is not. ``event_id`` is the key the entire replay contract rests on —
``run_stream.py``'s ``replayed_event_ids`` de-dup, ``append_event_next_seq``'s
idempotency, and the frontend's ``seenRef`` (FIX-175). A back-filled row must mint an
``event_id`` that never existed, which makes the durable log assert the engine emitted a
frame it did not, and creates a de-dup key no live frame can ever match. The four
structural losses are unrecoverable outright: ``workflow_clarifications`` is empty
corpus-wide and ``gate_events`` records no approve outcome for any run.

If a damaged agent's text is ever actually needed, read ``artifact_refs.content`` — the
intact record already exists and is already what Preview/Files render.

THE MECHANISM (FIX-240 / ISS-121)
---------------------------------
Two writers shared ONE per-run ``(run_id, owner_id, workspace_id)`` seq space with TWO
algorithms. The app-layer chat writers take ``max(seq)+1`` and RETRY past an
``IntegrityError``, so they always land. The engine's ``_RunEventSink.persist`` used a
fixed in-memory counter and caught ``SQLAlchemyError`` — which ``IntegrityError``
subclasses — so a real uniqueness collision took the branch written for the schema-less
offline harness and the row was silently discarded.

So a stolen seq destroys an engine event IFF the engine's counter actually WALKS onto it.
Gaps alone prove nothing (the steal occupies the seq), which is why this simulates the
allocator rather than looking for holes. Two loss signatures are reported:

  WALKED-ONTO   the counter reached a seq an app writer had taken -> that event was lost
  ORPHAN-CARD   a narrator ``chat_reply:{uuid}`` card whose source uuid has no row. The
                card is written by the always-lands allocator, so it survives its own
                source event and acts as a TOMBSTONE that NAMES what was destroyed.

Usage:
    python3 scripts/audit_lost_run_events.py [--db PATH] [--json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

# App-layer writers that allocate with max(seq)+1 and retry past a collision.
STEAL_EVENT_ID_PREFIXES = ("chat:", "chat-reply:", "chat-usage:", "concierge-proposal")
# The narrator's milestone card. NOTE the discriminator: "chat_reply:" with an UNDERSCORE
# is the narrator (free — the engine jumps its counter past it); "chat-reply:" with a
# HYPHEN is the Concierge (a steal). Getting these two backwards inverts the whole count.
CARD_EVENT_ID_PREFIX = "chat_reply:"

# FIX-240 (commit 88521920, 2026-08-12T18:45:08+02:00) taught the engine sink to
# re-append past a raced seq, so a run created after it cannot lose an event this way.
# Such a run STILL shows the "walked-onto" shape — the steal is real and the engine's
# counter did reach it — but the row landed at max+1 instead of being discarded, so
# nothing was destroyed. Counting those is the single easiest way to overstate the
# damage, and the ONLY reliable discriminator is the run's creation time: the surviving
# rows look structurally identical either way. Verified against run 1ea6d262 (created
# 16:55:50 UTC), whose pipeline_cancelled landed at 248 immediately after the steal at
# 247 — that IS FIX-240 working, observed on production data.
FIX240_LANDED_UTC = "2026-08-12 16:45:08"


def classify_writer(event_id: str, event_type: str) -> str:
    if event_type == "run_resuming":
        return "RESYNC"
    if event_id.startswith(CARD_EVENT_ID_PREFIX):
        return "CARD"
    if any(event_id.startswith(p) for p in STEAL_EVENT_ID_PREFIXES):
        return "STEAL"
    return "ENGINE"


def audit(db_path: str, fix240_utc: str = FIX240_LANDED_UTC) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        runs = {
            r["id"]: dict(r)
            for r in con.execute(
                "SELECT id, type, status, created_at, agent_outputs FROM workflow_runs"
            )
        }
        rows = con.execute(
            "SELECT run_id, owner_id, workspace_id, seq, event_id, type, payload_json "
            "FROM run_events ORDER BY run_id, owner_id, workspace_id, seq"
        ).fetchall()

        by_scope: dict[tuple, list] = defaultdict(list)
        event_ids: dict[str, set] = defaultdict(set)
        by_seq: dict[str, dict] = defaultdict(dict)
        for r in rows:
            by_scope[(r["run_id"], r["owner_id"], r["workspace_id"])].append(r)
            event_ids[r["run_id"]].add(r["event_id"])
            by_seq[r["run_id"]][r["seq"]] = r

        findings: dict[str, list] = defaultdict(list)
        protected = {
            rid for rid, r in runs.items()
            if (r.get("created_at") or "") > fix240_utc
        }

        for (run_id, _owner, _ws), scope_rows in by_scope.items():
            if run_id in protected:
                continue
            writer = {r["seq"]: classify_writer(r["event_id"], r["type"]) for r in scope_rows}
            counter = None
            for r in scope_rows:
                seq, kind = r["seq"], writer[r["seq"]]
                if kind == "RESYNC":
                    # A new drive re-reads max(seq)+1, so steals written between drives
                    # cost nothing. Dropping the counter models that resync.
                    counter = None
                    continue
                if kind == "STEAL":
                    continue
                if kind == "CARD":
                    source = r["event_id"][len(CARD_EVENT_ID_PREFIX):]
                    if not source.startswith("pipeline_start:") and source not in event_ids[run_id]:
                        card = json.loads(r["payload_json"] or "{}")
                        findings[run_id].append({
                            "seq": seq,
                            "signature": "ORPHAN-CARD",
                            "destroyed_type": _type_from_card(card.get("card_kind"), card.get("text")),
                            "evidence": f"card_kind={card.get('card_kind')} text={card.get('text')!r}",
                        })
                    # The engine jumps its counter past a card, so a card absorbs any
                    # steals below it for free.
                    if counter is None or seq + 1 > counter:
                        counter = seq + 1
                    continue
                # ENGINE
                if counter is None:
                    counter = seq + 1
                    continue
                for stolen in range(counter, seq):
                    if writer.get(stolen) != "STEAL":
                        continue
                    findings[run_id].append({
                        "seq": stolen,
                        "signature": "WALKED-ONTO",
                        "destroyed_type": _infer_destroyed_type(by_seq[run_id], stolen),
                        "evidence": f"seq taken by {by_seq[run_id][stolen]['type']}",
                    })
                counter = seq + 1

        # Second-order damage: _persist_resume_output_columns rebuilds
        # workflow_runs.agent_outputs by concatenating agent_chunk payloads from the
        # DURABLE TAIL, so a run that took a resume/reconcile path carries the hole into
        # a persisted column, not just the event log.
        for run_id, items in findings.items():
            for item in items:
                if item["destroyed_type"] != "agent_chunk":
                    continue
                agent = _damaged_agent(by_seq[run_id], item["seq"])
                if agent:
                    item["recovery"] = _measure_hole(con, run_id, agent)

        return {"runs": runs, "findings": dict(findings), "protected": sorted(protected)}
    finally:
        con.close()


def _type_from_card(card_kind: str | None, text: str | None) -> str:
    """An orphan card names its destroyed source: the narrator projects one card per
    generic lifecycle event, so card_kind + text identify the event that was lost."""
    if card_kind == "clarify":
        return "questionnaire_complete"
    if card_kind == "pipeline" and text and "cancel" in text.lower():
        return "pipeline_cancelled"
    if card_kind == "gate":
        return "review_gate_approved"
    return f"unknown(card_kind={card_kind})"


def _infer_destroyed_type(seq_rows: dict, stolen_seq: int) -> str:
    """Infer what the engine was about to emit at the stolen seq from its neighbours.

    Mid-agent is the common case: the engine streams ``agent_chunk`` rows contiguously,
    so a steal landing between two of them destroyed a chunk.

    The gate case needs one extra step and is easy to get wrong. A ``review_gate_ready``
    is ALWAYS followed by its narrator card, so the destroyed ``review_gate_approved``
    sits TWO rows after the ready, not one — the scan must look back past cards. On the
    one damaged gate in this corpus (``fa66227a`` @2181) the shape is
    ``2179 ready | 2180 card | 2181 STOLEN | 2182 agent_start`` while the run's two
    healthy gates both read ``ready | card | review_gate_approved | …`` — independent
    corroboration that the missing row is the approval.
    """
    def _prev_non_card(seq: int):
        for back in range(1, 4):
            row = seq_rows.get(seq - back)
            if row is None:
                return None
            if not row["event_id"].startswith(CARD_EVENT_ID_PREFIX):
                return row
        return None

    before = _prev_non_card(stolen_seq)
    after = seq_rows.get(stolen_seq + 1)
    if before is not None and before["type"] == "review_gate_ready":
        return "review_gate_approved"
    if before is not None and before["type"] == "agent_chunk":
        return "agent_chunk"
    if after is not None and after["type"] == "agent_chunk":
        return "agent_chunk"
    return "unknown"


def _measure_hole(con, run_id: str, agent_id: str) -> str:
    """Measure ONE damaged agent's hole by aligning its surviving chunks against
    ``artifact_refs.content`` — the independent authoritative record of the same text.

    This is what makes "the content is recoverable, the identity is not" a MEASUREMENT
    rather than an assertion: the shortfall is exactly the bytes the destroyed
    ``agent_chunk`` carried, and they are still readable from the artifact.
    """
    replay = 0
    for r in con.execute(
        "SELECT payload_json FROM run_events WHERE run_id=? AND type='agent_chunk'", (run_id,)
    ):
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except (ValueError, TypeError):
            continue
        if payload.get("agent_id") == agent_id:
            replay += len(payload.get("chunk") or "")

    # The LARGEST single artifact row, never the sum: an agent that ran more than once
    # (gate redo / spec revision) has one artifact_refs row PER VERSION, and summing them
    # reports a hole of exactly one whole document. Measured wrong first, then corrected —
    # a 1-character hole came out as 18,718 before this was a max() instead of a sum.
    versions = [len(r["content"] or "") for r in con.execute(
        "SELECT content FROM artifact_refs WHERE run_id=? AND producer_agent=?",
        (run_id, agent_id),
    )]
    if not versions:
        return f"agent {agent_id}: replay={replay} chars (no artifact_refs row to align against)"
    artifact = max(versions)
    nver = f", {len(versions)} versions" if len(versions) > 1 else ""
    hole = artifact - replay
    if hole < 0:
        # The replay spans several versions of a re-run agent; the per-version alignment
        # is the analysis's job, not this audit's. Report honestly rather than guess.
        return (
            f"agent {agent_id}: chunk replay={replay} chars spans multiple runs of the "
            f"agent (largest artifact={artifact}{nver}) — align per version to size the hole"
        )
    return (
        f"agent {agent_id}: chunk replay={replay} vs artifact_refs={artifact} chars{nver} "
        f"-> hole = {hole} char(s), recoverable from the artifact"
    )


def _damaged_agent(seq_rows: dict, stolen_seq: int) -> str | None:
    """The agent whose stream the stolen seq interrupted (read off a neighbouring chunk)."""
    for probe in (stolen_seq - 1, stolen_seq + 1, stolen_seq - 2, stolen_seq + 2):
        row = seq_rows.get(probe)
        if row is None or row["type"] != "agent_chunk":
            continue
        try:
            return json.loads(row["payload_json"] or "{}").get("agent_id")
        except (ValueError, TypeError):
            return None
    return None


def main() -> None:
    default_db = Path(__file__).resolve().parents[1] / "dev.db"
    ap = argparse.ArgumentParser(description="ISS-123 read-only lost-event audit")
    ap.add_argument("--db", default=str(default_db), help="path to the SQLite database")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--fix240-utc", default=FIX240_LANDED_UTC,
                    help="runs created after this UTC timestamp are protected by FIX-240")
    args = ap.parse_args()

    result = audit(args.db, args.fix240_utc)
    runs, findings = result["runs"], result["findings"]

    if args.json:
        print(json.dumps({
            "total_destroyed": sum(len(v) for v in findings.values()),
            "runs_affected": len(findings),
            "by_run": findings,
        }, indent=2))
        return

    by_type: Counter = Counter()
    total = 0
    print("=" * 92)
    print("ISS-123 — engine events destroyed by the pre-FIX-240 seq collision (READ-ONLY)")
    print("=" * 92)
    for run_id in sorted(findings, key=lambda r: runs[r]["created_at"]):
        run, items = runs[run_id], findings[run_id]
        total += len(items)
        print(f"\n{run_id[:8]}  {run['type']:<14} status={run['status']:<10} destroyed={len(items)}")
        for i in items:
            by_type[i["destroyed_type"]] += 1
            print(f"     seq {i['seq']:>6}  {i['signature']:<12} {i['destroyed_type']:<24} {i['evidence']}")
            if i.get("recovery"):
                print(f"                    {i['recovery']}")

    print("\n" + "=" * 92)
    print(f"TOTAL destroyed engine events: {total}  across {len(findings)} run(s)")
    for t, n in by_type.most_common():
        print(f"    {t:<26} {n}")
    print("=" * 92)
    print("A run whose durable log has no terminal event renders correctly anyway since")
    print("ISS-126; a run short an agent_chunk replays a transcript truncated by that many")
    print("characters. NOTHING here is repaired, and run_events must never be back-filled.")


if __name__ == "__main__":
    main()
