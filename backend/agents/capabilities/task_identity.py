"""agents/capabilities/task_identity.py — RESUME-14 content-addressed task identity.

THE single home of the task-identity primitives. A ``task_key`` is

    sha256(upstream_context_hash · normalized_task_content · occurrence_ordinal)

which is reorder-safe, insert-safe, duplicate-text-safe, and upstream-aware: a
reorder leaves the key unchanged (the heading ordinal is stripped from the
content), an edit rotates it (title/body/forward-field sensitive), a duplicate is
disambiguated by its 0-based occurrence ordinal, and a spec/plan edit rotates the
``upstream_context_hash`` — which rotates every dependent key. This is the identity
substrate the resume cursor and the reconciler key on (Phase 46 cursor + Phase 48
reconciler).

The upstream-context-hash itself is NOT computed here — it is factored ONCE out of
``ExecutionEngine._compute_step_input_hash`` into ``_compute_upstream_context_hash``
(INV-12: one home, reused by ``input_hash`` AND the task key) and threaded in by the
strategy via ``runner.upstream_context_hash(step)``. This module only consumes the
digest string.

Scope guards:
  - PURE functions only. Imports the canonical typed ``Task`` plus stdlib
    (``hashlib``, ``json``, ``re``, ``unicodedata``, ``logging``, ``__future__``).
  - MUST NOT import ``app.*``, ``agents.execution_engine``, or ``agents.workflows``
    control flow (only the pure-data ``agents.workflows.plan.Task``) — the
    import-linter contract "agents.capabilities must not import the execution
    kernel or the web layer". The kernel/strategies import THIS module, never the
    reverse.
  - Deterministic cross-restart: canonical JSON (``sort_keys=True``,
    ``separators=(",",":")``), ``sha256``, NFC — NO ``hash()`` (salted per process),
    NO timestamp, NO uuid, NO unsorted collection (Pitfall 1 / 12-era D-11).
  - Zero workflow/agent-name literals (SC-001 / INV-1): keys on generic parsed
    ``Task`` content only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata

from agents.workflows.plan import Task

logger = logging.getLogger(__name__)

# The leading ``## Task N:`` ordinal token on the first line of a heading-parser
# ``Task.body`` (heading_tasks ``_extract_task_block`` keeps the header line). The
# ordinal N MUST be stripped so reordering a task does not rotate its key; the title
# text after the colon is KEPT (it is meaningful content). ``\b`` guards a bare
# ``## Task 3`` with no colon.
_HEADING_ORDINAL_RE = re.compile(r"^##\s+Task\s+\d+\b:?", re.IGNORECASE)

# Collapse every run of whitespace to a single space (after newline normalization).
_WS_RE = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """NFC-normalize, fold ``\\r\\n``/``\\r`` → ``\\n``, collapse whitespace, strip.

    No locale-sensitive casefold and no ``hash()`` — deterministic across processes.
    """
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _WS_RE.sub(" ", text).strip()


def _strip_leading_ordinal(body: str) -> str:
    """Strip a leading ``## Task N:`` ordinal token from the FIRST line of ``body``.

    Reorder-safety hinge (Pitfall 2): heading ``Task.body`` embeds ``## Task N:`` so a
    reorder changes ``body`` verbatim; removing the ordinal token (keeping the title
    after the colon) makes the content reorder-independent. Non-heading bodies (json
    tasks) are unaffected — the pattern anchors at ``^`` on the first line only.
    """
    if not body:
        return body
    lines = body.split("\n", 1)
    lines[0] = _HEADING_ORDINAL_RE.sub("", lines[0], count=1)
    return "\n".join(lines)


def normalize_task_content(task: Task) -> str:
    """Return the reorder-stable, edit-sensitive canonical content of ``task``.

    Combines the task's OWN text (title + ordinal-stripped body) with its forward
    scheduling surface (``targets``/``depends_on``/``conflict_keys``, each sorted) so
    two same-titled wave workers with different targets do not collide (RESEARCH
    §Normalization). Heading tasks carry empty forward fields → those dimensions are
    constant and reorder-stability is preserved; json wave tasks gain the extra
    disambiguation. The result is a canonical JSON string (``sort_keys``) — stable
    across processes, sensitive to any content edit.
    """
    payload = {
        "t": _normalize_text(getattr(task, "title", "") or ""),
        "b": _normalize_text(_strip_leading_ordinal(getattr(task, "body", "") or "")),
        "targets": sorted(str(x) for x in (getattr(task, "targets", []) or [])),
        "depends_on": sorted(str(x) for x in (getattr(task, "depends_on", []) or [])),
        "conflict_keys": sorted(str(x) for x in (getattr(task, "conflict_keys", []) or [])),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def occurrence_ordinals(tasks: list[Task]) -> list[int]:
    """Return, per index, the 0-based count of PRIOR tasks with identical content.

    Left-to-right over the CURRENT list: two identical "Fix styling" tasks yield
    ordinals ``0`` and ``1`` (WR-05 duplicate-text safety). Used ONLY to tie-break
    identical text — position is never part of identity otherwise.
    """
    seen: dict[str, int] = {}
    ordinals: list[int] = []
    for task in tasks:
        content = normalize_task_content(task)
        n = seen.get(content, 0)
        ordinals.append(n)
        seen[content] = n + 1
    return ordinals


def compute_task_key(
    upstream_context_hash: str,
    normalized_content: str,
    ordinal: int,
) -> str:
    """Return the 64-char hex ``task_key`` for the (upstream · content · ordinal) triple.

    Canonical-JSON sha256 (mirrors ``_compute_step_input_hash`` discipline): sorted
    keys, compact separators, ``sha256().hexdigest()``. Deterministic across
    processes (no ``hash()``/timestamp/uuid). Any of the three components changing
    yields a different key; a produced key can never equal a legacy positional id
    (length 64 + hex charset), which is the backward-compat fail-safe (an unmappable
    legacy row simply re-runs).
    """
    canonical = json.dumps(
        {"u": upstream_context_hash, "c": normalized_content, "o": ordinal},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def common_prefix_length(
    current_keys: list[str], completed_ordered: list[str]
) -> int:
    """Return the length ``p`` of the longest POSITIONAL common prefix of the lists.

    RESUME-16 cumulative reconcile (THE single home of the common-prefix rule, called
    by BOTH the task_loop skip AND the engine boundary reconciler). For a cumulative
    single-file build each task EDITS the same evolving file, so task k's basis is
    "all of 1..k-1": a completed key is only safe to SKIP while it MATCHES the current
    key at the SAME position. The FIRST position where they differ (a deleted, edited,
    inserted, or reordered task) invalidates that task AND every task after it (their
    basis changed) — so ``p`` is the count of leading current tasks to skip; everything
    at index ``>= p`` re-runs (Pitfall 3 — never set-membership for task_loop).

    A first-position divergence (first task edited/deleted, or a task inserted at head)
    yields ``0`` → run every current task from a clean/empty basis; callers must NEVER
    index ``[p-1]`` when ``p == 0`` (the negative-index wrong-restore trap). Waves use
    per-key set-membership, NOT this rule.
    """
    p = 0
    for cur, done in zip(current_keys, completed_ordered):
        if cur != done:
            break
        p += 1
    return p
