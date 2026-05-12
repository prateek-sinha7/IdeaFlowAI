"""Pipeline orchestrator for /flowin-handoff.

Async generator that yields a stream of WS-shaped events as it walks
through clone → analyse → code → test-report → compliance → commit →
push → PR. The WebSocket handler at ``app.api.websocket`` subscribes
and forwards events to the browser.

Every event is a dict matching the existing envelope
``{"type": str, "chunk": str | None, "section": str | None, "data": dict | None}``
so the frontend can render handoff progress with the same components
that drive the presentation / user-stories pipelines.

The pipeline never executes user-supplied code. The only subprocess
invocations are ``git``, all wrapped in :mod:`handoff_github` which
applies rlimits + wall-clock timeout + scrubbed env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.agents.handoff import (
    CodingAgent,
    ComplianceAgent,
    TestAgent,
    classify_task,
)
from app.services import handoff_github as gh

logger = logging.getLogger("app.services.handoff_pipeline")


_BRANCH_SLUG_RE = re.compile(r"[^a-z0-9._-]+")
_BRANCH_PREFIX = "flowin-handoff"
_MAX_TREE_ENTRIES = 500
_MAX_RELEVANT_FILES = 12
_MAX_TEST_FILES = 10
_IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".turbo",
    ".cache",
    "coverage",
    ".idea",
    ".vscode",
}
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".bz2", ".xz", ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".mov", ".pptx", ".docx", ".xlsx", ".bin", ".so",
    ".dylib", ".dll", ".exe", ".class", ".jar",
}
_TEST_PATH_HINTS = ("/test", "/tests", "/__tests__", "/spec", ".test.", ".spec.", "test_", "_test.")


def _branch_name(handoff_id: str, task: str) -> str:
    """Derive a stable branch name from the handoff id + a slug of the task."""
    slug = _BRANCH_SLUG_RE.sub("-", task.lower())[:32].strip("-") or "task"
    short_id = handoff_id.split("-")[0]
    return f"{_BRANCH_PREFIX}/{short_id}-{slug}"


def _walk_repo(workspace: str) -> list[str]:
    """Return a sorted, capped list of repo-relative file paths."""
    paths: list[str] = []
    for root, dirs, files in os.walk(workspace, topdown=True):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIR_NAMES]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in _BINARY_EXTS:
                continue
            rel = os.path.relpath(os.path.join(root, name), workspace)
            if rel.startswith(".git/"):
                continue
            paths.append(rel.replace(os.sep, "/"))
            if len(paths) >= _MAX_TREE_ENTRIES * 4:
                break
        if len(paths) >= _MAX_TREE_ENTRIES * 4:
            break
    paths.sort()
    return paths[:_MAX_TREE_ENTRIES]


def _format_tree(paths: list[str]) -> str:
    return "\n".join(paths)


def _read_text_file(workspace: str, rel_path: str, max_bytes: int = 200_000) -> str:
    """Read a repo file as UTF-8 text. Binary or oversize → empty string."""
    full = os.path.join(workspace, rel_path)
    try:
        size = os.path.getsize(full)
    except OSError:
        return ""
    if size > max_bytes:
        return ""
    try:
        with open(full, "rb") as fh:
            raw = fh.read()
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{2,}")


def _select_relevant_files(task: str, paths: list[str]) -> list[str]:
    """Heuristic file selection. Cheap, deterministic, no LLM calls.

    Splits the task into identifier-like tokens, ranks every path by the
    number of distinct task tokens it contains, then returns the top N.
    A README is always included if present (provides project context).
    """
    tokens = {t.lower() for t in _IDENT_RE.findall(task) if len(t) >= 3}
    tokens -= {"the", "and", "for", "with", "from", "this", "that", "task", "fix", "add", "remove"}

    scored: list[tuple[int, int, str]] = []
    for p in paths:
        lower = p.lower()
        hits = sum(1 for tok in tokens if tok in lower)
        depth = lower.count("/")
        scored.append((hits, -depth, p))
    scored.sort(reverse=True)

    selected: list[str] = []
    for hits, _, path in scored:
        if hits == 0 and len(selected) >= _MAX_RELEVANT_FILES:
            break
        if path in selected:
            continue
        selected.append(path)
        if len(selected) >= _MAX_RELEVANT_FILES:
            break

    for candidate in ("README.md", "README.rst", "README.txt", "readme.md"):
        if candidate in paths and candidate not in selected:
            selected.insert(0, candidate)
            break
    return selected[:_MAX_RELEVANT_FILES]


def _select_test_files(paths: list[str]) -> list[str]:
    """Return the test-like files (capped). Cheap path heuristic."""
    tests = [p for p in paths if any(hint in p for hint in _TEST_PATH_HINTS)]
    return tests[:_MAX_TEST_FILES]


def _safe_workspace_join(workspace: str, rel_path: str) -> str:
    """Resolve ``workspace/rel_path`` and refuse anything escaping the workspace.

    Defends against the CodingAgent producing absolute paths, ``..``
    segments, ``.git`` writes, or symlinks. Returns the absolute path
    on success; raises ``ValueError`` on rejection.
    """
    if not rel_path or not isinstance(rel_path, str):
        raise ValueError("path must be a non-empty string")
    rel_path = rel_path.strip()
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise ValueError(f"absolute path not allowed: {rel_path!r}")
    norm = os.path.normpath(rel_path)
    if norm.startswith(".."):
        raise ValueError(f"path escapes workspace: {rel_path!r}")
    parts = norm.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ValueError(f"'..' segment not allowed: {rel_path!r}")
    if parts and parts[0] == ".git":
        raise ValueError(".git directory cannot be edited")
    workspace_real = os.path.realpath(workspace)
    target = os.path.realpath(os.path.join(workspace_real, norm))
    if target != workspace_real and not target.startswith(workspace_real + os.sep):
        raise ValueError(f"resolved path escapes workspace: {rel_path!r}")
    return target


def _apply_edits(workspace: str, edits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply the CodingAgent's edit plan. Returns per-edit application status."""
    results: list[dict[str, Any]] = []
    for raw_edit in edits:
        path = raw_edit.get("path", "")
        op = raw_edit.get("operation", "")
        old = raw_edit.get("old_string", "") or ""
        new = raw_edit.get("new_string", "") or ""
        try:
            target = _safe_workspace_join(workspace, path)
        except ValueError as exc:
            results.append({"path": path, "operation": op, "status": "rejected", "reason": str(exc)})
            continue

        try:
            if op == "create":
                if os.path.exists(target):
                    results.append({"path": path, "operation": op, "status": "rejected", "reason": "file exists"})
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(new)
                results.append({"path": path, "operation": op, "status": "applied"})
            elif op == "modify":
                if not os.path.exists(target):
                    results.append({"path": path, "operation": op, "status": "rejected", "reason": "file missing"})
                    continue
                with open(target, "r", encoding="utf-8") as fh:
                    contents = fh.read()
                if old and contents.count(old) != 1:
                    results.append({"path": path, "operation": op, "status": "rejected", "reason": f"old_string match count = {contents.count(old)} (expected 1)"})
                    continue
                if old:
                    contents = contents.replace(old, new, 1)
                else:
                    contents = new
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(contents)
                results.append({"path": path, "operation": op, "status": "applied"})
            elif op == "delete":
                if not os.path.exists(target):
                    results.append({"path": path, "operation": op, "status": "rejected", "reason": "file missing"})
                    continue
                os.remove(target)
                results.append({"path": path, "operation": op, "status": "applied"})
            else:
                results.append({"path": path, "operation": op, "status": "rejected", "reason": f"unknown operation {op!r}"})
        except OSError as exc:
            results.append({"path": path, "operation": op, "status": "rejected", "reason": f"OSError: {exc}"})
    return results


