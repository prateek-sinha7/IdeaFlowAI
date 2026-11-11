"""Unit tests for ``app.agents.workflow_builder.sandbox``.

Covers the folder layout, the containment refusal, rebuild contents, the script
call temp folder path and session/user deletion. Every folder lives under
``tmp_path``; the real settings are never read because each test passes ``root``.

Requirements: 20.4, 20.5, 20.12.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder import sandbox as sandbox_module
from app.agents.workflow_builder.sandbox import (
    BUILDER_SUBDIR,
    CANVAS_FILE,
    SANDBOX_DIRS,
    BuilderSandbox,
    SandboxPathError,
    resolve_builder_root,
)

USER_ID = "user-1"
SESSION_ID = "session-1"


@dataclass(frozen=True)
class _Draft:
    """Minimal stand-in for a stored revision (satisfies ``DraftLike``)."""

    manifest: dict[str, Any] = field(default_factory=dict)
    source_file: str | None = None


def _sandbox(root: Path, user: str = USER_ID, session: str = SESSION_ID):
    return BuilderSandbox(user, session, root=root)


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Make a folder symlink; skip only on a local Windows run that lacks the privilege.

    On CI and on every other platform a failure fails the test, so the symlink
    escape branches cannot be skipped silently.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        if sys.platform == "win32" and not os.environ.get("CI"):
            pytest.skip("symlinks need a privilege on this local Windows machine")
        pytest.fail(f"could not create a symlink: {type(exc).__name__}")


# --------------------------------------------------------------------------- root


def test_resolve_builder_root_returns_configured_path_when_set(tmp_path: Path) -> None:
    assert (
        resolve_builder_root(str(tmp_path / "b"), "ignored")
        == (tmp_path / "b").resolve()
    )


def test_resolve_builder_root_uses_runs_root_subdir_when_configured_is_empty(
    tmp_path: Path,
) -> None:
    assert (
        resolve_builder_root("", str(tmp_path)) == (tmp_path / BUILDER_SUBDIR).resolve()
    )


def test_resolve_builder_root_uses_runs_root_subdir_when_configured_is_blank(
    tmp_path: Path,
) -> None:
    assert (
        resolve_builder_root("   ", str(tmp_path))
        == (tmp_path / BUILDER_SUBDIR).resolve()
    )


# ------------------------------------------------------------------------- layout


def test_init_touches_no_disk_when_constructed(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)

    assert not sandbox.exists()
    assert list(tmp_path.iterdir()) == []


def test_init_places_session_under_user_segment_when_ids_are_plain(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    assert sandbox.path == tmp_path.resolve() / USER_ID / SESSION_ID


def test_init_replaces_unsafe_characters_when_user_id_is_an_email(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox("a/b@x.com", SESSION_ID, root=tmp_path)

    assert sandbox.user_seg == "a_b_x.com"
    assert sandbox.path.parent.parent == tmp_path.resolve()


def test_init_stays_inside_root_when_ids_are_traversal_sequences(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox("..", "..", root=tmp_path)

    assert sandbox.user_seg == "anonymous"
    assert sandbox.session_seg == "session"
    assert sandbox.path.is_relative_to(tmp_path.resolve())


def test_ensure_creates_standard_folders_when_sandbox_is_missing(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    created = sandbox.ensure()

    assert created is True
    assert sandbox.exists()
    for relative in SANDBOX_DIRS:
        assert (sandbox.path / relative).is_dir(), relative
    assert set(SANDBOX_DIRS) == {
        "canvas",
        "workflows",
        "exports",
        "large_tool_results",
        "conversation_history",
        ".tmp",
    }


def test_ensure_returns_false_when_sandbox_already_exists(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.ensure()

    assert sandbox.ensure() is False


def test_ensure_creates_no_git_repository_when_sandbox_is_created(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.ensure()

    assert not any(p.name == ".git" for p in sandbox.path.rglob("*"))


def test_canvas_file_points_into_canvas_folder_when_resolved(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)

    assert sandbox.path_for(CANVAS_FILE) == (
        sandbox.path / "canvas" / "current.workflow.json"
    )


# ------------------------------------------------------------------- containment


def test_path_for_resolves_virtual_path_when_it_has_a_leading_slash(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    assert sandbox.path_for("/workflows/a.workflow.json") == (
        sandbox.path / "workflows" / "a.workflow.json"
    )


def test_path_for_accepts_backslash_separators_when_path_is_inside(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    assert (
        sandbox.path_for("workflows\\a.json") == sandbox.path / "workflows" / "a.json"
    )


@pytest.mark.parametrize(
    "relative",
    ["../escape.txt", "workflows/../../escape.txt", "..\\escape.txt", "/../x"],
)
def test_path_for_raises_when_path_leaves_the_sandbox(
    tmp_path: Path, relative: str
) -> None:
    sandbox = _sandbox(tmp_path)

    with pytest.raises(SandboxPathError):
        sandbox.path_for(relative)


def test_path_for_raises_when_path_reaches_a_sibling_session_by_prefix(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path, session="s1")

    with pytest.raises(SandboxPathError):
        sandbox.path_for("../s1-other/file.txt")


def test_path_for_raises_when_a_symlink_points_outside(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path / "root")
    sandbox.ensure()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(sandbox.path / "exports" / "link", outside)

    with pytest.raises(SandboxPathError):
        sandbox.path_for("exports/link/secret.txt")


def test_init_raises_when_user_folder_is_a_symlink_outside_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(root / USER_ID, outside)

    with pytest.raises(SandboxPathError):
        BuilderSandbox(USER_ID, SESSION_ID, root=root)


def test_call_temp_dir_raises_when_call_folder_is_a_symlink_outside(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path / "root")
    sandbox.ensure()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(sandbox.path / ".tmp" / "call-1", outside)

    with pytest.raises(SandboxPathError):
        sandbox.call_temp_dir("call-1")


# --------------------------------------------------------------------- temp folder


def test_call_temp_dir_creates_folder_under_tmp_when_called(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.ensure()

    folder = sandbox.call_temp_dir("call-1")

    assert folder == sandbox.path / ".tmp" / "call-1"
    assert folder.is_dir()


def test_call_temp_dir_is_idempotent_when_called_twice_with_same_id(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    first = sandbox.call_temp_dir("call-1")
    (first / "keep.txt").write_text("x", encoding="utf-8")

    assert sandbox.call_temp_dir("call-1") == first
    assert (first / "keep.txt").exists()


def test_call_temp_dir_creates_session_folders_when_sandbox_is_missing(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    sandbox.call_temp_dir("call-1")

    assert (sandbox.path / ".tmp" / "call-1").is_dir()


def test_call_temp_dir_sanitizes_the_id_when_it_has_unsafe_characters(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    folder = sandbox.call_temp_dir("../../evil/id")

    assert folder.parent == sandbox.path / ".tmp"
    assert folder.name == "_.._evil_id"


def test_call_temp_dir_uses_fallback_name_when_id_is_empty(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)

    assert sandbox.call_temp_dir("").name == "call"


def test_call_temp_dir_is_left_in_place_when_nothing_removes_it(tmp_path: Path) -> None:
    """The module never deletes on a timer; the script runner removes the folder."""
    sandbox = _sandbox(tmp_path)
    folder = sandbox.call_temp_dir("call-1")
    old = 946684800  # 2000-01-01
    os.utime(folder, (old, old))

    sandbox.ensure()
    sandbox.rebuild(None, None)

    assert folder.is_dir()


# -------------------------------------------------------------------------- rebuild


def test_rebuild_creates_folders_when_there_are_no_revisions(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)

    written = sandbox.rebuild(None, None)

    assert written == []
    for relative in SANDBOX_DIRS:
        assert (sandbox.path / relative).is_dir(), relative


def test_rebuild_writes_draft_named_after_manifest_id_when_id_is_present(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)
    manifest = {"id": "my-flow", "steps": [{"name": "é"}]}

    written = sandbox.rebuild(_Draft(manifest=manifest), None)

    expected = sandbox.path / "workflows" / "my-flow.workflow.json"
    assert written == [expected]
    text = expected.read_text(encoding="utf-8")
    assert json.loads(text) == manifest
    assert text.endswith("\n")
    assert "é" in text  # ensure_ascii=False


@pytest.mark.parametrize("manifest", [{}, {"id": 7}, {"id": ""}, {"id": "..."}])
def test_rebuild_names_draft_file_draft_when_manifest_id_is_unusable(
    tmp_path: Path, manifest: dict[str, Any]
) -> None:
    sandbox = _sandbox(tmp_path)

    written = sandbox.rebuild(_Draft(manifest=manifest), None)

    assert written == [sandbox.path / "workflows" / "draft.workflow.json"]


def test_rebuild_sanitizes_the_file_name_when_manifest_id_has_separators(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    written = sandbox.rebuild(_Draft(manifest={"id": "../../x/y"}), None)

    assert len(written) == 1
    assert written[0].parent == sandbox.path / "workflows"
    assert written[0].name.endswith(".workflow.json")


def test_rebuild_writes_unproposed_revision_to_its_source_file_when_given(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)
    manifest = {"id": "wip", "v": 2}

    written = sandbox.rebuild(
        None, _Draft(manifest=manifest, source_file="/workflows/sub/wip.workflow.json")
    )

    target = sandbox.path / "workflows" / "sub" / "wip.workflow.json"
    assert written == [target]
    assert json.loads(target.read_text(encoding="utf-8")) == manifest


def test_rebuild_returns_draft_first_when_both_revisions_are_given(
    tmp_path: Path,
) -> None:
    sandbox = _sandbox(tmp_path)

    written = sandbox.rebuild(
        _Draft(manifest={"id": "a"}),
        _Draft(manifest={"id": "b"}, source_file="/workflows/b.workflow.json"),
    )

    assert [p.name for p in written] == ["a.workflow.json", "b.workflow.json"]


def test_rebuild_overwrites_existing_file_when_names_match(tmp_path: Path) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.rebuild(_Draft(manifest={"id": "a", "v": 1}), None)

    written = sandbox.rebuild(_Draft(manifest={"id": "a", "v": 2}), None)

    assert json.loads(written[0].read_text(encoding="utf-8")) == {"id": "a", "v": 2}


def test_rebuild_does_not_write_canvas_file_when_called(tmp_path: Path) -> None:
    """The server writes ``canvas/current.workflow.json`` at each turn start."""
    sandbox = _sandbox(tmp_path)

    sandbox.rebuild(_Draft(manifest={"id": "a"}), None)

    assert not sandbox.path_for(CANVAS_FILE).exists()


@pytest.mark.parametrize(
    "source_file",
    [
        None,
        "",
        "/exports/x.json",
        "/canvas/current.workflow.json",
        "/workflows",
        "/workflows/",
        "/workflows/.",
        "/workflows/../exports/x.json",
        "/../escape.json",
    ],
)
def test_rebuild_raises_when_unproposed_source_file_is_not_under_workflows(
    tmp_path: Path, source_file: str | None
) -> None:
    sandbox = _sandbox(tmp_path)

    with pytest.raises(SandboxPathError):
        sandbox.rebuild(None, _Draft(manifest={"id": "a"}, source_file=source_file))


# -------------------------------------------------------------------------- delete


def test_delete_session_removes_only_this_session_when_user_has_two(
    tmp_path: Path,
) -> None:
    first = _sandbox(tmp_path, session="s1")
    second = _sandbox(tmp_path, session="s2")
    first.rebuild(_Draft(manifest={"id": "a"}), None)
    second.ensure()

    assert first.delete_session() is True

    assert not first.exists()
    assert second.exists()


def test_delete_session_returns_true_when_folder_is_already_gone(
    tmp_path: Path,
) -> None:
    assert _sandbox(tmp_path).delete_session() is True


def test_delete_session_retries_once_and_returns_true_when_first_attempt_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.ensure()
    real = sandbox_module.shutil.rmtree
    calls: list[Path] = []

    def flaky(path: Path) -> None:
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("locked")
        real(path)

    monkeypatch.setattr(sandbox_module.shutil, "rmtree", flaky)

    assert sandbox.delete_session() is True
    assert len(calls) == 2
    assert not sandbox.exists()


def test_delete_session_returns_false_without_raising_when_both_attempts_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _sandbox(tmp_path)
    sandbox.ensure()
    calls: list[Path] = []

    def always_fail(path: Path) -> None:
        calls.append(path)
        raise PermissionError("locked")

    monkeypatch.setattr(sandbox_module.shutil, "rmtree", always_fail)

    assert sandbox.delete_session() is False
    assert len(calls) == 2
    assert sandbox.exists()


def test_delete_user_removes_every_session_when_user_has_several(
    tmp_path: Path,
) -> None:
    mine = [_sandbox(tmp_path, session=f"s{i}") for i in range(2)]
    other = _sandbox(tmp_path, user="user-2")
    for sandbox in (*mine, other):
        sandbox.ensure()

    assert BuilderSandbox.delete_user(USER_ID, root=tmp_path) is True

    assert not any(s.exists() for s in mine)
    assert not (tmp_path / USER_ID).exists()
    assert other.exists()


def test_delete_user_returns_true_when_user_has_no_folder(tmp_path: Path) -> None:
    assert BuilderSandbox.delete_user("nobody", root=tmp_path) is True


def test_delete_user_returns_false_without_raising_when_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sandbox(tmp_path).ensure()

    def always_fail(path: Path) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(sandbox_module.shutil, "rmtree", always_fail)

    assert BuilderSandbox.delete_user(USER_ID, root=tmp_path) is False


def test_delete_user_raises_when_user_folder_is_a_symlink_outside_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("x", encoding="utf-8")
    _symlink_or_skip(root / USER_ID, outside)

    with pytest.raises(SandboxPathError):
        BuilderSandbox.delete_user(USER_ID, root=root)

    assert (outside / "keep.txt").exists()
