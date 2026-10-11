"""Tests for .context/ determinism — task 6.9 of sandbox-git-versioning-v2.

These tests verify Requirement 8 acceptance criteria:

  AC 1  A resumed and an uninterrupted execution with the same inputs observe
        byte-identical .context/ files.
  AC 2  A revision inherits the root's design/ and selections.json unchanged;
        the same revision *with* an explicit design selection rewrites them.
  AC 3  A chain install does not touch design/ or selections.json; a resume
        after install re-reads neither the source ref nor the payload.
  AC 4  A source tag swept between the original run and the resume does not
        change what the resumed run sees (resume reads sandbox bytes, not the
        ref).

Tests use a SimpleNamespace sandbox backed by a real tmpdir — no actual Git,
no real DB, no AsyncIO.  The three public functions under test are pure
file-level logic and do not need either.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from app.services.od_context_sandbox import (
    context_already_present,
    rebuild_od_context_from_sandbox,
    write_od_context_to_sandbox,
)


# ---------------------------------------------------------------------------
# Sandbox factory
# ---------------------------------------------------------------------------


def _make_sandbox(tmp_path: Path) -> types.SimpleNamespace:
    """Return a sandbox whose read/write methods are backed by *tmp_path*.

    Mirrors the duck-typed surface that app/services/od_context_sandbox.py probes:
      - ``write(relpath, content: str)``
      - ``read(relpath) -> str | None``
      - ``list_files() -> (list[dict], ...)``
    """
    root = tmp_path

    def write(relpath: str, content: str) -> None:
        dest = root / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    def read(relpath: str) -> str | None:
        p = root / relpath
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def list_files():  # noqa: ANN001 — mirrors real signature
        paths = [
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file()
        ]
        entries = [{"path": p} for p in paths]
        return entries, {}

    return types.SimpleNamespace(write=write, read=read, list_files=list_files)


# ---------------------------------------------------------------------------
# Sample od_context fixture
# ---------------------------------------------------------------------------


_SAMPLE_OD_CONTEXT: dict = {
    "template_id": "tpl-abc",
    "ds_id": "ds-xyz",
    "template_name": "My Template",
    "ds_name": "My Design System",
    "no_template": False,
    "is_design_system_required": True,
    "ds_body": "# Design System\nColor: #123456",
    "craft_block": "## Craft Rules\nKeep it clean.",
    "template_body": "# Template Skill\nDo the thing.",
    "template_files": {
        "assets/template.html": "<html>seed</html>",
        "references/style.md": "# Style notes",
    },
}


def _full_expected_selections(ctx: dict) -> dict:
    return {
        "template_id": ctx.get("template_id"),
        "ds_id": ctx.get("ds_id"),
        "template_name": ctx.get("template_name"),
        "ds_name": ctx.get("ds_name"),
        "no_template": ctx.get("no_template", False),
        "is_design_system_required": ctx.get("is_design_system_required"),
    }


# ---------------------------------------------------------------------------
# AC 1 — A resumed and an uninterrupted execution observe byte-identical files
# ---------------------------------------------------------------------------


class TestResumeBytesIdentical:
    """Resumed run sees byte-identical .context/ to an uninterrupted run.

    The key invariant: write_od_context_to_sandbox + rebuild_od_context_from_sandbox
    is an identity round-trip — what was written is exactly what rebuild reconstructs,
    and writing the same od_context a second time (simulating resume) does not alter
    any file bytes.
    """

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        """write → rebuild round-trips every od_context field exactly."""
        sb = _make_sandbox(tmp_path)

        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        rebuilt = rebuild_od_context_from_sandbox(sb)

        assert rebuilt is not None
        assert rebuilt["template_id"] == _SAMPLE_OD_CONTEXT["template_id"]
        assert rebuilt["ds_id"] == _SAMPLE_OD_CONTEXT["ds_id"]
        assert rebuilt["template_name"] == _SAMPLE_OD_CONTEXT["template_name"]
        assert rebuilt["ds_name"] == _SAMPLE_OD_CONTEXT["ds_name"]
        assert rebuilt["no_template"] == _SAMPLE_OD_CONTEXT["no_template"]
        assert (
            rebuilt["is_design_system_required"]
            == _SAMPLE_OD_CONTEXT["is_design_system_required"]
        )
        assert rebuilt["ds_body"] == _SAMPLE_OD_CONTEXT["ds_body"]
        assert rebuilt["craft_block"] == _SAMPLE_OD_CONTEXT["craft_block"]
        assert rebuilt["template_body"] == _SAMPLE_OD_CONTEXT["template_body"]

    def test_round_trip_preserves_template_files(self, tmp_path: Path) -> None:
        """write → rebuild reconstructs template_files including nested paths."""
        sb = _make_sandbox(tmp_path)

        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        rebuilt = rebuild_od_context_from_sandbox(sb)

        assert rebuilt is not None
        tf = rebuilt.get("template_files") or {}
        for rel, content in _SAMPLE_OD_CONTEXT["template_files"].items():
            assert rel in tf, f"template_files missing key {rel!r}"
            assert (
                tf[rel] == content
            ), f"template_files[{rel!r}] does not match: {tf[rel]!r} != {content!r}"

    def test_resume_does_not_change_file_bytes(self, tmp_path: Path) -> None:
        """A second write call (simulating resume) must not alter any file.

        The inheritance guard fires when .context/ is already present and
        explicit_selection is False, so the bytes written by the first call
        survive untouched.
        """
        sb = _make_sandbox(tmp_path)
        root = tmp_path

        # First write (original run).
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)

        # Snapshot every .context/ file before the simulated resume.
        def _snapshot() -> dict[str, bytes]:
            return {
                str(p.relative_to(root)).replace("\\", "/"): p.read_bytes()
                for p in root.rglob("*")
                if p.is_file() and ".context" in str(p)
            }

        before = _snapshot()
        assert before  # sanity check — files were actually written

        # Second write (resume, same od_context, no explicit_selection).
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT, explicit_selection=False)

        after = _snapshot()

        assert before == after, (
            "Resume altered .context/ file bytes even though no explicit_selection "
            "was supplied. The inheritance guard must prevent any overwrite."
        )

    def test_rebuild_after_resume_is_identical_to_original(
        self, tmp_path: Path
    ) -> None:
        """rebuild_od_context_from_sandbox after a resume returns the same dict."""
        sb = _make_sandbox(tmp_path)

        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        after_original = rebuild_od_context_from_sandbox(sb)

        # Simulate resume write attempt.
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT, explicit_selection=False)
        after_resume = rebuild_od_context_from_sandbox(sb)

        # The rebuilt dicts must be equal (same bytes → same parse result).
        assert after_original == after_resume, (
            "rebuild_od_context_from_sandbox returned different data after resume "
            "compared to after the original write.  Resume must be byte-identical."
        )

    def test_selections_json_is_valid_json_and_stable(self, tmp_path: Path) -> None:
        """selections.json is valid JSON and does not change across two writes."""
        sb = _make_sandbox(tmp_path)

        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        first = (tmp_path / ".context" / "selections.json").read_text(encoding="utf-8")

        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT, explicit_selection=False)
        second = (tmp_path / ".context" / "selections.json").read_text(encoding="utf-8")

        # Must parse as JSON.
        parsed = json.loads(first)
        assert isinstance(parsed, dict)

        # Must not change on resume.
        assert first == second


# ---------------------------------------------------------------------------
# AC 2 — Revision inheritance and explicit-selection override
# ---------------------------------------------------------------------------


class TestRevisionInheritance:
    """A revision shares .context/ with the root; explicit_selection rewrites it."""

    def test_revision_inherits_root_selections_unchanged(self, tmp_path: Path) -> None:
        """A revision write with no explicit_selection leaves the root's files intact.

        The root run writes first; the revision call is a no-op because
        context_already_present returns True and explicit_selection is False.
        """
        sb = _make_sandbox(tmp_path)

        # Root run writes its design inputs.
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        root_selections = (tmp_path / ".context" / "selections.json").read_bytes()
        root_design_system = (
            tmp_path / ".context" / "design" / "design-system.md"
        ).read_bytes()

        # Revision run does NOT supply an explicit_selection.
        revision_ctx = dict(_SAMPLE_OD_CONTEXT)
        revision_ctx["template_id"] = "tpl-DIFFERENT"
        write_od_context_to_sandbox(sb, revision_ctx, explicit_selection=False)

        # Files must be unchanged.
        assert (
            tmp_path / ".context" / "selections.json"
        ).read_bytes() == root_selections
        assert (
            tmp_path / ".context" / "design" / "design-system.md"
        ).read_bytes() == root_design_system

        # And the template_id in selections must still be the ROOT's value.
        sel = json.loads(
            (tmp_path / ".context" / "selections.json").read_text(encoding="utf-8")
        )
        assert sel["template_id"] == _SAMPLE_OD_CONTEXT["template_id"], (
            "selections.json was overwritten by the revision even though no "
            "explicit_selection was supplied."
        )

    def test_revision_with_explicit_selection_rewrites_design_inputs(
        self, tmp_path: Path
    ) -> None:
        """A revision write with explicit_selection=True overwrites the inherited files.

        This is the one legitimate override path: the user chose a new template
        or design system on the revision launch form.
        """
        sb = _make_sandbox(tmp_path)

        # Root run.
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        root_ds = (tmp_path / ".context" / "design" / "design-system.md").read_bytes()

        # Revision with a deliberately different design system and explicit_selection.
        new_ctx = dict(_SAMPLE_OD_CONTEXT)
        new_ctx["ds_body"] = "# REVISED Design System\nNew color: #FFFFFF"
        write_od_context_to_sandbox(sb, new_ctx, explicit_selection=True)

        revised_ds = (
            tmp_path / ".context" / "design" / "design-system.md"
        ).read_bytes()
        assert (
            revised_ds != root_ds
        ), "design-system.md was NOT updated despite explicit_selection=True."
        assert b"REVISED Design System" in revised_ds

        # selections.json must also reflect the new context.
        sel = json.loads(
            (tmp_path / ".context" / "selections.json").read_text(encoding="utf-8")
        )
        assert sel["ds_id"] == new_ctx["ds_id"]

    def test_context_already_present_returns_false_for_empty_sandbox(
        self, tmp_path: Path
    ) -> None:
        """context_already_present is False before any write."""
        sb = _make_sandbox(tmp_path)
        assert context_already_present(sb) is False

    def test_context_already_present_returns_true_after_write(
        self, tmp_path: Path
    ) -> None:
        """context_already_present is True after write_od_context_to_sandbox."""
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)
        assert context_already_present(sb) is True

    def test_none_sandbox_is_not_present(self) -> None:
        """context_already_present returns False for a None sandbox (duck-type guard)."""
        assert context_already_present(None) is False

    def test_no_op_write_does_not_create_context(self, tmp_path: Path) -> None:
        """write_od_context_to_sandbox with None od_context is a complete no-op."""
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, None)
        assert not (tmp_path / ".context").exists()
        assert context_already_present(sb) is False


# ---------------------------------------------------------------------------
# AC 3 — Chain install must not touch design/ or selections.json
# ---------------------------------------------------------------------------


class TestChainInstallDoesNotTouchDesignFiles:
    """Chain payload install writes only the three flat .context/ root files.

    The chain_context provider writes ``logs.jsonl``, ``summary.md``, and the
    output basename to ``.context/`` using ``_atomic_write_context_dir``.  It
    must NOT overwrite ``design/`` or ``selections.json``.

    We test this by calling ``_atomic_write_context_dir`` directly on a
    directory that already contains selections.json and design/, then asserting
    those files are untouched.
    """

    def test_atomic_write_context_dir_preserves_sibling_files(
        self, tmp_path: Path
    ) -> None:
        """_atomic_write_context_dir only writes its own files; siblings survive.

        This mirrors what the chain install path does: it calls
        _atomic_write_context_dir on the .context/ directory and passes only
        the three chain flat-file bytes.  The design/ subtree and selections.json
        are siblings that must survive.
        """
        from agents.capabilities.context_providers.chain_context import (
            _atomic_write_context_dir,
        )

        context_dir = tmp_path / ".context"

        # Pre-condition: design inputs from the OD run exist.
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)

        assert (context_dir / "selections.json").exists()
        assert (context_dir / "design" / "design-system.md").exists()

        sel_before = (context_dir / "selections.json").read_bytes()
        design_before = (context_dir / "design" / "design-system.md").read_bytes()

        # The chain install writes ONLY the three chain payload flat files.
        chain_files = {
            "logs.jsonl": b'{"event": "done"}\n',
            "summary.md": b"schema_version: 2\n",
            "prototype.html": b"<html/>",
        }
        _atomic_write_context_dir(context_dir, chain_files)

        # Chain flat files must be written.
        assert (context_dir / "logs.jsonl").read_bytes() == chain_files["logs.jsonl"]
        assert (context_dir / "summary.md").read_bytes() == chain_files["summary.md"]
        assert (context_dir / "prototype.html").read_bytes() == chain_files[
            "prototype.html"
        ]

        # Design inputs must still be present and byte-identical — the chain
        # install must not blow away the whole directory (BUG-126 / B24 fix).
        assert (
            context_dir / "selections.json"
        ).exists(), "selections.json was destroyed by _atomic_write_context_dir — BUG-126 regression"
        assert (
            (context_dir / "selections.json").read_bytes() == sel_before
        ), "selections.json was modified by _atomic_write_context_dir — BUG-126 regression"
        assert (
            context_dir / "design" / "design-system.md"
        ).exists(), "design/design-system.md was destroyed by _atomic_write_context_dir — BUG-126 regression"
        assert (
            (context_dir / "design" / "design-system.md").read_bytes() == design_before
        ), "design/design-system.md was modified by _atomic_write_context_dir — BUG-126 regression"

    def test_chain_payload_files_are_at_context_root_not_in_subdir(
        self, tmp_path: Path
    ) -> None:
        """Chain payload files land at .context/ root, never in a subdirectory.

        The three flat files are logs.jsonl, summary.md, and the output basename.
        They must NOT be nested like .context/design/logs.jsonl.
        """
        from agents.capabilities.context_providers.chain_context import (
            _atomic_write_context_dir,
        )

        context_dir = tmp_path / ".context"
        context_dir.mkdir(parents=True, exist_ok=True)

        chain_files = {
            "logs.jsonl": b"{}",
            "summary.md": b"schema_version: 2",
            "output.html": b"<html/>",
        }
        _atomic_write_context_dir(context_dir, chain_files)

        # Files must exist at the root, not in a subdirectory.
        for name in chain_files:
            assert (context_dir / name).exists(), (
                f"Chain file {name!r} not found at .context/ root — "
                "it must not be nested in a subdirectory."
            )

        # No subdirectory is created.
        subdirs = [p for p in context_dir.iterdir() if p.is_dir()]
        assert (
            not subdirs
        ), f"_atomic_write_context_dir created unexpected subdirectory/ies: {subdirs}"

    def test_resume_after_chain_install_does_not_re_read_source_ref(
        self, tmp_path: Path
    ) -> None:
        """Resume reads sandbox bytes; the source ref is never consulted again.

        The resume path calls rebuild_od_context_from_sandbox to reconstruct
        od_context from the .context/ files on disk.  It does NOT open the
        source sandbox, call read_bytes_at_ref, or contact the source ref in any
        way.  This test verifies that rebuild_od_context_from_sandbox reads only
        the local sandbox files.

        We simulate a "swept source tag" by checking that rebuild works perfectly
        even when no source sandbox or runner exists — only the local tmpdir.
        """
        sb = _make_sandbox(tmp_path)

        # Write od_context (original run).
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)

        # "Sweep" the source (simulated by: there is no runner, no source ref,
        # no external network — only the local sandbox).  rebuild must still work.
        rebuilt = rebuild_od_context_from_sandbox(sb)

        assert rebuilt is not None, (
            "rebuild_od_context_from_sandbox returned None — it must read from "
            "the local sandbox only, not from any source ref or runner."
        )
        assert rebuilt["template_id"] == _SAMPLE_OD_CONTEXT["template_id"]
        assert rebuilt["ds_body"] == _SAMPLE_OD_CONTEXT["ds_body"]


# ---------------------------------------------------------------------------
# AC 4 — Swept source tag does not affect what resume sees
# ---------------------------------------------------------------------------


class TestSweptSourceTagDoesNotAffectResume:
    """A swept source tag must not alter the resumed run's .context/ view.

    The resumed run reads from the local sandbox files, not from a source ref.
    So even if the source sandbox is deleted, GC'd, or its tag removed, the
    bytes the resumed run sees are unchanged.
    """

    def test_rebuild_succeeds_after_source_would_be_swept(self, tmp_path: Path) -> None:
        """rebuild works when the 'source' directory no longer exists.

        We write context to sandbox A, then attempt a rebuild from sandbox A
        while sandbox B (the "source") is deleted entirely.  rebuild_od_context_from_sandbox
        must not reference sandbox B at all.
        """
        receiving_sb = _make_sandbox(tmp_path / "receiving")

        # Simulate: chain payload was copied into receiving sandbox at install time.
        # The od_context was written before agent 1.
        write_od_context_to_sandbox(receiving_sb, _SAMPLE_OD_CONTEXT)

        # The source sandbox (tmp_path / "source") never exists in this test,
        # simulating a swept tag.  rebuild must be entirely local.
        rebuilt = rebuild_od_context_from_sandbox(receiving_sb)
        assert rebuilt is not None
        assert rebuilt["template_id"] == _SAMPLE_OD_CONTEXT["template_id"]
        assert rebuilt["ds_body"] == _SAMPLE_OD_CONTEXT["ds_body"]
        assert rebuilt["craft_block"] == _SAMPLE_OD_CONTEXT["craft_block"]

    def test_context_files_unchanged_when_source_deleted(self, tmp_path: Path) -> None:
        """The .context/ bytes on disk are not affected by source sandbox deletion.

        Byte-for-byte: snapshot the files, delete the source, re-read the files,
        compare.
        """
        receiving_dir = tmp_path / "receiving"
        source_dir = tmp_path / "source"
        source_dir.mkdir(parents=True)
        (source_dir / "dummy.txt").write_text("source content", encoding="utf-8")

        receiving_sb = _make_sandbox(receiving_dir)
        write_od_context_to_sandbox(receiving_sb, _SAMPLE_OD_CONTEXT)

        # Snapshot files in receiving sandbox before source deletion.
        context_root = receiving_dir / ".context"
        before = {
            str(p.relative_to(receiving_dir)).replace("\\", "/"): p.read_bytes()
            for p in context_root.rglob("*")
            if p.is_file()
        }
        assert before  # sanity check

        # Delete the source.
        import shutil

        shutil.rmtree(str(source_dir))
        assert not source_dir.exists()

        # Re-read the receiving sandbox files.
        after = {
            str(p.relative_to(receiving_dir)).replace("\\", "/"): p.read_bytes()
            for p in context_root.rglob("*")
            if p.is_file()
        }

        assert (
            before == after
        ), "Deleting the source sandbox altered the receiving sandbox's .context/ bytes."

    def test_rebuild_after_source_sweep_returns_same_data(self, tmp_path: Path) -> None:
        """rebuild_od_context_from_sandbox returns identical data before and after source sweep."""
        source_dir = tmp_path / "source"
        source_dir.mkdir(parents=True)
        (source_dir / "summary.md").write_text("schema_version: 2", encoding="utf-8")

        receiving_sb = _make_sandbox(tmp_path / "receiving")
        write_od_context_to_sandbox(receiving_sb, _SAMPLE_OD_CONTEXT)

        before = rebuild_od_context_from_sandbox(receiving_sb)

        # "Sweep" source.
        import shutil

        shutil.rmtree(str(source_dir))

        after = rebuild_od_context_from_sandbox(receiving_sb)

        assert before == after, (
            "rebuild_od_context_from_sandbox returned different data after "
            "source sweep.  Resume must read only local sandbox files."
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Miscellaneous edge and boundary cases for the three public functions."""

    def test_rebuild_returns_none_for_empty_sandbox(self, tmp_path: Path) -> None:
        """rebuild_od_context_from_sandbox returns None when no .context/ exists."""
        sb = _make_sandbox(tmp_path)
        assert rebuild_od_context_from_sandbox(sb) is None

    def test_rebuild_returns_none_for_none_sandbox(self) -> None:
        """rebuild_od_context_from_sandbox returns None for a None sandbox."""
        assert rebuild_od_context_from_sandbox(None) is None

    def test_write_is_no_op_for_none_od_context(self, tmp_path: Path) -> None:
        """write_od_context_to_sandbox with None od_context writes nothing."""
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, None)
        assert not (tmp_path / ".context").exists()

    def test_write_is_no_op_for_empty_od_context(self, tmp_path: Path) -> None:
        """write_od_context_to_sandbox with an empty dict writes nothing."""
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, {})
        assert not (tmp_path / ".context").exists()

    def test_context_already_present_is_false_when_only_design_exists(
        self, tmp_path: Path
    ) -> None:
        """context_already_present is False when design/ exists but selections.json absent.

        selections.json is the sentinel file.  Its absence means context is not
        fully written, even if other files are present.
        """
        sb = _make_sandbox(tmp_path)
        # Write design/ but skip selections.json (partial/broken write simulation).
        sb.write(".context/design/design-system.md", "# DS")
        assert context_already_present(sb) is False

    def test_write_minimal_od_context_no_template_files(self, tmp_path: Path) -> None:
        """A minimal od_context with only selections fields writes only selections.json."""
        sb = _make_sandbox(tmp_path)
        minimal_ctx = {
            "template_id": None,
            "ds_id": None,
            "template_name": None,
            "ds_name": None,
            "no_template": True,
            "is_design_system_required": False,
        }
        write_od_context_to_sandbox(sb, minimal_ctx)

        # selections.json must exist.
        assert (tmp_path / ".context" / "selections.json").exists()

        # No design files since ds_body / craft_block / template_body are absent.
        assert not (tmp_path / ".context" / "design").exists()

        # context_already_present must be True.
        assert context_already_present(sb) is True

    def test_selections_json_fields_match_expected_shape(self, tmp_path: Path) -> None:
        """selections.json contains exactly the expected keys from od_context."""
        sb = _make_sandbox(tmp_path)
        write_od_context_to_sandbox(sb, _SAMPLE_OD_CONTEXT)

        sel_raw = (tmp_path / ".context" / "selections.json").read_text(
            encoding="utf-8"
        )
        sel = json.loads(sel_raw)

        expected = _full_expected_selections(_SAMPLE_OD_CONTEXT)
        assert sel == expected, (
            f"selections.json shape mismatch.\n"
            f"Got:      {sel}\n"
            f"Expected: {expected}"
        )

    def test_multiple_template_files_all_round_trip(self, tmp_path: Path) -> None:
        """All template_files entries survive the write → rebuild round-trip."""
        sb = _make_sandbox(tmp_path)
        ctx = dict(_SAMPLE_OD_CONTEXT)
        ctx["template_files"] = {
            "assets/template.html": "<html>T</html>",
            "references/style.md": "# style",
            "references/motion.md": "# motion",
        }
        write_od_context_to_sandbox(sb, ctx)
        rebuilt = rebuild_od_context_from_sandbox(sb)

        assert rebuilt is not None
        tf = rebuilt.get("template_files") or {}
        for rel, content in ctx["template_files"].items():
            assert rel in tf, f"Missing template_files key {rel!r} after rebuild."
            assert tf[rel] == content

    def test_explicit_selection_false_is_default_behavior(self, tmp_path: Path) -> None:
        """explicit_selection=False is the same as omitting the parameter."""
        sb1 = _make_sandbox(tmp_path / "sb1")
        sb2 = _make_sandbox(tmp_path / "sb2")

        write_od_context_to_sandbox(sb1, _SAMPLE_OD_CONTEXT, explicit_selection=False)
        write_od_context_to_sandbox(sb2, _SAMPLE_OD_CONTEXT)

        context1 = tmp_path / "sb1" / ".context"
        context2 = tmp_path / "sb2" / ".context"

        files1 = {
            str(p.relative_to(context1)).replace("\\", "/"): p.read_bytes()
            for p in context1.rglob("*")
            if p.is_file()
        }
        files2 = {
            str(p.relative_to(context2)).replace("\\", "/"): p.read_bytes()
            for p in context2.rglob("*")
            if p.is_file()
        }
        assert (
            files1 == files2
        ), "explicit_selection=False produced different files from the default."
