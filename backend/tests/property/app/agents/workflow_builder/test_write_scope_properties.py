"""Property tests for the Builder_Agent's write scope (Property 21).

Two layers keep writes inside ``/workflows/`` and the skill read-only:

* ``BuilderToolObserverMiddleware.awrap_tool_call`` refuses ``write_file`` and
  ``edit_file`` calls whose normalised path is not under ``/workflows/``.
* ``ReadOnlySkillsBackend`` (the ``/skills/`` route of the composite backend)
  refuses every mutation.

The skill under test is a copy of ``workflow_builder/skills`` made inside each
example, together with a fresh sandbox, in a ``TemporaryDirectory`` that
Hypothesis never reuses between examples. The tree digest taken before and
after each operation is built here from ``os.walk`` and ``hashlib``.

The expected verdict comes from ``_expected_verdict`` below. It resolves a path
with a segment stack and does not call the production path helpers. The
refusal texts are written out as literals from tasks 13.1 and 13.2.

**Validates: Requirements 18.8, 20.7, 27.2, 27.3**
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.backend_fs import (
    ReadOnlySkillsBackend,
    build_builder_backend,
)
from app.agents.workflow_builder.middleware import BuilderToolObserverMiddleware
from tests.fakes.builder_turn import FakeTurnPort

_BACKEND_DIR = Path(__file__).resolve().parents[5]
_REAL_SKILLS_ROOT = SKILLS_ROOT
_SKILL_ID = "velocity-workflow-creator"

_SCOPE_REFUSAL = "Write only under /workflows/."
_SKILL_REFUSAL = "The skill is read-only. Write your manifest under /workflows/."
_VALID_JSON = '{"k": "old"}'

# --- Path strategies -------------------------------------------------------------

_SEGMENTS = [
    "workflows",
    "skills",
    "Workflows",
    "workflows2",
    "a",
    "b.md",
    "seed.md",
    "other.md",
    "notes",
    "n.md",
    "x.workflow.json",
    "..",
    ".",
    "",
    _SKILL_ID,
    "SKILL.md",
]
_ANY_PREFIX = ["", "/", "//", "///", "./", "../", "\\", "C:\\"]
_DISK_PREFIX = ["", "/", "//", "./", "../"]


def _joined_paths(prefixes: list[str], separators: list[str]) -> st.SearchStrategy[str]:
    """Build a path from a prefix, segments and separators."""
    return st.builds(
        lambda prefix, segments, seps: prefix
        + "".join(
            seg + (seps[i % len(seps)] if i < len(segments) - 1 else "")
            for i, seg in enumerate(segments)
        ),
        st.sampled_from(prefixes),
        st.lists(st.sampled_from(_SEGMENTS), min_size=0, max_size=6),
        st.lists(st.sampled_from(separators), min_size=1, max_size=3),
    )


def _under_workflows(separators: list[str]) -> st.SearchStrategy[str]:
    """Paths that start under ``/workflows/`` so the allowed side is well covered."""
    return st.builds(
        lambda head, tail: head + tail,
        st.sampled_from(["/workflows/", "workflows/", "//workflows/", "/workflows//"]),
        _joined_paths([""], separators),
    )


_DECISION_PATHS = st.one_of(
    st.none(),
    st.just(""),
    _joined_paths(_ANY_PREFIX, ["/", "\\", "//"]),
    _under_workflows(["/", "\\"]),
)
_DISK_PATHS = st.one_of(
    _joined_paths(_DISK_PREFIX, ["/", "//"]),
    _under_workflows(["/", "//"]),
)
_WRITE_TOOLS = st.sampled_from(["write_file", "edit_file"])
_PATH_ARGS = st.sampled_from(["file_path", "path"])


def _resolve(raw: str) -> list[str]:
    """Resolve ``raw`` to path segments with a stack. ``..`` cannot pass the root."""
    stack: list[str] = []
    for segment in raw.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if stack:
                stack.pop()
            continue
        stack.append(segment)
    return stack


def _expected_verdict(raw: str | None) -> str:
    """Return ``allow``, ``skill`` or ``scope`` for a write to ``raw``."""
    if not raw:
        return "scope"
    segments = _resolve(raw)
    if segments[:1] == ["skills"]:
        return "skill"
    if segments[:1] == ["workflows"] and len(segments) >= 2:
        return "allow"
    return "scope"


# --- Tree helpers ---------------------------------------------------------------


def _tree_digest(root: Path, *, skip: Path | None = None) -> str:
    """Return one sha256 over every directory and file (name and bytes) below ``root``."""
    digest = hashlib.sha256()
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if skip is not None and current_path == skip:
            dirs.clear()
            continue
        dirs.sort()
        rel_dir = current_path.relative_to(root).as_posix()
        digest.update(f"D:{rel_dir}\n".encode())
        for name in sorted(files):
            rel = (current_path / name).relative_to(root).as_posix()
            content_hash = hashlib.sha256(
                (current_path / name).read_bytes()
            ).hexdigest()
            digest.update(f"F:{rel}:{content_hash}\n".encode())
    return digest.hexdigest()


def _skill_files(skills: Path) -> list[str]:
    """Return the skill copy's files as sorted POSIX paths relative to ``skills``."""
    return sorted(
        p.relative_to(skills).as_posix() for p in skills.rglob("*") if p.is_file()
    )