def _build_pr_body(
    task: str,
    coding_summary: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    compliance_report: dict[str, Any] | None,
    edit_results: list[dict[str, Any]] | None,
    handoff_token: str,
    issuer_email: str | None,
) -> str:
    """Markdown body for the GitHub PR. No secrets, length-capped at call site."""
    lines = ["## Summary", "", f"_Task:_ {task}", ""]
    if coding_summary:
        lines.append(f"**What changed**: {coding_summary.get('summary', '').strip() or '(no summary)'}")
        rationale = (coding_summary.get("rationale") or "").strip()
        if rationale:
            lines += ["", "**Why**:", rationale]
    if edit_results:
        applied = [r for r in edit_results if r.get("status") == "applied"]
        rejected = [r for r in edit_results if r.get("status") != "applied"]
        lines += ["", f"**Files edited**: {len(applied)} applied" + (f", {len(rejected)} rejected" if rejected else "")]
        for r in applied:
            lines.append(f"- `{r['path']}` ({r['operation']})")
        for r in rejected:
            lines.append(f"- ~~`{r['path']}`~~ rejected: {r.get('reason', '')}")
    if test_report:
        lines += [
            "",
            "## Test analysis",
            "",
            f"_Verdict_: **{test_report.get('verdict', 'concerns')}**",
            "",
            test_report.get("summary", "") or "",
        ]
        missing = test_report.get("missing_coverage") or []
        if missing:
            lines.append("\n**Missing coverage:**")
            for m in missing[:10]:
                lines.append(f"- {m.get('area', '')}: {m.get('suggested_test', '')}")
        quality = test_report.get("quality_issues") or []
        if quality:
            lines.append("\n**Test-quality issues:**")
            for q in quality[:10]:
                lines.append(f"- ({q.get('severity', '?')}) {q.get('issue', '')} — {q.get('path', '')}")
    if compliance_report:
        lines += [
            "",
            "## Compliance review",
            "",
            f"_Verdict_: **{compliance_report.get('verdict', 'approve_with_changes')}**",
            "",
            compliance_report.get("summary", "") or "",
        ]
        findings = compliance_report.get("findings") or []
        if findings:
            lines.append("\n**Findings:**")
            for f in findings[:15]:
                lines.append(
                    f"- [{f.get('severity', '?')}/{f.get('category', '?')}] "
                    f"{f.get('location', '')}: {f.get('issue', '')}. _{f.get('recommendation', '')}_"
                )
        positives = compliance_report.get("positives") or []
        if positives:
            lines.append("\n**Positives:**")
            for p in positives[:5]:
                lines.append(f"- {p}")
    lines += [
        "",
        "---",
        "",
        f"_Generated by [Flowin handoff]({handoff_token}) — review carefully before merging._",
    ]
    if issuer_email:
        lines += ["", f"_Requested by {issuer_email}._"]
    return "\n".join(lines)


