"""Run-history CRUD API endpoints (relocated from /api/workflows — D-02).

This router owns the WorkflowRun read/delete/export surface that previously
lived under ``/api/workflows``. The move (Phase 4 / D-02) reclaims
``/api/workflows`` for manifest-derived definitions (see ``workflows.py``) and
establishes ``/api/runs`` as the run-history sub-resource home the §22 plan
envisions (Phase 5 lands ``/api/runs/{id}/artifacts|events`` here).

The relocation is a clean break with NO legacy redirect aliases: RESEARCH § "D-02
— API-Key Public Surface Check (RESOLVED)" confirmed these routes are JWT-only
(``Depends(get_current_user)``) with no external API-key consumer, so the 10
frontend refs are repointed atomically (Plan 04-05 Task 3).

Security carried over VERBATIM from the original handlers:
  * IDOR (ASVS V4 / T-04-12): every query that reads a run keeps the per-user
    ``.filter(WorkflowRun.user_id == current_user.id)`` ownership filter, so a
    cross-owner request resolves to 404, never another user's data.
  * HTTP response splitting (T-04-14): the export-pptx filename is sanitized
    with ``re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]`` exactly as before.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.artifact_ref import ArtifactRef
from app.models.database import get_db
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.hook_runs import HookRun
from app.models.run_capabilities import RunCapabilities
from app.models.run_event import RunEvent
from app.models.subagent_run import SubagentRun
from app.models.user import User
from app.models.validation_results import ValidationResult
from app.models.wave_run import WaveRun
from app.models.workflow import WorkflowRun
from app.models.workflow_clarification import WorkflowClarification

router = APIRouter(prefix="/api/runs", tags=["runs"])


# --- Request/Response Schemas ---


class ExportPptxRequest(BaseModel):
    """Request body for POST /api/runs/export-pptx.

    All four fields are optional, but at least one of ``workflow_id``,
    ``js_code`` or ``html`` MUST be present (enforced inside the handler
    rather than via Pydantic, since the field that matters depends on the
    extraction strategy chosen).

    Caps exist to bound subprocess input and prevent trivial DoS via huge
    payloads — they are intentionally generous (a real PptxGenJS function
    is rarely > 100 KB) and not a substitute for the sandboxing work
    tracked separately under the pptx_export hardening item.
    """

    workflow_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="UUID of a WorkflowRun belonging to the caller; agent output is fetched server-side.",
    )
    js_code: Optional[str] = Field(
        default=None,
        max_length=512_000,
        description="Raw PptxGenJS JavaScript (the generatePresentation function body).",
    )
    html: Optional[str] = Field(
        default=None,
        max_length=2_000_000,
        description="An HTML preview containing a generatePresentation() function in a <script> block.",
    )
    title: str = Field(
        default="Presentation",
        max_length=120,
        description="Filename hint for the Content-Disposition response header.",
    )


class WorkflowRunResponse(BaseModel):
    """Workflow run data returned in API responses."""

    id: str
    title: str
    type: str
    status: str
    input: str
    output: Optional[str] = None
    agent_outputs: Optional[str] = None
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    token_usage: Optional[str] = None
    # CWF-002 (fix c): the effective model the run used (WorkflowRun.model_id, migration
    # 0014 column — now written by the launch driver). Auto-materialized into BOTH the
    # list (summary) and detail responses by _run_response's model_fields getattr loop.
    model_id: Optional[str] = None
    # UXFIX-02 (22-03 / D-19): the persisted declared/resolved deliverable shape
    # so history-reopen drives the deliverable mimetype from the persisted value
    # (legacy rows NULL → FE deriveDeliverableMimetype heuristic fallback, parity).
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    # Workstream A (POR §4.2 / D-06,D-07): revision-family read surface.
    #   * parent_run_id — the verbatim self-FK column (resolved by from_attributes);
    #     None for a standalone run, else the id of the run this one revises.
    #   * root_run_id — server-computed (NOT an ORM column): the last OWNED
    #     ancestor reached by walking parent_run_id up the chain. A standalone run
    #     roots to its own id; a foreign/missing parent terminates the walk so no
    #     foreign run is ever named. Required (contract-strong) — injected by
    #     _run_response since from_attributes cannot supply a computed field.
    parent_run_id: Optional[str] = None
    root_run_id: str
    # KAN-130: expose the chaining indicator so the frontend can show "(Chained)"
    # in the Jump Back In section. source_run_id is set when a run was launched
    # by chaining from a prior run's output. The column already exists (migration
    # 0014 forward field) — no migration needed; from_attributes resolves it.
    source_run_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    # KAN-113: SQLite returns timezone-naive datetimes even though we write UTC.
    # Pydantic v2 serialises a naive datetime without a +00:00 suffix, so
    # JavaScript Date.parse() treats it as local time → wrong "Nh ago" display.
    # Promote to UTC-aware before ISO-formatting (matches _coerce_to_aware_utc
    # in dependencies.py — same pattern, applied at the serialisation boundary).
    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


class WorkflowRunListResponse(BaseModel):
    """Slim run data for the history list endpoint (KAN-131).

    Excludes the heavy ``output``, ``agent_outputs``, and ``input`` fields that
    are only needed when a run is opened. Omitting them reduces the list payload
    from ~2.8MB to <50KB for 50 rows — a ~50x reduction.
    The full ``WorkflowRunResponse`` is returned by ``GET /api/runs/{id}``.
    """

    id: str
    title: str
    type: str
    status: str
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    token_usage: Optional[str] = None
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    parent_run_id: Optional[str] = None
    root_run_id: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


# ---------------------------------------------------------------------------
# Workstream A — revision-family read helpers (POR §4.2 + §4.3, app-layer only).
# ---------------------------------------------------------------------------

# Sentinel for an ancestor id that is missing OR owned by another user — the
# owned walk terminates here (root = the last OWNED ancestor, POR §3.2). Kept
# distinct from None (which means "no parent") so the family walk never leaks a
# foreign run into a root/family response (threat T-A-03).
_FOREIGN_ANCESTOR = object()


def _compute_root_ids(db: Session, user_id: str, runs: list) -> dict[str, str]:
    """Return ``{run_id: root_run_id}`` for every run in ``runs`` via a memoized
    in-Python owned-ancestor walk with batched parent fetches.

    Chosen over a recursive CTE for SQLite (tests) + Postgres (prod) portability
    — the POR grants implementation freedom here. ``root_run_id`` is the last
    OWNED ancestor reachable by following ``parent_run_id`` up the chain: a NULL
    parent, a missing parent, or a parent owned by another user all terminate
    the walk (POR §3.2), so a foreign link never leaks foreign run metadata.

    Latency invariant: a page whose rows ALL have NULL parent_run_id issues ZERO
    additional queries (the frontier is empty on the first pass); otherwise one
    extra batched query per chain-depth level. Cycle guard: each per-run walk
    carries a visited set so a corrupt cyclic chain terminates at the revisited
    node instead of looping forever (threat T-A-04).
    """
    # parent_of[id] -> parent id (str), None (no parent), or _FOREIGN_ANCESTOR
    # (missing / not owned → walk terminator). Seed from the page rows.
    parent_of: dict[str, object] = {r.id: r.parent_run_id for r in runs}

    # Iteratively resolve unknown ancestors, OWNED-only, one depth-level per pass.
    while True:
        frontier = {
            pid
            for pid in parent_of.values()
            if isinstance(pid, str) and pid not in parent_of
        }
        if not frontier:
            break
        rows = (
            db.query(WorkflowRun.id, WorkflowRun.parent_run_id)
            .filter(
                WorkflowRun.id.in_(frontier),
                WorkflowRun.user_id == user_id,
            )
            .all()
        )
        fetched = {rid: ppid for rid, ppid in rows}
        for pid in frontier:
            # A frontier id the OWNED fetch did not return is missing or owned by
            # another user → mark as the walk terminator (never re-queried).
            parent_of[pid] = fetched.get(pid, _FOREIGN_ANCESTOR)

    # Resolve each run's root by walking parent_of, memoizing across the page.
    root_cache: dict[str, str] = {}

    def _root_of(start: str) -> str:
        chain: list[str] = []
        cur = start
        visited: set[str] = set()
        while True:
            if cur in root_cache:
                resolved = root_cache[cur]
                break
            if cur in visited:
                # Cycle — terminate at the current node (its own root).
                resolved = cur
                break
            visited.add(cur)
            parent = parent_of.get(cur, _FOREIGN_ANCESTOR)
            # Step ONLY into an OWNED parent. A None parent (no parent), the
            # foreign sentinel, or a parent id that itself resolves to a
            # foreign/missing node all terminate the walk — cur is the last owned
            # ancestor, i.e. the root. (parent_of[x] is a real str/None iff x is
            # owned; it is the sentinel iff x is foreign/missing.)
            if (
                not isinstance(parent, str)
                or parent_of.get(parent, _FOREIGN_ANCESTOR) is _FOREIGN_ANCESTOR
            ):
                resolved = cur
                break
            chain.append(cur)
            cur = parent
        root_cache[cur] = resolved
        for node in chain:
            root_cache[node] = resolved
        return resolved

    return {r.id: _root_of(r.id) for r in runs}


def _run_response(run, root_id: str) -> WorkflowRunResponse:
    """Build a ``WorkflowRunResponse`` injecting the server-computed root_run_id.

    ``from_attributes`` cannot supply ``root_run_id`` (it is not an ORM column),
    so every OTHER field is materialized from the row by iterating
    ``model_fields`` — which auto-tracks future field additions with no
    hand-maintained list — and ``root_run_id`` is injected explicitly, keeping it
    a required ``str`` (contract-strong).
    """
    kwargs = {
        name: getattr(run, name)
        for name in WorkflowRunResponse.model_fields
        if name != "root_run_id"
    }
    kwargs["root_run_id"] = root_id
    return WorkflowRunResponse(**kwargs)


def _run_list_response(run, root_id: str) -> WorkflowRunListResponse:
    """Build a slim ``WorkflowRunListResponse`` for the history list (KAN-131).

    Identical pattern to ``_run_response`` but uses the slim schema that
    excludes ``output``, ``agent_outputs``, and ``input`` — reducing the list
    payload from ~2.8MB to <50KB for 50 rows.
    """
    kwargs = {
        name: getattr(run, name)
        for name in WorkflowRunListResponse.model_fields
        if name != "root_run_id"
    }
    kwargs["root_run_id"] = root_id
    return WorkflowRunListResponse(**kwargs)


# --- Endpoints ---


@router.get("", response_model=list[WorkflowRunListResponse])
def list_runs(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    type: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """List workflow runs for the authenticated user (slim — no output/agent_outputs).

    Ordered by created_at descending (most recent first).
    Returns ``X-Total-Count`` header with the total matching run count.
    Heavy fields (output, agent_outputs, input) are excluded — fetch the full
    run via ``GET /api/runs/{id}`` when a specific run is opened.
    """
    # KAN-131: only load the columns the list schema needs — skip the heavy
    # Text columns (output, agent_outputs, input) entirely so SQLite/Postgres
    # never reads them off disk. This is the dominant performance win.
    _LIST_COLS = [
        WorkflowRun.id,
        WorkflowRun.title,
        WorkflowRun.type,
        WorkflowRun.status,
        WorkflowRun.agent_count,
        WorkflowRun.duration,
        WorkflowRun.error,
        WorkflowRun.token_usage,
        WorkflowRun.deliverable_mimetype,
        WorkflowRun.deliverable_filename,
        WorkflowRun.parent_run_id,
        WorkflowRun.user_id,
        WorkflowRun.created_at,
        WorkflowRun.completed_at,
    ]
    query = (
        db.query(*_LIST_COLS)
        .filter(WorkflowRun.user_id == current_user.id)
    )
    
    if type:
        query = query.filter(WorkflowRun.type == type)
    if status_filter:
        query = query.filter(WorkflowRun.status == status_filter)
    
    # Count before applying limit/offset so the total reflects filters.
    # Uses the same WHERE clause as the page query — no extra round trip on a
    # cold query; SQLite/Postgres both plan it as a single index scan.
    total = query.count()
    response.headers["X-Total-Count"] = str(total)

    runs = (
        query
        .order_by(WorkflowRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # Compute the owned root for the whole page once (batched ancestor walk); a
    # NULL-parent page issues zero extra queries (POR §4.2 latency invariant).
    # Note: column-select rows support attribute access by column name, so
    # _compute_root_ids and _run_list_response work identically to ORM objects.
    roots = _compute_root_ids(db, current_user.id, runs)
    return [_run_list_response(r, roots[r.id]) for r in runs]


@router.post("/export-pptx")
def export_pptx(
    request: ExportPptxRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a .pptx file from Agent 3's PptxGenJS code.

    Tries to get the code from:
    1. workflow_id → agent_outputs (the ppt-code-generator agent's output)
    2. js_code field directly
    3. html field → extract generatePresentation() from HTML

    Returns: .pptx binary download.
    """
    from fastapi.responses import Response
    from app.services.pptx_export import generate_pptx_from_code

    js_code = request.js_code or ""
    html_content = request.html or ""
    workflow_id = request.workflow_id or ""
    title = request.title

    # The set of agent IDs whose `output` is canonical PptxGenJS source. The
    # previous substring scan (`"code" in aid or "generator" in aid or
    # "ppt-code" in aid`) had four false positives (`app-code-generator`,
    # `barcode-extractor`, `prototype-generator`, `code-reviewer`) — a user
    # who had run a non-PPT pipeline in the same workflow_id could silently
    # download a deck built from the wrong agent's output. Exact match
    # against the registered IDs eliminates that class of mistake.
    _PPT_CODE_AGENT_IDS = {"ppt-code-generator"}

    # Strategy 1: Get Agent 3 output from workflow DB
    if not js_code and workflow_id:
        wr = db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == current_user.id
        ).first()
        if wr and wr.agent_outputs:
            try:
                outputs = json.loads(wr.agent_outputs)
                for agent in outputs:
                    if agent.get("agent_id", "") in _PPT_CODE_AGENT_IDS:
                        js_code = agent.get("output", "")
                        break
            except Exception:
                pass

    # Strategy 2: Extract from HTML
    if not js_code and html_content:
        # Find generatePresentation function in script tags
        scripts = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html_content)
        for script in scripts:
            m = re.search(r'((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)', script)
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(m.end() - 1, len(script)):
                    if script[i] == '{':
                        depth += 1
                    elif script[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = script[start:end]
                    break

        # Also try full HTML search
        if not js_code:
            m = re.search(r'((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)', html_content)
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(start, len(html_content)):
                    if html_content[i] == '{':
                        depth += 1
                    elif html_content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = html_content[start:end]

    if not js_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not find PptxGenJS code. Try re-running the pipeline.",
        )

    try:
        pptx_bytes = generate_pptx_from_code(js_code, title=title)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PPTX: {str(e)[:200]}",
        )

    # Sanitize the filename to ASCII alphanumerics + `_-.` only. The previous
    # `title.replace(' ', '_')[:40]` did NOT strip CR/LF/control chars or
    # double-quote, which let a maliciously-crafted title smuggle additional
    # headers (HTTP response splitting). The Pydantic max_length on `title`
    # bounds the size; this re.sub bounds the alphabet.
    safe_title = re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40] or "Presentation"
    filename = f"{safe_title}.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{workflow_id}", response_model=WorkflowRunResponse)