def _make_workspace(tmp: Path) -> tuple[Path, Path]:
    """Copy the real skill into ``tmp/skills`` and seed ``tmp/sandbox``."""
    skills = tmp / "skills"
    sandbox = tmp / "sandbox"
    shutil.copytree(
        _REAL_SKILLS_ROOT, skills, ignore=shutil.ignore_patterns("__pycache__")
    )
    for rel in ("workflows/seed.md", "other.md", "notes/n.md"):
        target = sandbox / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("old", encoding="utf-8")
    return skills, sandbox


def _request(tool: str, args: dict[str, Any]) -> ToolCallRequest:
    """Build a tool call request outside a graph."""
    return ToolCallRequest(
        tool_call={"name": tool, "args": args, "id": "call-1", "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


def _write_args(tool: str, arg_name: str, path: str | None) -> dict[str, Any]:
    """Build the tool arguments for a write or edit call."""
    args: dict[str, Any] = (
        {"content": _VALID_JSON}
        if tool == "write_file"
        else {"old_string": "old", "new_string": "new"}
    )
    if path is not None:
        args[arg_name] = path
    return args


# Feature: ai-workflow-builder, Property 21: Writes stay in `/workflows/` and the skill stays read-only
@settings(max_examples=100, deadline=None)
@given(tool=_WRITE_TOOLS, arg_name=_PATH_ARGS, path=_DECISION_PATHS)
def test_awrap_tool_call_allows_write_only_when_path_under_workflows(
    tool: str, arg_name: str, path: str | None
) -> None:
    """The handler runs iff the path resolves below ``/workflows/``; else the refusal is the result."""
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handled: list[ToolCallRequest] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        handled.append(request)
        return ToolMessage(content="handled", tool_call_id="call-1", name=tool)

    result = asyncio.run(
        middleware.awrap_tool_call(
            _request(tool, _write_args(tool, arg_name, path)), handler
        )
    )

    verdict = _expected_verdict(path)
    assert isinstance(result, ToolMessage)
    assert result.tool_call_id == "call-1"
    if verdict == "allow":
        assert len(handled) == 1
        assert result.content == "handled"
    else:
        assert handled == []
        assert result.status == "error"
        assert result.content == (
            _SKILL_REFUSAL if verdict == "skill" else _SCOPE_REFUSAL
        )
        assert turn.workflow_writes == []


# Feature: ai-workflow-builder, Property 21: Writes stay in `/workflows/` and the skill stays read-only
@settings(max_examples=100, deadline=None)
@given(
    tool=st.sampled_from(["read_file", "ls", "glob", "grep"]),
    arg_name=_PATH_ARGS,
    path=_DECISION_PATHS,
)
def test_awrap_tool_call_passes_read_tools_when_path_is_outside_workflows(
    tool: str, arg_name: str, path: str | None
) -> None:
    """Read tools reach the handler for any path; the write scope applies to writes only."""
    turn = FakeTurnPort()
    middleware = BuilderToolObserverMiddleware(turn)
    handled: list[ToolCallRequest] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        handled.append(request)
        return ToolMessage(content="handled", tool_call_id="call-1", name=tool)

    args: dict[str, Any] = {} if path is None else {arg_name: path}
    result = asyncio.run(middleware.awrap_tool_call(_request(tool, args), handler))

    assert len(handled) == 1
    assert isinstance(result, ToolMessage)
    assert result.content == "handled"


# Feature: ai-workflow-builder, Property 21: Writes stay in `/workflows/` and the skill stays read-only
@settings(max_examples=100, deadline=None)
@given(tool=_WRITE_TOOLS, arg_name=_PATH_ARGS, path=_DISK_PATHS)
def test_awrap_tool_call_keeps_skill_and_sandbox_unchanged_when_write_is_refused(
    tool: str, arg_name: str, path: str
) -> None:
    """Through the real composite backend, no file outside ``/workflows/`` changes and the skill hash is the same."""
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        skills, sandbox = _make_workspace(tmp)
        backend = build_builder_backend(sandbox, skills, [_SKILL_ID])
        verdict = _expected_verdict(path)
        # An allowed write may add files below sandbox/workflows; nothing else may change.
        skip = sandbox / "workflows" if verdict == "allow" else None
        skill_before = _tree_digest(skills)
        tree_before = _tree_digest(tmp, skip=skip)
        handled: list[ToolCallRequest] = []

        async def handler(request: ToolCallRequest) -> ToolMessage:
            handled.append(request)
            target = request.tool_call["args"][arg_name]
            try:
                if tool == "write_file":
                    outcome = await backend.awrite(target, _VALID_JSON)
                else:
                    outcome = await backend.aedit(target, "old", "new")
            except ValueError as exc:  # the backend rejects ".." in virtual mode
                return ToolMessage(
                    content=str(exc), tool_call_id="call-1", name=tool, status="error"
                )
            return ToolMessage(
                content=outcome.error or "ok",
                tool_call_id="call-1",
                name=tool,
                status="error" if outcome.error else "success",
            )

        middleware = BuilderToolObserverMiddleware(FakeTurnPort())
        asyncio.run(
            middleware.awrap_tool_call(
                _request(tool, _write_args(tool, arg_name, path)), handler
            )
        )

        assert (len(handled) == 1) == (verdict == "allow")
        assert _tree_digest(skills) == skill_before
        assert _tree_digest(tmp, skip=skip) == tree_before


# Feature: ai-workflow-builder, Property 21: Writes stay in `/workflows/` and the skill stays read-only
@settings(max_examples=100, deadline=None)
@given(
    operation=st.sampled_from(
        ["write", "awrite", "edit", "aedit", "upload_files", "aupload_files"]
    ),
    through_composite=st.booleans(),
    use_existing=st.booleans(),
    pick=st.integers(min_value=0, max_value=10_000),
    segments=st.lists(st.sampled_from(_SEGMENTS), min_size=1, max_size=5),
)
def test_read_only_skills_backend_refuses_mutation_when_path_is_any_skill_path(
    operation: str,
    through_composite: bool,  # noqa: FBT001
    use_existing: bool,  # noqa: FBT001
    pick: int,
    segments: list[str],
) -> None:
    """Every mutation returns the read-only text and leaves the whole temporary tree identical."""
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        skills, sandbox = _make_workspace(tmp)
        existing = _skill_files(skills)
        if use_existing:
            chosen = existing[pick % len(existing)]
            relative = "/" + chosen
            old_string = (skills / chosen).read_bytes()[:8].decode(
                "utf-8", "ignore"
            ) or "x"
        else:
            relative = "/" + "/".join(segments)
            old_string = "old"
        before = _tree_digest(tmp)

        if through_composite:
            target: Any = build_builder_backend(sandbox, skills, [_SKILL_ID])
            path = "/skills" + relative
        else:
            target = ReadOnlySkillsBackend(skills, visible=frozenset({_SKILL_ID}))
            path = relative

        errors = asyncio.run(_mutate(target, operation, path, old_string))

        assert errors == [_SKILL_REFUSAL]
        assert _tree_digest(tmp) == before


async def _mutate(
    target: Any, operation: str, path: str, old_string: str
) -> list[str | None]:
    """Run one mutation on ``target`` and return the error text of each result."""
    if operation == "write":
        return [target.write(path, "new content").error]
    if operation == "awrite":
        return [(await target.awrite(path, "new content")).error]
    if operation == "edit":
        return [target.edit(path, old_string, "new").error]
    if operation == "aedit":
        return [(await target.aedit(path, old_string, "new")).error]
    if operation == "upload_files":
        return [r.error for r in target.upload_files([(path, b"new content")])]
    return [r.error for r in await target.aupload_files([(path, b"new content")])]