def _event(
    event_type: str,
    *,
    chunk: str | None = None,
    section: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": event_type, "chunk": chunk, "section": section, "data": data}


async def run_handoff_pipeline(
    *,
    handoff_id: str,
    handoff_token: str,
    task_description: str,
    transcript_excerpt: str | None,
    repo_url: str,
    requested_mode: str,
    source_branch: str | None,
    pat: str,
    issuer_email: str | None,
    handoff_public_url: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator over pipeline events.

    Yields one dict per step (envelope shape matches existing
    ``app.api.websocket`` events). The caller is responsible for:

    * Persisting the final ``pipeline_complete`` event's ``data`` to
      ``HandoffSession.pipeline_output``.
    * Updating ``HandoffSession.status`` based on success/failure.
    * Forwarding the events to the WebSocket client.

    On any unhandled exception the generator yields a single
    ``handoff_error`` event and re-raises. The workspace is always
    cleaned up.
    """
    workspace_root = tempfile.mkdtemp(prefix=f"handoff-{handoff_id[:8]}-")
    workspace = os.path.join(workspace_root, "workspace")
    branch = _branch_name(handoff_id, task_description)

    pipeline_output: dict[str, Any] = {
        "handoff_id": handoff_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "branch_name": branch,
        "edit_results": [],
    }

    try:
        # --- Parse repo URL & resolve default branch ---
        try:
            target = gh.parse_github_url(repo_url)
        except ValueError as exc:
            yield _event("handoff_error", data={"message": f"Invalid repo URL: {exc}"})
            raise

        yield _event("phase_start", section="setup", data={"task": task_description, "repo": f"{target.owner}/{target.repo}"})
        try:
            meta = await gh.get_repo_metadata(target, pat)
        except RuntimeError as exc:
            yield _event("handoff_error", data={"message": f"GitHub metadata fetch failed: {exc}"})
            raise
        default_branch = meta["default_branch"]
        base_branch = source_branch or default_branch
        pipeline_output["base_branch"] = base_branch
        pipeline_output["default_branch"] = default_branch
        yield _event("phase_end", section="setup", data={"default_branch": default_branch, "base_branch": base_branch})

        # --- Clone ---
        yield _event("phase_start", section="clone", data={"branch": base_branch})
        clone_res = await asyncio.to_thread(gh.clone, target, pat, workspace_root, base_branch)
        if clone_res.returncode != 0:
            yield _event(
                "handoff_error",
                data={"message": "git clone failed", "stderr": clone_res.stderr[:1000]},
            )
            raise RuntimeError(f"git clone failed: {clone_res.stderr[:300]}")
        yield _event("phase_end", section="clone", data={"workspace": workspace})

        # --- Classify mode ---
        mode = requested_mode
        if mode == "auto":
            yield _event("phase_start", section="classify")
            mode = await classify_task(task_description, transcript_excerpt)
            yield _event("phase_end", section="classify", data={"resolved_mode": mode})
        pipeline_output["resolved_mode"] = mode

        # --- Walk repo, prep context ---
        paths = _walk_repo(workspace)
        tree_text = _format_tree(paths)

        coding_summary: dict[str, Any] | None = None
        edit_results: list[dict[str, Any]] = []
        edited_file_contents: dict[str, str] = {}

        # --- Coding step (only if mode is "coding") ---
        if mode == "coding":
            yield _event("agent_thinking", data={"agent_id": "coding_agent", "thinking": "Reading relevant files and planning the change..."})
            relevant_paths = _select_relevant_files(task_description, paths)
            relevant_files = {p: _read_text_file(workspace, p) for p in relevant_paths}
            coding_agent = CodingAgent()
            try:
                coding_summary = await coding_agent.propose_edits(
                    task=task_description,
                    repo_tree=tree_text,
                    relevant_files=relevant_files,
                    transcript_excerpt=transcript_excerpt,
                )
            except Exception as exc:
                yield _event("agent_error", data={"agent_id": "coding_agent", "error": str(exc)})
                raise
            # Trim each edit's old/new strings before shipping to the frontend.
            # 16 KiB per side is enough to render a meaningful diff for the
            # human reviewer; the canonical full version stays in the PR body.
            _MAX_EDIT_SIDE_BYTES = 16 * 1024

            def _trim(s: str | None) -> str:
                s = s or ""
                if len(s.encode("utf-8")) <= _MAX_EDIT_SIDE_BYTES:
                    return s
                return s.encode("utf-8")[:_MAX_EDIT_SIDE_BYTES].decode("utf-8", errors="replace") + "\n\n… (truncated for preview)"

            preview_edits = [
                {
                    "path": e.get("path", ""),
                    "operation": e.get("operation", ""),
                    "old_string": _trim(e.get("old_string", "")),
                    "new_string": _trim(e.get("new_string", "")),
                }
                for e in coding_summary.get("edits", [])
            ]
            yield _event(
                "agent_complete",
                data={
                    "agent_id": "coding_agent",
                    "summary": coding_summary.get("summary", ""),
                    "rationale": coding_summary.get("rationale", ""),
                    "edit_count": len(coding_summary.get("edits", [])),
                    "edits": preview_edits,
                    "tests_added": coding_summary.get("tests_added", []),
                    "follow_ups": coding_summary.get("follow_ups", []),
                },
            )
            # Persist the trimmed view so a refresh after pipeline_complete can
            # rebuild the Diff tab from pipeline_output without re-running the
            # WS event stream. The untrimmed coding_summary stays in the
            # pipeline-task local scope; we never ship the full edit bodies
            # to the DB to keep the row size bounded.
            pipeline_output["coding_summary"] = {
                "summary": coding_summary.get("summary", ""),
                "rationale": coding_summary.get("rationale", ""),
                "edits": preview_edits,
                "edit_count": len(coding_summary.get("edits", [])),
                "tests_added": coding_summary.get("tests_added", []),
                "follow_ups": coding_summary.get("follow_ups", []),
            }
            edit_results = _apply_edits(workspace, coding_summary.get("edits", []))
            pipeline_output["edit_results"] = edit_results
            yield _event("phase_end", section="apply_edits", data={"results": edit_results})

            for r in edit_results:
                if r.get("status") == "applied" and r.get("operation") != "delete":
                    contents = _read_text_file(workspace, r["path"])
                    if contents:
                        edited_file_contents[r["path"]] = contents

        # --- Test analysis ---
        yield _event("agent_thinking", data={"agent_id": "test_agent", "thinking": "Analysing test coverage..."})
        test_paths = _select_test_files(_walk_repo(workspace))
        test_files = {p: _read_text_file(workspace, p) for p in test_paths}
        if edited_file_contents:
            for p, c in edited_file_contents.items():
                if any(hint in p for hint in _TEST_PATH_HINTS):
                    test_files[p] = c
        test_agent = TestAgent()
        try:
            test_report = await test_agent.analyse(
                task=task_description,
                repo_tree=tree_text,
                test_files=test_files,
                coding_summary=coding_summary,
            )
        except Exception as exc:
            yield _event("agent_error", data={"agent_id": "test_agent", "error": str(exc)})
            raise
        yield _event("agent_complete", data={"agent_id": "test_agent", "report": test_report})
        pipeline_output["test_report"] = test_report

        # --- Compliance ---
        yield _event("agent_thinking", data={"agent_id": "compliance_agent", "thinking": "Reviewing for security and best practices..."})
        if not edited_file_contents and coding_summary is None:
            review_files = test_files
        else:
            review_files = edited_file_contents or test_files
        compliance_agent = ComplianceAgent()
        try:
            compliance_report = await compliance_agent.review(
                task=task_description,
                repo_tree=tree_text,
                edited_files=review_files,
                coding_summary=coding_summary,
                test_report=test_report,
            )
        except Exception as exc:
            yield _event("agent_error", data={"agent_id": "compliance_agent", "error": str(exc)})
            raise
        yield _event("agent_complete", data={"agent_id": "compliance_agent", "report": compliance_report})
        pipeline_output["compliance_report"] = compliance_report

        # --- Commit + push (only if we actually changed something) ---
        applied_edits = [r for r in edit_results if r.get("status") == "applied"]
        pr_info: dict[str, object] | None = None
        if applied_edits:
            yield _event("phase_start", section="commit", data={"branch": branch})
            cb = await asyncio.to_thread(gh.checkout_new_branch, workspace, branch)
            if cb.returncode != 0:
                yield _event("handoff_error", data={"message": "branch checkout failed", "stderr": cb.stderr[:500]})
                raise RuntimeError(f"branch checkout failed: {cb.stderr[:300]}")
            sa = await asyncio.to_thread(gh.stage_all, workspace)
            if sa.returncode != 0:
                yield _event("handoff_error", data={"message": "git add failed", "stderr": sa.stderr[:500]})
                raise RuntimeError(f"git add failed: {sa.stderr[:300]}")
            commit_msg = (coding_summary or {}).get("summary") or task_description[:72]
            commit_msg = commit_msg.strip().replace("\n", " ")[:200] or "Flowin handoff change"
            cm = await asyncio.to_thread(gh.commit, workspace, commit_msg)
            if cm.returncode != 0:
                # Possible cause: no changes vs base. Treat as soft failure.
                yield _event("phase_end", section="commit", data={"committed": False, "stderr": cm.stderr[:300]})
            else:
                yield _event("phase_end", section="commit", data={"committed": True, "message": commit_msg})
                yield _event("phase_start", section="push", data={"branch": branch})
                pu = await asyncio.to_thread(gh.push, target, pat, workspace, branch)
                if pu.returncode != 0:
                    yield _event("handoff_error", data={"message": "git push failed", "stderr": pu.stderr[:500]})
                    raise RuntimeError(f"git push failed: {pu.stderr[:300]}")
                gh.wipe_credentialed_remote(workspace)
                yield _event("phase_end", section="push", data={"pushed": True, "branch": branch})

                pr_body = _build_pr_body(
                    task=task_description,
                    coding_summary=coding_summary,
                    test_report=test_report,
                    compliance_report=compliance_report,
                    edit_results=edit_results,
                    handoff_token=handoff_public_url,
                    issuer_email=issuer_email,
                )
                pr_title = commit_msg
                yield _event("phase_start", section="open_pr", data={"head": branch, "base": base_branch})
                try:
                    pr_info = await gh.create_pull_request(
                        target=target,
                        pat=pat,
                        head_branch=branch,
                        base_branch=base_branch,
                        title=pr_title,
                        body=pr_body,
                    )
                except RuntimeError as exc:
                    yield _event("handoff_error", data={"message": f"PR creation failed: {exc}"})
                    raise
                yield _event("pr_created", data={"url": pr_info["url"], "number": pr_info["number"]})
                pipeline_output["pr_url"] = pr_info["url"]
                pipeline_output["pr_number"] = pr_info["number"]
        else:
            yield _event(
                "phase_end",
                section="commit",
                data={
                    "committed": False,
                    "message": "No file changes were applied (test-only run or no edits accepted).",
                },
            )

        pipeline_output["completed_at"] = datetime.now(timezone.utc).isoformat()
        yield _event("pipeline_complete", data=pipeline_output)
    finally:
        gh.cleanup_workspace(workspace_root)


# Export the JSON-serialiser used by callers persisting pipeline_output.
def serialise_pipeline_output(output: dict[str, Any]) -> str:
    return json.dumps(output)