def get_run(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific workflow run by ID.

    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    roots = _compute_root_ids(db, current_user.id, [workflow_run])
    return _run_response(workflow_run, roots[workflow_run.id])


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_run(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow run and all its child rows.

    Cleans up all 9 child tables that FK into workflow_runs before deleting
    the parent row — required because PRAGMA foreign_keys=ON (database.py)
    enforces FK integrity and none of the child tables declare ON DELETE CASCADE.

    Also handles the self-referential parent_run_id FK: child WorkflowRun rows
    (revision chains) have their parent_run_id nulled before the parent is deleted.

    Returns 204 No Content on success.
    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # ── Delete child rows in dependency order before removing the parent ──────
    # All 9 audit tables FK into workflow_runs.id with no ON DELETE CASCADE.
    # Column names differ per table — confirmed from each model file.
    db.query(RunEvent).filter(RunEvent.run_id == workflow_id).delete(synchronize_session=False)
    db.query(ArtifactRef).filter(ArtifactRef.run_id == workflow_id).delete(synchronize_session=False)
    db.query(WorkflowClarification).filter(WorkflowClarification.workflow_run_id == workflow_id).delete(synchronize_session=False)
    db.query(GateEvent).filter(GateEvent.run_id == workflow_id).delete(synchronize_session=False)
    db.query(HookRun).filter(HookRun.run_id == workflow_id).delete(synchronize_session=False)
    db.query(ExecRun).filter(ExecRun.run_id == workflow_id).delete(synchronize_session=False)
    db.query(RunCapabilities).filter(RunCapabilities.run_id == workflow_id).delete(synchronize_session=False)
    db.query(ValidationResult).filter(ValidationResult.run_id == workflow_id).delete(synchronize_session=False)
    db.query(SubagentRun).filter(SubagentRun.parent_run_id == workflow_id).delete(synchronize_session=False)
    db.query(WaveRun).filter(WaveRun.run_id == workflow_id).delete(synchronize_session=False)

    # ── Self-referential FK: null out parent_run_id on any child revision runs ─
    # Deleting the parent while revision children point to it via parent_run_id
    # would also violate the self-referential FK. Null the reference instead of
    # cascade-deleting the child runs (preserves the revision run history).
    db.query(WorkflowRun).filter(WorkflowRun.parent_run_id == workflow_id).update(
        {WorkflowRun.parent_run_id: None}, synchronize_session=False
    )

    db.delete(workflow_run)
    db.commit()

    return None


# ---------------------------------------------------------------------------
# Chain context endpoint — extracts structured text from a completed run
# for use as context in the next chained pipeline.
# ---------------------------------------------------------------------------

class ChainContextResponse(BaseModel):
    """Structured context extracted from a completed workflow run."""
    workflow_id: str
    pipeline_type: str
    title: str
    brief: str                          # Original user input
    structured_summary: str             # Extracted text content (not HTML)
    agent_summaries: list[dict]         # Per-agent key outputs
    context_block: str                  # Ready-to-inject context string


def _extract_chain_context(workflow_run: WorkflowRun) -> ChainContextResponse:
    """Extract structured, chain-ready context from a completed WorkflowRun.

    For each pipeline type, extracts the most useful text content:
    - od_ppt / ppt: extracts the slide spec JSON from the brief-analyst output
    - user_stories: extracts the backlog text from the compiler output
    - od_prototype / prototype: extracts the component spec from the analyst
    - app_builder: extracts the architecture summary from the system-design agent
    - mulesoft / dotnet: extracts the migration plan from the inventory agent
    - custom: extracts the final output text
    """

    pipeline_type = workflow_run.type
    brief = workflow_run.input or ""
    title = workflow_run.title or ""

    # KAN-116 (Bug 3): strip === ... === marker text from title and brief before
    # embedding them in the context_block. If a prior run had polluted title/input
    # (stored before FIX-087), the nested markers would break parseRunInput on the FE.
    # Generic regex — no pipeline-name literals (SC-001/INV-1).
    import re as _re_ctx
    _marker_re = _re_ctx.compile(r"===.*?===", _re_ctx.DOTALL)

    def _clean_for_context(text: str) -> str:
        """Strip === ... === blocks and return the first clean line."""
        if "===" not in text:
            return text
        # For title: extract revision instruction or brief via the same logic as _clean_run_title
        rev_match = _re_ctx.search(r"===\s*REVISION REQUEST\s*===\s*(.*?)\s*(?:===|$)", text, _re_ctx.DOTALL)
        if rev_match:
            return rev_match.group(1).split("\n")[0].strip()
        # Strip all === ... === blocks and return first non-empty line
        stripped = _marker_re.sub("", text).strip()
        return stripped.split("\n")[0].strip() if stripped else text.split("\n")[0].strip()

    title = _clean_for_context(title)
    # For brief, just take the first clean line before any context block
    brief_first_line = brief.split("\n")[0].strip()
    if "===" not in brief_first_line:
        brief = brief_first_line  # use clean first line as the brief preview
    else:
        brief = _clean_for_context(brief)

    # Parse agent_outputs JSON array
    agent_outputs: list[dict] = []
    if workflow_run.agent_outputs:
        try:
            agent_outputs = json.loads(workflow_run.agent_outputs)
        except Exception:
            pass

    # ── Pipeline-specific extraction ──────────────────────────────────────
    agent_summaries: list[dict] = []
    structured_summary = ""

    # Helper: find agent output by ID
    def get_agent_output(agent_id: str) -> str:
        for a in agent_outputs:
            if a.get("agent_id") == agent_id:
                return a.get("output", "")
        return ""

    # Helper: extract <spec>...</spec> JSON from text
    def extract_spec(text: str) -> str:
        m = re.search(r"<spec>([\s\S]*?)</spec>", text)
        if m:
            try:
                spec = json.loads(m.group(1))
                # Format as readable text
                lines = [f"Title: {spec.get('title', '')}"]
                if spec.get("audience"):
                    lines.append(f"Audience: {spec['audience']}")
                if spec.get("tone"):
                    lines.append(f"Tone: {spec['tone']}")
                if spec.get("theme_choice"):
                    lines.append(f"Theme: {spec['theme_choice']}")
                slides = spec.get("slides", [])
                if slides:
                    lines.append(f"\nSlide Plan ({len(slides)} slides):")
                    for s in slides:
                        lines.append(f"  Slide {s.get('index', '?')}: {s.get('title', '')} [{s.get('type', '')}]")
                        if s.get("content"):
                            lines.append(f"    Content: {str(s['content'])[:200]}")
                return "\n".join(lines)
            except Exception:
                return m.group(1)[:2000]
        return ""

    if pipeline_type in ("ppt", "ppt_revision"):
        # Extract slide spec from brief-analyst
        analyst_output = get_agent_output("ppt-brief-analyst")
        spec_text = extract_spec(analyst_output)
        if spec_text:
            structured_summary = f"Presentation Slide Plan:\n{spec_text}"
            agent_summaries.append({"agent": "Presentation Strategist", "summary": spec_text[:500]})
        elif analyst_output:
            structured_summary = analyst_output[:3000]
            agent_summaries.append({"agent": "Presentation Strategist", "summary": analyst_output[:500]})

    elif pipeline_type in ("user_stories", "user_stories_revision"):
        # Extract from backlog compiler (last agent)
        compiler_output = get_agent_output("backlog-compiler")
        if not compiler_output:
            # Fall back to final output
            compiler_output = workflow_run.output or ""
        if compiler_output:
            structured_summary = compiler_output[:4000]
            agent_summaries.append({"agent": "Backlog Compiler", "summary": compiler_output[:500]})

    elif pipeline_type in ("od_prototype", "prototype", "prototype_revision"):
        # The spec writer (first agent) emits a Markdown spec wrapped in
        # <spec>...</spec>. Read THAT — not the HTML deliverable, and not the
        # retired "requirements-analyst" agent which isn't in this pipeline
        # (the old lookup always returned "" → empty chain context). od_prototype
        # resolves to the same prototype agents, so the IDs match for both.
        # For prototype_revision, the revision agent doesn't have a spec writer —
        # use the revision instruction extracted from the run's input instead.
        spec_output = get_agent_output("prototype-specify") or get_agent_output("prototype-plan")
        if spec_output:
            m = re.search(r"<spec>([\s\S]*?)</spec>", spec_output)
            spec_text = (m.group(1).strip() if m else spec_output)
            structured_summary = f"Prototype Specification:\n{spec_text[:3500]}"
            agent_summaries.append({"agent": "Spec Writer", "summary": spec_text[:500]})
        elif pipeline_type == "prototype_revision":
            # Extract the revision instruction from the run's input field
            # (format: "=== EXISTING PROTOTYPE HTML ===\n...\n=== REVISION REQUEST ===\n{instruction}\n=== END REQUEST ===")
            import re as _re_local
            rev_match = _re_local.search(
                r"===\s*REVISION REQUEST\s*===\s*\n(.*?)\n===\s*END REQUEST\s*===",
                workflow_run.input or "",
                _re_local.DOTALL,
            )
            if rev_match:
                instruction = rev_match.group(1).strip()
                structured_summary = f"Prototype Revision: {instruction}"
                agent_summaries.append({"agent": "Revision Specialist", "summary": instruction[:500]})

    elif pipeline_type in ("app_builder", "app_builder_revision"):
        # Extract from system design agent
        design_output = get_agent_output("app-system-design")
        stories_output = get_agent_output("app-user-stories")
        parts = []
        if stories_output:
            parts.append(f"User Stories:\n{stories_output[:1500]}")
            agent_summaries.append({"agent": "App User Stories", "summary": stories_output[:300]})
        if design_output:
            parts.append(f"System Design:\n{design_output[:1500]}")
            agent_summaries.append({"agent": "System Design", "summary": design_output[:300]})
        structured_summary = "\n\n".join(parts)

    elif pipeline_type in ("mulesoft_to_springboot",):
        inventory_output = get_agent_output("mulesoft-inventory")
        decomp_output = get_agent_output("mulesoft-decomposition")
        parts = []
        if inventory_output:
            parts.append(f"Mulesoft Inventory:\n{inventory_output[:2000]}")
        if decomp_output:
            parts.append(f"Migration Decomposition:\n{decomp_output[:2000]}")
        structured_summary = "\n\n".join(parts)

    elif pipeline_type in ("dotnet_to_azure",):
        inventory_output = get_agent_output("dotnet-inventory")
        mapping_output = get_agent_output("dotnet-azure-target-mapping")
        parts = []
        if inventory_output:
            parts.append(f".NET Inventory:\n{inventory_output[:2000]}")
        if mapping_output:
            parts.append(f"Azure Target Mapping:\n{mapping_output[:2000]}")
        structured_summary = "\n\n".join(parts)

    else:
        # Generic: use final output
        structured_summary = (workflow_run.output or "")[:3000]

    # Fallback: if no structured summary, use the final output
    if not structured_summary and workflow_run.output:
        output = workflow_run.output
        # Skip HTML artifacts
        if not re.search(r"<!DOCTYPE|<html", output, re.IGNORECASE):
            structured_summary = output[:3000]

    # Build the ready-to-inject context block
    context_block = ""
    if structured_summary:
        context_block = (
            f"=== CONTEXT FROM PREVIOUS PIPELINE ({pipeline_type}) ===\n"
            f"Title: {title}\n"
            f"Original Brief: {brief[:200]}\n\n"
            f"{structured_summary}\n"
            f"=== END PREVIOUS CONTEXT ==="
        )

    return ChainContextResponse(
        workflow_id=str(workflow_run.id),
        pipeline_type=pipeline_type,
        title=title,
        brief=brief,
        structured_summary=structured_summary,
        agent_summaries=agent_summaries,
        context_block=context_block,
    )


@router.get("/{workflow_id}/chain-context", response_model=ChainContextResponse)
def get_chain_context(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extract structured chain context from a completed workflow run.

    Returns the key text content from the run's agent outputs, formatted
    as a ready-to-inject context block for the next chained pipeline.
    Only returns context for completed runs owned by the current user.

    For *_revision pipeline types (od_ppt_revision, ppt_revision, etc.) the
    revision run itself has no brief-analyst / spec-writer output — those agents
    run only on the original pipeline.  We therefore walk up one level to the
    parent run and extract its context instead, preserving the slide-plan /
    spec structure the chained pipeline needs.  The revision instruction from
    the *_revision run's input is appended as additional context so the
    downstream pipeline knows what changed.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == current_user.id,
        )
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # KAN-137: for *_revision pipeline types, extract context from the ROOT
    # non-revision ancestor (the original pipeline). A revision of a revision
    # (v1 → v2 → v3) has a parent that is itself a *_revision run — walk up
    # the chain until we reach a non-revision base run. Each revision run in
    # the chain has no brief-analyst / spec-writer output, so only the root
    # has the structural context the chained pipeline needs.
    # Generic suffix check (SC-001/INV-1 — no pipeline-name literals).
    source_run = workflow_run
    revision_instruction: str | None = None
    if workflow_run.type.endswith("_revision") and workflow_run.parent_run_id:
        # Walk up the revision chain to find the root non-revision ancestor.
        # Cap at 20 hops to prevent an infinite loop on corrupted data.
        candidate = workflow_run
        for _ in range(20):
            if not candidate.type.endswith("_revision") or not candidate.parent_run_id:
                break
            parent_run = (
                db.query(WorkflowRun)
                .filter(
                    WorkflowRun.id == candidate.parent_run_id,
                    WorkflowRun.user_id == current_user.id,
                )
                .first()
            )
            if not parent_run:
                break
            candidate = parent_run
        if candidate is not workflow_run:
            source_run = candidate
            # Extract the revision instruction from the MOST RECENT *_revision
            # run's input so the context_block includes "what was changed".
            import re as _re_rev
            rev_match = _re_rev.search(
                r"===\s*REVISION REQUEST\s*===\s*(.*?)\s*(?:===|$)",
                workflow_run.input or "",
                _re_rev.DOTALL,
            )
            if rev_match:
                revision_instruction = rev_match.group(1).split("\n")[0].strip()
            else:
                revision_instruction = workflow_run.title or None

    ctx = _extract_chain_context(source_run)

    # Append the revision instruction to the context_block so the chained
    # pipeline knows what the user changed in the revision (additional signal
    # without replacing the parent's structural context).
    if revision_instruction and ctx.context_block:
        ctx = ChainContextResponse(
            workflow_id=ctx.workflow_id,
            pipeline_type=ctx.pipeline_type,
            title=ctx.title,
            brief=ctx.brief,
            structured_summary=ctx.structured_summary,
            agent_summaries=ctx.agent_summaries,
            context_block=(
                ctx.context_block.rstrip("=").rstrip()
                + f"\nLatest Revision: {revision_instruction}\n"
                + "=== END PREVIOUS CONTEXT ==="
            ),
        )

    return ctx


# ---------------------------------------------------------------------------
# Phase 5 — typed-artifact / durable-replay read surface (API-04, API-05).
#
# Both endpoints route every read through the SINGLE default-deny ``ScopedStore``
# helper (``agents/authz.py``, §19) — the engine and the API share one enforced
# read path. A cross-owner / missing run resolves to ``None`` at the helper and
# is surfaced as 404 here (never 403 — no existence leak; the runs.py:14-17 IDOR
# precedent, D-08). These handlers are ``async def`` because the ``ScopedStore``
# methods are coroutines (D-08); they accept the injected request ``Session`` via
# ``Depends(get_db)`` so the helper reuses the one acquisition path.
# ---------------------------------------------------------------------------


def _build_lineage_tree(refs: list, *, include_content: bool) -> list[dict]:
    """Assemble the nested lineage TREE from a flat list of scoped ArtifactRef
    rows (D-10). Roots = refs with neither ``derived_from`` nor any in-set
    ``parents``; each node carries the typed ref fields + ``children: []`` built
    by walking ``parents``/``derived_from``. Cycles / dangling parent ids are
    tolerated (an unreachable ref still surfaces as a root so nothing is lost).
    Inline ``content`` is EXCLUDED unless ``include_content`` (D-10 — reduces
    incidental exposure of large artifact bodies, T-5-CONTENT).
    """
    ids = {r.id for r in refs}

    def _node(r) -> dict:
        node = {
            "id": r.id,
            "kind": r.kind,
            "producer_step": r.producer_step,
            "producer_agent": r.producer_agent,
            "task_id": r.task_id,
            "content_hash": r.content_hash,
            "version": r.version,
            "visibility": r.visibility,
            "retention": r.retention,
            "location": r.location,
            "parents": list(r.parents or []),
            "derived_from": r.derived_from,
            "children": [],
        }
        if include_content:
            node["content"] = r.content
        return node

    nodes = {r.id: _node(r) for r in refs}

    # A ref's parent set = explicit derived_from + the parents[] list, restricted
    # to ids present in THIS run's scoped set (a parent outside the set can't be a
    # tree edge — the child becomes a root instead).
    def _parent_ids(r) -> list[str]:
        pids: list[str] = []
        if r.derived_from and r.derived_from in ids:
            pids.append(r.derived_from)
        for pid in (r.parents or []):
            if pid in ids and pid not in pids:
                pids.append(pid)
        return pids

    # WR-04: attach each node under AT MOST ONE parent, and never close a cycle.
    # The previous loop appended the same nodes[r.id] object under every in-set
    # parent, so one dict was shared across multiple children lists — and a
    # mutual-parent pair (A↦B, B↦A both in-set) produced a self-referential
    # structure that FastAPI's JSON encoder rejects with "Circular reference
    # detected". Here each node is attached to exactly one parent (the first in-set
    # parent that does not create a cycle); nodes that cannot be attached surface
    # as roots so nothing is lost.
    #
    # `_attached_parent[child_id] = parent_id` records the single chosen edge so we
    # can walk a candidate parent's ancestry and refuse an edge whose parent is a
    # descendant of the child (that would close a cycle).
    _attached_parent: dict[str, str] = {}

    def _would_cycle(child_id: str, parent_id: str) -> bool:
        # True iff child_id is already an ancestor of parent_id via chosen edges
        # (so attaching child under parent would form a loop). Also covers self.
        cur = parent_id
        seen: set[str] = set()
        while cur is not None and cur not in seen:
            if cur == child_id:
                return True
            seen.add(cur)
            cur = _attached_parent.get(cur)
        return False

    roots: list[dict] = []
    for r in refs:
        pids = _parent_ids(r)
        chosen_parent: Optional[str] = None
        for pid in pids:
            if pid == r.id:
                continue  # self-edge — never attach
            if _would_cycle(r.id, pid):
                continue  # closing this edge would create a cycle — skip it
            chosen_parent = pid
            break
        if chosen_parent is None:
            roots.append(nodes[r.id])
        else:
            nodes[chosen_parent]["children"].append(nodes[r.id])
            _attached_parent[r.id] = chosen_parent
    return roots


@router.get("/{workflow_id}/artifacts")
async def get_run_artifacts(
    workflow_id: str,
    include: Optional[str] = None,
    kind: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's typed ``ArtifactRef`` lineage TREE (API-04, D-10).

    Each node carries the ref fields (id/kind/producer step/agent/task/
    content_hash/version/visibility/retention/location/parents/derived_from)
    plus ``children: []`` assembled by walking ``parents``/``derived_from`` from
    the roots. Inline ``content`` is excluded by default; pass
    ``?include=content`` to include it (same-owner only). A cross-owner or
    missing run returns 404 (IDOR → 404, never 403).

    ``?kind=X`` (Workstream A, D-8) filters the refs to exact-kind matches BEFORE
    the tree is assembled, enabling precise fetches like
    ``?kind=clarifications&include=content`` instead of pulling the whole tree.
    Filtering before tree-building means a filtered-out parent drops its edge, so
    a surviving child surfaces as a root (the in-set parent restriction in
    ``_build_lineage_tree`` already guarantees this). An unknown kind yields an
    empty refs list → an empty tree (NOT a 422). With no ``kind`` param the code
    path is byte-identical to the pre-Workstream-A behavior by construction.
    """
    # Resolve the run with the owner filter first (for authed users owner_id ==
    # user_id) to obtain its workspace_id, then construct the ScopedStore so the
    # uniform owner+workspace scope holds for the lineage read.
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from agents.authz import ScopedStore

    store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
        session=db,
    )
    # Defense in depth: re-resolve through the single enforced read path so the
    # ownership boundary lives in ONE place (§19); cross-owner → None → 404.
    if await store.get_run(workflow_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    refs = await store.lineage(workflow_id)
    # D-8: exact-kind filter applied to the already owner+workspace-scoped refs
    # BEFORE tree-building. Pure in-Python equality — the value never reaches a
    # query (no LIKE, no SQL; ASVS V5 posture free). Unknown kind → empty list.
    if kind is not None:
        refs = [r for r in refs if r.kind == kind]
    tree = _build_lineage_tree(refs, include_content=(include == "content"))
    return {"workflow_id": workflow_id, "artifacts": tree}


@router.get("/{workflow_id}/events")
async def get_run_events(
    workflow_id: str,
    after: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``run_events`` rows with ``seq > after`` (API-05, D-11).

    Rows are ordered by ``seq`` ascending, each carrying ``seq`` + a unique
    ``event_id`` (idempotent replay). ``after`` is int-coerced by FastAPI
    (non-int → 422; ASVS V5 — never reaches raw SQL) and flows into the
    parameterized ORM ``.filter()``. A cross-owner or missing run returns 404.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from agents.authz import ScopedStore

    store = ScopedStore(
        owner_id=current_user.id,
        workspace_id=workflow_run.workspace_id,
        session=db,
    )
    if await store.get_run(workflow_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    rows = await store.read_events(workflow_id, after_seq=after)
    return {
        "workflow_id": workflow_id,
        "after": after,
        "events": [
            {
                "seq": r.seq,
                "event_id": r.event_id,
                "type": r.type,
                "payload_json": r.payload_json,
            }
            for r in rows
        ],
    }

class FamilyMemberResponse(BaseModel):
    """One run in a revision family (POR §4.3). Carries only the lightweight
    listing fields — NOT the heavy input/output/agent_outputs bodies — since the
    timeline UI renders chips, and a full member fetch goes through get_run."""

    id: str
    type: str
    title: str
    status: str
    revision_index: int          # 1-based chronological position within the family
    parent_run_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    # KAN-113: same UTC-promotion serialiser as WorkflowRunResponse (SQLite naive
    # datetime → JavaScript Date.parse local-time misread → wrong "Nh ago" label).
    @field_serializer("created_at", "completed_at")
    def _serialize_dt(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()


class RunFamilyResponse(BaseModel):
    """The owned revision family of a run: its root + all owned descendants."""

    root_id: str
    members: list[FamilyMemberResponse]


def _owned_family_members(
    db: Session, user_id: str, root_id: str
) -> list[FamilyMemberResponse]:
    """BFS DOWN from ``root_id`` over OWNED children only → the ordered family
    member list (1-based ``revision_index``, root's out-of-family parent nulled).

    Extracted from ``get_run_family`` so ``get_run_summary`` reuses the SAME owned
    walk instead of duplicating it (INV-12 / no dual impl). Every query is
    owner-scoped (``user_id == user_id``) so no foreign run metadata enters the
    list; a visited-id set guards a cyclic parent chain (threat T-A-04). Members
    are ordered ``(created_at ASC, id ASC)`` — the id tiebreak makes same-timestamp
    ordering deterministic on SQLite — and every non-root member's parent is
    in-family by BFS construction, so the ``in members`` nulling never leaks a
    foreign id.

    BUG-FIX (FIX-173): the BFS now only admits children whose normalized base type
    matches the root's — stripping the generic ``_revision`` suffix and the ``od_``
    variant prefix (SC-001: no literal pipeline-type name check). A prototype revision
    accidentally parented to a PPT root (or vice-versa) is excluded, so concurrent
    PPT + prototype revision sessions no longer cross-contaminate each other's version
    dropdown.

    BUG-FIX (FIX-179): the normalization now ALSO strips the ``od_`` variant prefix
    so that an ``od_prototype`` root correctly admits ``prototype_revision`` children —
    both normalize to ``"prototype"``. Without this, ``od_prototype`` roots returned
    only themselves (1 member) because ``"prototype" != "od_prototype"``, causing the
    version dropdown to show only the initial run regardless of how many revisions existed.
    """
    members: dict[str, WorkflowRun] = {}
    root_row = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == root_id, WorkflowRun.user_id == user_id)
        .first()
    )
    if root_row is not None:
        members[root_row.id] = root_row

    # Derive the root's base pipeline-type ONCE for the cross-family guard below.
    # SC-001 / INV-1: keyed ONLY on generic suffixes/prefixes — no literal
    # pipeline-name branch. We strip the ``_revision`` suffix THEN the ``od_``
    # variant prefix so that ``od_prototype`` and ``prototype_revision`` both
    # normalise to ``"prototype"``, and ``ppt_revision`` normalises to ``"ppt"``,
    # etc. — preventing cross-type contamination without
    # naming any workflow. Without the ``od_`` strip, an ``od_prototype`` root's
    # children (type ``prototype_revision``) were incorrectly excluded by the
    # guard because ``"prototype" != "od_prototype"`` (FIX-179).
    def _canonical_base(t: str) -> str:
        """Strip generic ``_revision`` suffix then ``od_`` variant prefix."""
        return t.removesuffix("_revision").removeprefix("od_")

    root_base_type: str | None = (
        _canonical_base(root_row.type) if root_row is not None else None
    )

    frontier = {root_id}
    visited = {root_id}
    while frontier:
        children = (
            db.query(WorkflowRun)
            .filter(
                WorkflowRun.parent_run_id.in_(frontier),
                WorkflowRun.user_id == user_id,
            )
            .all()
        )
        frontier = set()
        for child in children:
            if child.id in visited:
                continue  # cycle guard — never re-enqueue an already-seen run
            # FIX-173/FIX-179: cross-family isolation — skip a child whose
            # canonical base type differs from the root's. Uses _canonical_base
            # (strip ``_revision`` then ``od_`` prefix) so ``od_prototype`` roots
            # correctly admit ``prototype_revision`` children (both → ``prototype``).
            if root_base_type is not None and _canonical_base(child.type) != root_base_type:
                continue
            visited.add(child.id)
            members[child.id] = child
            frontier.add(child.id)

    ordered = sorted(members.values(), key=lambda r: (r.created_at, r.id))
    return [
        FamilyMemberResponse(
            id=r.id,
            type=r.type,
            title=r.title,
            status=r.status,
            revision_index=idx,
            parent_run_id=(r.parent_run_id if r.parent_run_id in members else None),
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for idx, r in enumerate(ordered, start=1)
    ]


# Per-agent fields that are summary-SAFE to surface (identity + KPI telemetry
# only). Deliberately EXCLUDES the raw content fields — output / input_prompt /
# thinking_text / tool_calls / context_sources — which could carry a secret, so
# the summary never echoes untrusted agent bytes (threat T-36-02-Leak / V7).
_SUMMARY_SAFE_AGENT_KEYS = (
    "agent_id",
    "name",
    "role",
    "icon",
    "duration",
    "error",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)


class RunSummaryResponse(BaseModel):
    """Aggregated, read-only summary of an owned run — the data spine for the
    Wave-2 Run-detail page (SHELL-03).

    Every field maps to an EXISTING ``WorkflowRun`` column or the owned family
    walk (ZERO invented fields, ZERO new tables/migrations). The endpoint only
    READS, so the 5 backend goldens are untouched by construction (INV-3):
      * KPI stats  → ``duration`` + ``agent_count`` + ``token_usage`` columns
      * failure banner → ``status`` + ``error`` columns
      * per-agent breakdown → ``agent_outputs`` (safe-projected, no raw bytes)
      * version/revision timeline → the ``parent_run_id`` family walk (reused).
    """

    id: str
    title: str
    type: str
    status: str
    input: Optional[str] = None        # the owner's OWN top-level brief/prompt (run.input)
    duration: Optional[float] = None
    agent_count: int
    token_usage: dict
    error: Optional[str] = None
    agents: list                       # per-agent breakdown (summary-safe fields only)
    root_id: str
    members: list[FamilyMemberResponse]


@router.get("/{workflow_id}/family", response_model=RunFamilyResponse)
def get_run_family(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the owned revision family (root + all owned descendants) of a run.

    POR §4.3 / D-2 / D-6. Every step is owner-scoped (``user_id ==
    current_user.id``): the entry resolve, the root walk, AND every BFS step, so
    a cross-owner or missing run resolves to 404 (never 403 — the runs.py:14-17
    IDOR posture) and a foreign parent in the chain terminates the walk with NO
    foreign run metadata entering the response (threats T-A-02/03).

    Members are ordered ``(created_at ASC, id ASC)`` — the id tiebreak makes
    same-timestamp ordering deterministic on SQLite — and each carries a 1-based
    ``revision_index`` (chronological v-number, D-2) plus its ``parent_run_id``,
    which is nulled for the root (whose parent is out-of-family) so no dangling
    foreign pointer leaks.
    """
    # (a) Owner-scoped entry resolve — missing / cross-owner → 404.
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    # (b) Resolve the family root via the owned ancestor walk (terminates at any
    # foreign/missing link, so root is always an OWNED run id).
    root_id = _compute_root_ids(db, current_user.id, [workflow_run])[workflow_run.id]

    # (c)–(e) Collect + order the owned family via the shared BFS-down helper
    # (deterministic chronological order, 1-based revision_index, root parent
    # nulled). Extracted so /summary reuses the SAME owned walk (no dual impl).
    member_responses = _owned_family_members(db, current_user.id, root_id)
    return RunFamilyResponse(root_id=root_id, members=member_responses)


@router.get("/{workflow_id}/summary", response_model=RunSummaryResponse)
def get_run_summary(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate an owned run into the Wave-2 Run-detail summary (SHELL-03).

    Additive + READ-ONLY: reads ONLY existing ``WorkflowRun`` columns plus the
    owned revision-family walk — inventing zero fields and adding zero tables /
    migrations, so the 5 backend goldens are untouched by construction (INV-3)
    and no engine/transport is touched (LOCK-B).

    Owner-scoped via ``_owner_gate_or_404`` on ``WorkflowRun.user_id`` — the
    principal, NEVER the nullable ``owner_id`` — so a cross-owner or missing run
    resolves to 404 (IDOR → 404, never 403, never a 200 with another owner's
    data; P13/P25). The owned family walk terminates at any foreign ancestor, so
    no foreign run metadata leaks into the timeline (threat T-36-02-IDOR).
    """
    # (1) Owner gate — user_id keyed; missing / cross-owner → 404.
    run = _owner_gate_or_404(db, workflow_id, current_user.id)

    # (2) Tolerant parse of the two stored JSON blobs. Stored text is never
    # trusted to be well-formed → parse each inside try/except with a []/{}
    # fallback so a malformed blob degrades to an empty aggregate, never a 500
    # (DoS guard; mirrors the runs.py agent_outputs idiom above, threat
    # T-36-02-DoS).
    raw_agents: list = []
    if run.agent_outputs:
        try:
            parsed = json.loads(run.agent_outputs)
            if isinstance(parsed, list):
                raw_agents = parsed
        except Exception:
            pass

    token_usage: dict = {}
    if run.token_usage:
        try:
            parsed_tu = json.loads(run.token_usage)
            if isinstance(parsed_tu, dict):
                token_usage = parsed_tu
        except Exception:
            pass

    # (3) Per-agent breakdown — project ONLY the summary-safe identity + KPI
    # fields; NEVER echo the raw output / input_prompt / thinking_text /
    # tool_calls that could carry a secret (threat T-36-02-Leak / V7).
    agents = [
        {k: a.get(k) for k in _SUMMARY_SAFE_AGENT_KEYS if k in a}
        for a in raw_agents
        if isinstance(a, dict)
    ]

    # (4) Version/revision timeline — REUSE the owned ancestor walk for the root
    # and the SAME owned BFS-down member list get_run_family builds (no dual impl).
    root_id = _compute_root_ids(db, current_user.id, [run])[run.id]
    members = _owned_family_members(db, current_user.id, root_id)

    return RunSummaryResponse(
        id=run.id,
        title=run.title,
        type=run.type,
        status=run.status,
        # The owner's OWN top-level brief (run.input) — owner-gated already; this is
        # the same prompt the base detail showed the owner (the revision-instruction
        # preview reads it). NEVER child-agent output/input_prompt/secrets (V7 keeps
        # those out of the per-agent projection above).
        input=run.input,
        duration=run.duration,
        agent_count=run.agent_count,
        token_usage=token_usage,
        error=run.error,
        agents=agents,
        root_id=root_id,
        members=members,
    )


@router.get("/{workflow_id}/hook-runs")
async def get_hook_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all ``hook_runs`` rows for a completed or active workflow run (KAN-73).

    Used by the frontend Audit tab to populate the audit trail on history-reopen.
    Owner-scoped (returns 404 on a cross-owner or missing run). Rows are ordered
    by ``created_at`` ascending so the Audit tab shows events in execution order.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    from app.models.hook_runs import HookRun

    rows = (
        db.query(HookRun)
        .filter(HookRun.run_id == workflow_id, HookRun.owner_id == current_user.id)
        .order_by(HookRun.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "hook_runs": [
            {
                "id": r.id,
                "hook": r.hook,
                "event": r.event,
                "outcome": r.outcome,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _owner_gate_or_404(db: Session, workflow_id: str, user_id: str) -> WorkflowRun:
    """Layer-1 owner gate shared by the audit reads (mirrors ``get_hook_runs``).

    Gates the run by ``WorkflowRun.user_id == current_user.id`` — the principal,
    NEVER the nullable ``owner_id`` — so a cross-owner or missing run resolves to
    404 (IDOR → 404, never 403, never a 200 with another owner's rows; P13/P25).
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )
    return workflow_run


@router.get("/{workflow_id}/gate-events")
async def get_gate_events(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``gate_events`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated
    ``gate_events`` table. Two-layer owner gate (mirrors ``get_hook_runs``):
    Layer 1 gates the run by ``user_id`` (→ 404 on cross-owner/missing); Layer 2
    re-filters the child rows by ``owner_id`` (defense-in-depth, T-32-03-01/03).
    Rows are ordered by ``created_at`` ascending so the Audit tab shows events in
    execution order.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(GateEvent)
        .filter(GateEvent.run_id == workflow_id, GateEvent.owner_id == current_user.id)
        .order_by(GateEvent.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "gate_events": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "gate": r.gate,
                "outcome": r.outcome,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{workflow_id}/validation-results")
async def get_validation_results(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``validation_results`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated
    ``validation_results`` table. Two-layer owner gate identical to
    ``get_gate_events`` (Layer 1 ``user_id`` → 404; Layer 2 ``owner_id``
    re-filter). Ordered by ``created_at`` ascending.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(ValidationResult)
        .filter(
            ValidationResult.run_id == workflow_id,
            ValidationResult.owner_id == current_user.id,
        )
        .order_by(ValidationResult.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "validation_results": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "validator": r.validator,
                "severity": r.severity,
                "attempt": r.attempt,
                "issues": r.issues,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{workflow_id}/exec-runs")
async def get_exec_runs(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the run's ``exec_runs`` rows for the Audit tab (SC-3).

    Additive, read-only, owner-scoped read over the engine-populated ``exec_runs``
    table. Two-layer owner gate identical to ``get_gate_events``. The projection
    surfaces the ``output_digest`` column AS STORED (truncated by design) and
    NEVER re-reads or expands the raw child output, which could carry a secret
    (T-32-03-02 / ASVS V7). Ordered by ``created_at`` ascending.
    """
    _owner_gate_or_404(db, workflow_id, current_user.id)

    rows = (
        db.query(ExecRun)
        .filter(ExecRun.run_id == workflow_id, ExecRun.owner_id == current_user.id)
        .order_by(ExecRun.created_at.asc())
        .all()
    )
    return {
        "workflow_id": workflow_id,
        "exec_runs": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "step": r.step,
                "argv_json": r.argv_json,
                "outcome": r.outcome,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
                "policy_snapshot_json": r.policy_snapshot_json,
                "output_digest": r.output_digest,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
