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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.workflow import WorkflowRun

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
    # UXFIX-02 (22-03 / D-19): the persisted declared/resolved deliverable shape
    # so history-reopen drives the deliverable mimetype from the persisted value
    # (legacy rows NULL → FE deriveDeliverableMimetype heuristic fallback, parity).
    deliverable_mimetype: Optional[str] = None
    deliverable_filename: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Endpoints ---


@router.get("", response_model=list[WorkflowRunResponse])
def list_runs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    type: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """List workflow runs for the authenticated user.

    Ordered by created_at descending (most recent first).
    Supports optional filtering by type and status.
    """
    query = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)

    if type:
        query = query.filter(WorkflowRun.type == type)
    if status_filter:
        query = query.filter(WorkflowRun.status == status_filter)

    runs = (
        query
        .order_by(WorkflowRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return runs


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

    return workflow_run


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_run(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow run.

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

    if pipeline_type in ("od_ppt", "ppt", "od_ppt_revision", "ppt_revision"):
        # Extract slide spec from brief-analyst
        analyst_output = get_agent_output("od-ppt-brief-analyst")
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
        spec_output = get_agent_output("prototype-specify") or get_agent_output("prototype-plan")
        if spec_output:
            m = re.search(r"<spec>([\s\S]*?)</spec>", spec_output)
            spec_text = (m.group(1).strip() if m else spec_output)
            structured_summary = f"Prototype Specification:\n{spec_text[:3500]}"
            agent_summaries.append({"agent": "Spec Writer", "summary": spec_text[:500]})

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
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == current_user.id,
            WorkflowRun.status == "completed",
        )
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found or not completed",
        )

    return _extract_chain_context(workflow_run)


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
