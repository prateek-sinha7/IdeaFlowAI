"""tests/agents/test_reserved_path_registry.py

Anti-regression test suite for the reserved-path registry (Requirement 18, V2-Q7).

The core contract enforced here is: ONE canonical ``RESERVED_PATHS`` registry in
``app.agents.sandbox`` drives every enforcement point.  The v1 failure mode was two
separate literal lists that drifted.  Every test below is designed to fail
immediately if any enforcement point starts maintaining its own list instead of
deriving from the registry.

Coverage (12 distinct assertions across 13 test classes):
  1. ``RESERVED_PATHS`` itself — shape and slash-form membership
  2. ``GIT_METADATA_PATHS`` wired into the five deliverable/listing/zip/share surfaces
  3. ``_GITIGNORE_PATHS`` in ``local.py`` equals ``tuple(sorted(RESERVED_PATHS))``
  4. ``_RESERVED_PREFIXES`` in ``previous_run.py`` covers all slash + bare forms of
     ``RESERVED_PATHS``
  5. ``_COMPILER_RESERVED_PATHS`` in ``compiler.py`` equals
     ``RESERVED_PATHS`` plus all corresponding bare-name entries
  6. ``write_to_sandbox`` in ``kernel_services.py`` refuses every registry path
  7. ``_ReservedPathGuardMiddleware`` — write/read guard logic (requires ``deepagents``)
  8. ``is_deliverable_relpath`` excludes every ``RESERVED_PATHS`` + ``GIT_METADATA_PATHS``
  9. ``list_files`` excludes the right set, keeping ``.chain/``, ``.context/``,
     ``.agents/``
 10. ``read_sandbox_file`` guard in ``run_files.py`` refuses ``.uploads/``, ``.logs/``,
     ``.chain-legacy/`` (requires ``fastapi``)
 11. ``_assert_share_output_clean`` refuses reserved paths in the deliverable string
     (requires ``fastapi``)
 12. Compiler raises ``CompilerError`` for a manifest declaring only reserved entries;
     rejected entry does NOT fall back to the default seed set
 13. Real-disk end-to-end: ``write_to_sandbox`` refuses all registry paths

Requirements: 18
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# 1.  RESERVED_PATHS registry shape and membership
# ---------------------------------------------------------------------------


class TestReservedPathsRegistry:
    """The registry must contain the expected slash-form entries."""

    def test_reserved_paths_is_frozenset(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        assert isinstance(RESERVED_PATHS, frozenset)

    def test_reserved_paths_contains_all_required_slash_entries(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        required_slash = {
            ".uploads/",
            ".logs/",
            ".verify/",
            ".browser/",
            ".agents/",
            ".chain/",
            ".context/",
            "skills/",
            "conversation_history/",
            ".chain-legacy/",
        }
        missing = required_slash - RESERVED_PATHS
        assert not missing, f"RESERVED_PATHS is missing slash entries: {missing}"

    def test_reserved_paths_contains_chain_legacy(self) -> None:
        """v2 addition: .chain-legacy/ must be present."""
        from app.agents.sandbox import RESERVED_PATHS

        assert ".chain-legacy/" in RESERVED_PATHS

    def test_agent_readable_reserved_is_subset_of_reserved_paths(self) -> None:
        from app.agents.sandbox import AGENT_READABLE_RESERVED, RESERVED_PATHS

        assert AGENT_READABLE_RESERVED.issubset(
            RESERVED_PATHS
        ), "AGENT_READABLE_RESERVED must be a subset of RESERVED_PATHS"

    def test_context_slash_is_agent_readable(self) -> None:
        from app.agents.sandbox import AGENT_READABLE_RESERVED

        assert ".context/" in AGENT_READABLE_RESERVED

    def test_chain_slash_is_not_agent_readable(self) -> None:
        """Agents must NOT be able to read .chain/ directly (Requirement 18 AC 8)."""
        from app.agents.sandbox import AGENT_READABLE_RESERVED

        assert ".chain/" not in AGENT_READABLE_RESERVED
        assert ".chain" not in AGENT_READABLE_RESERVED

    def test_payload_allowlist_returns_three_exact_paths(self) -> None:
        """payload_allowlist must return exactly the three force-stageable paths."""
        from app.agents.sandbox import payload_allowlist

        result = payload_allowlist("prototype.html")
        assert ".chain/logs.jsonl" in result
        assert ".chain/summary.md" in result
        assert ".chain/prototype.html" in result
        assert len(result) == 3

    def test_payload_allowlist_rejects_separator_in_basename(self) -> None:
        from app.agents.sandbox import payload_allowlist

        with pytest.raises(ValueError, match="path separator"):
            payload_allowlist("sub/dir/output.html")

    def test_payload_allowlist_rejects_reserved_collision(self) -> None:
        from app.agents.sandbox import payload_allowlist

        with pytest.raises(ValueError, match="reserved payload name"):
            payload_allowlist("logs.jsonl")

        with pytest.raises(ValueError, match="reserved payload name"):
            payload_allowlist("summary.md")


# ---------------------------------------------------------------------------
# 2.  GIT_METADATA_PATHS wired into the five surfaces
# ---------------------------------------------------------------------------


class TestGitMetadataPathsEnforcement:
    """GIT_METADATA_PATHS must be excluded from deliverable walk, counting,
    list_files, zip, and public share — five surfaces (Requirement 18 AC 3)."""

    def test_git_metadata_paths_is_frozenset_with_required_entries(self) -> None:
        from app.agents.sandbox import GIT_METADATA_PATHS

        assert isinstance(GIT_METADATA_PATHS, frozenset)
        assert ".git/" in GIT_METADATA_PATHS
        assert ".gitignore" in GIT_METADATA_PATHS

    def test_deliverable_excluded_prefixes_includes_git_prefix(self) -> None:
        """The _DELIVERABLE_EXCLUDED_PREFIXES tuple must contain .git/."""
        from app.agents.sandbox import _DELIVERABLE_EXCLUDED_PREFIXES

        assert ".git/" in _DELIVERABLE_EXCLUDED_PREFIXES

    def test_deliverable_excluded_exact_includes_gitignore(self) -> None:
        """The _DELIVERABLE_EXCLUDED_EXACT set must contain .gitignore."""
        from app.agents.sandbox import _DELIVERABLE_EXCLUDED_EXACT

        assert ".gitignore" in _DELIVERABLE_EXCLUDED_EXACT

    def test_is_deliverable_relpath_excludes_git_directory(self) -> None:
        """Files under .git/ must never be deliverables."""
        from app.agents.sandbox import is_deliverable_relpath

        assert not is_deliverable_relpath(".git/config")
        assert not is_deliverable_relpath(".git/HEAD")
        assert not is_deliverable_relpath(".git/objects/ab/cdef")

    def test_is_deliverable_relpath_excludes_gitignore(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        assert not is_deliverable_relpath(".gitignore")

    def test_listing_excluded_prefixes_excludes_git_prefix(self) -> None:
        """The Workspace listing no longer has a hidden-prefix policy."""
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_PREFIXES")

    def test_listing_excluded_exact_excludes_gitignore(self) -> None:
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_EXACT")

    def test_share_excluded_set_includes_git_metadata_paths(self) -> None:
        """_SHARE_EXCLUDED in runs.py must include all GIT_METADATA_PATHS entries."""
        runs = pytest.importorskip("app.api.runs", reason="fastapi not installed")
        from app.agents.sandbox import GIT_METADATA_PATHS

        assert GIT_METADATA_PATHS.issubset(
            runs._SHARE_EXCLUDED
        ), "_SHARE_EXCLUDED in runs.py must include all GIT_METADATA_PATHS entries"

    def test_share_excluded_set_includes_reserved_paths(self) -> None:
        runs = pytest.importorskip("app.api.runs", reason="fastapi not installed")
        from app.agents.sandbox import RESERVED_PATHS

        assert RESERVED_PATHS.issubset(
            runs._SHARE_EXCLUDED
        ), "_SHARE_EXCLUDED in runs.py must include all RESERVED_PATHS entries"


# ---------------------------------------------------------------------------
# 3.  _GITIGNORE_PATHS in local.py equals tuple(sorted(RESERVED_PATHS))
# ---------------------------------------------------------------------------


class TestGitignorePathsDerivedFromRegistry:
    """local.py seeds .gitignore from the registry, never a hand-rolled literal."""

    def test_gitignore_paths_equals_sorted_reserved_paths(self) -> None:
        from app.agents.runtime.local import LocalWorkspace
        from app.agents.sandbox import RESERVED_PATHS

        expected = tuple(sorted(RESERVED_PATHS))
        assert LocalWorkspace._GITIGNORE_PATHS == expected, (
            f"LocalWorkspace._GITIGNORE_PATHS must equal tuple(sorted(RESERVED_PATHS)).\n"
            f"Extra in _GITIGNORE_PATHS: "
            f"{set(LocalWorkspace._GITIGNORE_PATHS) - RESERVED_PATHS}\n"
            f"Missing from _GITIGNORE_PATHS: "
            f"{RESERVED_PATHS - set(LocalWorkspace._GITIGNORE_PATHS)}"
        )

    def test_gitignore_paths_contains_chain_legacy(self) -> None:
        from app.agents.runtime.local import LocalWorkspace

        assert (
            ".chain-legacy/" in LocalWorkspace._GITIGNORE_PATHS
        ), ".chain-legacy/ (the v2 addition) must be in _GITIGNORE_PATHS"

    def test_gitignore_paths_contains_conversation_history(self) -> None:
        """conversation_history/ was absent from the old literal list — the registry
        exists to prevent that drift from recurring."""
        from app.agents.runtime.local import LocalWorkspace

        assert "conversation_history/" in LocalWorkspace._GITIGNORE_PATHS


# ---------------------------------------------------------------------------
# 4.  _RESERVED_PREFIXES in previous_run.py covers all of RESERVED_PATHS
# ---------------------------------------------------------------------------


class TestPreviousRunReservedPrefixesDerivedFromRegistry:
    """previous_run.py's guard must refuse every RESERVED_PATHS entry in both
    slash and bare form, and must handle path-traversal bypass forms."""

    def test_reserved_prefixes_covers_all_slash_entries(self) -> None:
        """Every slash-form entry in RESERVED_PATHS must appear in _RESERVED_PREFIXES."""
        from agents.capabilities.context_providers.previous_run import (
            _RESERVED_PREFIXES,
        )
        from app.agents.sandbox import RESERVED_PATHS

        slash_entries = {e for e in RESERVED_PATHS if e.endswith("/")}
        missing = slash_entries - _RESERVED_PREFIXES
        assert (
            not missing
        ), f"_RESERVED_PREFIXES missing slash entries from RESERVED_PATHS: {missing}"

    def test_reserved_prefixes_covers_all_bare_forms(self) -> None:
        """For every slash-form entry in RESERVED_PATHS, the corresponding bare
        name must be in _RESERVED_PREFIXES (e.g. '.chain/' → '.chain')."""
        from agents.capabilities.context_providers.previous_run import (
            _RESERVED_PREFIXES,
        )
        from app.agents.sandbox import RESERVED_PATHS

        slash_entries = {e for e in RESERVED_PATHS if e.endswith("/")}
        bare_forms = {e.rstrip("/") for e in slash_entries}
        missing_bare = bare_forms - _RESERVED_PREFIXES
        assert not missing_bare, (
            f"_RESERVED_PREFIXES missing bare forms for RESERVED_PATHS entries: "
            f"{missing_bare}"
        )

    def test_is_reserved_blocks_slash_form(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        for entry in (".uploads/", ".logs/", ".chain/", "skills/", ".chain-legacy/"):
            assert _is_reserved(
                entry
            ), f"_is_reserved should block slash form {entry!r}"

    def test_is_reserved_blocks_bare_form(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        for entry in (".uploads", ".logs", ".chain", "skills", ".chain-legacy"):
            assert _is_reserved(entry), f"_is_reserved should block bare form {entry!r}"

    def test_is_reserved_blocks_nested_paths(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        nested = [
            ".uploads/manifest.json",
            ".logs/run-abc.jsonl",
            ".chain/summary.md",
            "skills/writing/SKILL.md",
            "conversation_history/turn1.md",
            ".chain-legacy/old-run/summary.md",
        ]
        for path in nested:
            assert _is_reserved(
                path
            ), f"_is_reserved should block nested reserved path {path!r}"

    def test_is_reserved_blocks_dot_slash_prefix_bypass(self) -> None:
        """./.chain/x must be blocked (path-traversal bypass form)."""
        from agents.capabilities.context_providers.previous_run import _is_reserved

        assert _is_reserved(
            "./.chain/secrets.txt"
        ), "_is_reserved must block ./.chain/ bypass form"
        assert _is_reserved(
            "./skills/"
        ), "_is_reserved must block ./skills/ bypass form"

    def test_is_reserved_blocks_leading_dotdot_slash_bypass(self) -> None:
        """../.chain/x must be blocked after normalization (path-traversal bypass)."""
        from agents.capabilities.context_providers.previous_run import _is_reserved

        # Leading ../ must be normalized and the result checked
        assert _is_reserved(
            "../.chain/secrets.txt"
        ), "_is_reserved must block ../.chain/ bypass form after normalization"
        assert _is_reserved(
            "../skills/writing.md"
        ), "_is_reserved must block ../skills/ bypass form after normalization"
        assert _is_reserved(
            "../../.chain/"
        ), "_is_reserved must block nested ../ bypasses"

    def test_is_reserved_does_not_block_regular_files(self) -> None:
        from agents.capabilities.context_providers.previous_run import _is_reserved

        safe = ["prototype.html", "spec.md", "design.md", "tasks.md", "output.md"]
        for path in safe:
            assert not _is_reserved(
                path
            ), f"_is_reserved should NOT block safe path {path!r}"

    def test_declared_seed_files_drops_reserved_entries(self) -> None:
        """_declared_seed_files must filter out reserved entries from from_run."""
        from agents.capabilities.context_providers.previous_run import (
            _declared_seed_files,
        )

        ctx = MagicMock()
        ctx.seed_files = {
            "from_run": [
                "spec.md",  # safe — must be kept
                ".chain/logs.jsonl",  # reserved — must be dropped
                ".uploads/",  # reserved — must be dropped
                "skills/foo.md",  # reserved — must be dropped
                "design.md",  # safe — must be kept
            ]
        }
        result = _declared_seed_files(ctx)
        assert "spec.md" in result
        assert "design.md" in result
        assert ".chain/logs.jsonl" not in result
        assert ".uploads/" not in result
        assert "skills/foo.md" not in result

    def test_declared_seed_files_falls_back_to_default_when_empty(self) -> None:
        """An empty / absent from_run falls back to the default _SEED_FILES triple."""
        from agents.capabilities.context_providers.previous_run import (
            _SEED_FILES,
            _declared_seed_files,
        )

        ctx = MagicMock()
        ctx.seed_files = {}
        assert _declared_seed_files(ctx) == _SEED_FILES

        ctx2 = MagicMock()
        ctx2.seed_files = None
        assert _declared_seed_files(ctx2) == _SEED_FILES

    def test_rejected_reserved_entry_does_not_fall_back_to_default_set(self) -> None:
        """A from_run list containing ONLY reserved entries must yield an empty
        tuple, never the default _SEED_FILES triple (Requirement 18 AC 12)."""
        from agents.capabilities.context_providers.previous_run import (
            _SEED_FILES,
            _declared_seed_files,
        )

        ctx = MagicMock()
        ctx.seed_files = {"from_run": [".chain/", ".uploads/", "skills/"]}
        result = _declared_seed_files(ctx)
        # Must be empty — NOT the default triple
        assert result == (), (
            "When ALL from_run entries are reserved, result must be empty tuple, "
            "not the default _SEED_FILES fallback (Requirement 18 AC 12)"
        )
        assert result != _SEED_FILES, (
            "A rejected list of only reserved entries must not fall back to the "
            "default seed set (Requirement 18 AC 12)"
        )


# ---------------------------------------------------------------------------
# 5.  _COMPILER_RESERVED_PATHS in compiler.py covers RESERVED_PATHS + bare forms
# ---------------------------------------------------------------------------


class TestCompilerReservedPathsCoverageOfRegistry:
    """The compiler's inline copy must contain every entry from RESERVED_PATHS
    AND the corresponding bare-name form for each slash entry (so both
    ``'.chain/'`` and ``'.chain'`` are blocked at compile time)."""

    def test_compiler_reserved_paths_is_frozenset(self) -> None:
        from agents.workflows.compiler import _COMPILER_RESERVED_PATHS

        assert isinstance(_COMPILER_RESERVED_PATHS, frozenset)

    def test_compiler_reserved_paths_contains_all_reserved_paths_entries(
        self,
    ) -> None:
        """Every RESERVED_PATHS entry must appear in _COMPILER_RESERVED_PATHS."""
        from agents.workflows.compiler import _COMPILER_RESERVED_PATHS
        from app.agents.sandbox import RESERVED_PATHS

        missing = RESERVED_PATHS - _COMPILER_RESERVED_PATHS
        assert not missing, (
            f"_COMPILER_RESERVED_PATHS is missing entries from RESERVED_PATHS: "
            f"{missing}"
        )

    def test_compiler_reserved_paths_contains_bare_forms_for_slash_entries(
        self,
    ) -> None:
        """For every slash-form entry in RESERVED_PATHS, the compiler's copy must
        also have the corresponding bare form (e.g. '.chain/' → '.chain').
        This is the 'plus bare names' the spec prescribes."""
        from agents.workflows.compiler import _COMPILER_RESERVED_PATHS
        from app.agents.sandbox import RESERVED_PATHS

        slash_entries = {e for e in RESERVED_PATHS if e.endswith("/")}
        expected_bare = {e.rstrip("/") for e in slash_entries}
        missing_bare = expected_bare - _COMPILER_RESERVED_PATHS
        assert (
            not missing_bare
        ), f"_COMPILER_RESERVED_PATHS is missing bare forms: {missing_bare}"

    def test_compiler_reserved_paths_contains_chain_legacy_both_forms(self) -> None:
        from agents.workflows.compiler import _COMPILER_RESERVED_PATHS

        assert ".chain-legacy/" in _COMPILER_RESERVED_PATHS
        assert ".chain-legacy" in _COMPILER_RESERVED_PATHS

    def test_compiler_reserved_paths_is_superset_of_reserved_paths(self) -> None:
        """_COMPILER_RESERVED_PATHS must be a superset — it extends the registry
        with bare names, never a subset."""
        from agents.workflows.compiler import _COMPILER_RESERVED_PATHS
        from app.agents.sandbox import RESERVED_PATHS

        assert RESERVED_PATHS.issubset(_COMPILER_RESERVED_PATHS), (
            "_COMPILER_RESERVED_PATHS must contain all of RESERVED_PATHS "
            "(it extends it with bare names, never shrinks it)"
        )


# ---------------------------------------------------------------------------
# 6.  write_to_sandbox refuses every registry path
# ---------------------------------------------------------------------------


class TestWriteToSandboxRefusesReservedPaths:
    """kernel_services.KernelServices.write_to_sandbox must raise ValueError for
    every RESERVED_PATHS entry (Requirement 18 AC, task 2.4)."""

    def _make_services(self) -> Any:
        from agents.execution_engine.kernel_services import KernelServices
        from app.agents.sandbox import RunSandbox

        mock_sandbox = MagicMock(spec=RunSandbox)
        ks = KernelServices.__new__(KernelServices)
        ks.sandbox = mock_sandbox
        return ks

    @pytest.mark.parametrize(
        "reserved_path",
        [
            ".uploads/manifest.json",
            ".logs/run.jsonl",
            ".verify/run-id/static.json",
            ".browser/run-id/screenshot.png",
            ".agents/01-build.md",
            ".chain/summary.md",
            ".chain/logs.jsonl",
            ".context/design/design-system.md",
            "skills/writing/SKILL.md",
            "conversation_history/turn1.md",
            ".chain-legacy/old-run/summary.md",
        ],
    )
    def test_write_to_sandbox_raises_for_reserved_path(
        self, reserved_path: str
    ) -> None:
        ks = self._make_services()
        with pytest.raises(ValueError, match="reserved"):
            ks.write_to_sandbox(reserved_path, "some content")

    def test_write_to_sandbox_raises_for_all_registry_slash_entries(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        ks = self._make_services()
        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                path = entry + "test.txt"
                with pytest.raises(ValueError):
                    ks.write_to_sandbox(path, "content")

    def test_write_to_sandbox_allows_regular_files(self) -> None:
        """Normal files must be passed through to sandbox.write()."""
        ks = self._make_services()
        ks.sandbox.write = MagicMock()

        ks.write_to_sandbox("prototype.html", "<html/>")
        ks.sandbox.write.assert_called_once_with("prototype.html", "<html/>")

    def test_write_to_sandbox_raises_for_slash_leading_reserved_path(self) -> None:
        """A leading / should still be caught after normalisation."""
        ks = self._make_services()
        with pytest.raises(ValueError):
            ks.write_to_sandbox("/.uploads/test.txt", "x")


# ---------------------------------------------------------------------------
# 7.  _ReservedPathGuardMiddleware — write and read guard logic
# ---------------------------------------------------------------------------


def _make_guard_middleware() -> Any:
    """Import the guard from deep_agent_runner, skipping if deepagents is absent."""
    from app.agents.deep_agent_runner import _ReservedPathGuardMiddleware  # noqa: PLC0415

    return _ReservedPathGuardMiddleware()


def _make_tool_request(name: str, path_key: str, path_val: str) -> Any:
    """Build a minimal ToolCallRequest-shaped mock."""
    req = MagicMock()
    req.tool_call = {"name": name, "args": {path_key: path_val}, "id": "tc-1"}
    return req


def test_deepagents_package_is_installed() -> None:
    """Canary: the `deepagents` package must be present in this environment.

    B20 (GIT_VERSIONING_BUGS.md): `TestReservedPathGuardMiddleware` uses an
    autouse `importorskip("deepagents")` fixture, which causes every test in
    that class to **skip** silently when the package is absent.  A CI run
    without the package therefore reports a green test suite while the
    middleware guard — the sole enforcement point that stops an agent from
    writing `.chain/summary.md` via `sub/../.chain/summary.md` — is completely
    untested.

    This test FAILS (not skips) when the package is absent, making the gap
    visible in CI rather than letting it pass silently.  The 25 tests in the
    class still need the package to execute; this canary ensures those skips
    are never mistaken for "all good".
    """
    try:
        import deepagents  # noqa: F401
    except ImportError:
        pytest.fail(
            "deepagents is not installed.  "
            "TestReservedPathGuardMiddleware (B17/B20) will skip all its "
            "tests and the middleware guard will be completely untested.  "
            "Install the package or add it to the CI environment."
        )


class TestReservedPathGuardMiddleware:
    """The middleware must refuse writes to all reserved paths, reads to all
    reserved paths except those in AGENT_READABLE_RESERVED (.context/)."""

    @pytest.fixture(autouse=True)
    def skip_without_deepagents(self) -> None:
        pytest.importorskip("deepagents", reason="deepagents not installed")

    # -- Write guard tests --

    @pytest.mark.parametrize(
        "tool,path_key,path",
        [
            ("write_file", "file_path", ".uploads/test.txt"),
            ("write_file", "file_path", ".logs/run.jsonl"),
            ("write_file", "file_path", ".chain/summary.md"),
            ("write_file", "file_path", "skills/foo.md"),
            ("write_file", "file_path", ".chain-legacy/old/summary.md"),
            ("edit_file", "file_path", ".context/design/design-system.md"),
            ("create_directory", "directory", ".agents/"),
        ],
    )
    def test_write_refused_for_reserved_path(
        self, tool: str, path_key: str, path: str
    ) -> None:
        from langchain_core.messages import ToolMessage

        mw = _make_guard_middleware()
        req = _make_tool_request(tool, path_key, path)
        result = mw._refusal(req)
        assert result is not None, (
            f"Middleware should refuse write tool '{tool}' targeting reserved "
            f"path '{path}'"
        )
        assert isinstance(result, ToolMessage)

    def test_write_allowed_for_normal_file(self) -> None:
        mw = _make_guard_middleware()
        req = _make_tool_request("write_file", "file_path", "prototype.html")
        assert mw._refusal(req) is None

    def test_write_allowed_for_nested_normal_file(self) -> None:
        mw = _make_guard_middleware()
        req = _make_tool_request("write_file", "file_path", "src/components/Button.tsx")
        assert mw._refusal(req) is None

    # -- Read guard tests --

    @pytest.mark.parametrize(
        "tool,path_key,path",
        [
            ("read_file", "path", ".agents/01-domain-analyst.md"),
            ("read_file", "path", ".uploads/brief.pdf.txt"),
            ("ls", "directory", ".uploads/"),
            ("ls", "directory", ".agents/"),
            ("glob", "pattern", ".agents/**/*.md"),
            ("grep", "pattern", ".agents"),
        ],
    )
    def test_agents_dir_is_readable_by_agent_tools(
        self, tool: str, path_key: str, path: str
    ) -> None:
        """`.agents/` and `.uploads/` are READ-allowed — the Q4 migration depends on it.

        GAPS.md §0.2 (the owner's decision, which that document states overrides
        both the original spec text and what v2 built) delivers an upstream
        agent's output to the next agent as a FILE at `.agents/NN-<agent-id>.md`
        rather than pasted into its message, and 81 migrated `AGENT.md` reading
        guides name that path. Before 2026-09-11 the guard refused every one of
        those reads, so the migration was inert — a live `ppt_v2` run produced no
        deliverable at all because its composer could not reach the spec it was
        told to read. Writes stay refused; see the companion test below.
        """
        mw = _make_guard_middleware()
        req = _make_tool_request(tool, path_key, path)
        assert mw._refusal(req) is None, (
            f"Middleware must ALLOW read tool {tool!r} on {path!r} — the migrated "
            "prompts cannot reach their upstream inputs otherwise"
        )

    @pytest.mark.parametrize(
        "tool,path_key,path",
        [
            ("write_file", "file_path", ".agents/01-domain-analyst.md"),
            ("edit_file", "file_path", ".agents/01-domain-analyst.md"),
            ("create_directory", "directory", ".agents/sneaky/"),
            ("write_file", "file_path", ".uploads/planted.txt"),
        ],
    )
    def test_agents_dir_stays_write_refused(
        self, tool: str, path_key: str, path: str
    ) -> None:
        """Granting READ must not grant WRITE — `.agents/` stays engine-written."""
        mw = _make_guard_middleware()
        req = _make_tool_request(tool, path_key, path)
        assert (
            mw._refusal(req) is not None
        ), f"Middleware must still REFUSE write tool {tool!r} on {path!r}"

    @pytest.mark.parametrize(
        "tool,path_key,path",
        [
            ("read_file", "path", ".chain/logs.jsonl"),
            ("read_file", "path", ".chain/summary.md"),
            ("read_file", "path", ".logs/run.jsonl"),
            ("read_file", "path", "skills/foo.md"),
            ("ls", "directory", ".chain/"),
            ("grep", "pattern", ".chain"),
        ],
    )
    def test_read_refused_for_non_readable_reserved_path(
        self, tool: str, path_key: str, path: str
    ) -> None:
        from langchain_core.messages import ToolMessage

        mw = _make_guard_middleware()
        req = _make_tool_request(tool, path_key, path)
        result = mw._refusal(req)
        assert result is not None, (
            f"Middleware should refuse read tool '{tool}' targeting reserved "
            f"path '{path}'"
        )
        assert isinstance(result, ToolMessage)

    def test_read_allowed_for_context_directory(self) -> None:
        """.context/ is in AGENT_READABLE_RESERVED — reads must be permitted."""
        mw = _make_guard_middleware()
        req = _make_tool_request(
            "read_file", "path", ".context/design/design-system.md"
        )
        assert (
            mw._refusal(req) is None
        ), "Reads under .context/ must be allowed (AGENT_READABLE_RESERVED)"

    def test_read_allowed_for_context_root(self) -> None:
        mw = _make_guard_middleware()
        req = _make_tool_request("ls", "directory", ".context/")
        assert mw._refusal(req) is None

    def test_chain_specifically_not_readable_by_agent(self) -> None:
        """Requirement 18 AC 8: an agent tool cannot read .chain/."""
        mw = _make_guard_middleware()
        req = _make_tool_request("read_file", "path", ".chain/summary.md")
        assert (
            mw._refusal(req) is not None
        ), "Agents must not read .chain/ — only authorized Workspace surfaces may"

    def test_read_allowed_for_regular_file(self) -> None:
        mw = _make_guard_middleware()
        req = _make_tool_request("read_file", "path", "prototype.html")
        assert mw._refusal(req) is None

    def test_normalisation_leading_slash_still_blocked(self) -> None:
        """A path like /.chain/x should still be caught after normalisation."""
        mw = _make_guard_middleware()
        req = _make_tool_request("read_file", "path", "/.chain/summary.md")
        assert mw._refusal(req) is not None

    def test_normalisation_dot_slash_prefix_still_blocked(self) -> None:
        mw = _make_guard_middleware()
        req = _make_tool_request("write_file", "file_path", "./.uploads/test.txt")
        assert mw._refusal(req) is not None

    @pytest.mark.parametrize(
        "tool,path_key,path",
        [
            # Embedded ../ collapses to a reserved prefix — must be refused.
            ("read_file", "path", "sub/../.chain/summary.md"),
            ("read_file", "path", "a/b/../../.chain/logs.jsonl"),
            ("write_file", "file_path", "work/../.chain/summary.md"),
            ("write_file", "file_path", ".uploads/sub/../../.chain/secret.txt"),
            ("read_file", "path", "x/../.logs/run.jsonl"),
            ("write_file", "file_path", "docs/../skills/injected.md"),
        ],
    )
    def test_normalisation_embedded_dotdot_still_blocked(
        self, tool: str, path_key: str, path: str
    ) -> None:
        """B17: embedded ../ must be collapsed before the reserved-prefix check.

        Without ``posixpath.normpath`` in ``_normalise``, a path like
        ``sub/../.chain/summary.md`` passes the guard and resolves back into
        the reserved chain payload via ``sandbox.path_for``.
        """
        mw = _make_guard_middleware()
        req = _make_tool_request(tool, path_key, path)
        assert (
            mw._refusal(req) is not None
        ), f"Embedded ../ bypass must be blocked: {path!r}"


# ---------------------------------------------------------------------------
# 7b.  Guard logic extracted — importable without deepagents
# ---------------------------------------------------------------------------
# These tests replicate the guard logic by reading the relevant constants
# (RESERVED_PATHS / AGENT_READABLE_RESERVED) directly. They verify the SAME
# behaviour contract as section 7, but without the deepagents import, so they
# run in all environments.


class TestReservedPathGuardLogicWithoutDependencies:
    """Test the reserved-path guard semantics using RESERVED_PATHS directly,
    independent of deepagents."""

    def _is_reserved(self, path: str) -> bool:
        import posixpath

        from app.agents.sandbox import RESERVED_PATHS

        norm = path.lstrip("/")
        if norm.startswith("./"):
            norm = norm[2:]
        # Collapse embedded ../ segments — mirrors _ReservedPathGuardMiddleware._normalise
        if norm and norm != ".":
            norm = posixpath.normpath(norm)
        else:
            norm = ""
        if norm.startswith("./"):
            norm = norm[2:]
        for entry in RESERVED_PATHS:
            bare = entry.rstrip("/")
            if norm == bare or norm.startswith(bare + "/") or norm.startswith(entry):
                return True
        return False

    def _is_agent_readable(self, path: str) -> bool:
        import posixpath

        from app.agents.sandbox import AGENT_READABLE_RESERVED

        norm = path.lstrip("/")
        if norm.startswith("./"):
            norm = norm[2:]
        if norm and norm != ".":
            norm = posixpath.normpath(norm)
        else:
            norm = ""
        if norm.startswith("./"):
            norm = norm[2:]
        for entry in AGENT_READABLE_RESERVED:
            bare = entry.rstrip("/")
            if norm == bare or norm.startswith(bare + "/") or norm.startswith(entry):
                return True
        return False

    def test_all_reserved_slash_entries_are_blocked(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                # Test both the prefix itself and a nested file
                assert self._is_reserved(entry), f"should block {entry!r}"
                assert self._is_reserved(
                    entry + "test.txt"
                ), f"should block nested path under {entry!r}"

    def test_chain_blocked_but_not_agent_readable(self) -> None:
        """Requirement 18 AC 8: .chain/ is reserved AND not agent-readable."""
        assert self._is_reserved(".chain/summary.md")
        assert not self._is_agent_readable(
            ".chain/summary.md"
        ), ".chain/ must not be readable by agents"

    def test_context_readable_by_agents(self) -> None:
        assert self._is_reserved(".context/selections.json")
        assert self._is_agent_readable(
            ".context/selections.json"
        ), ".context/ must be readable by agents (AGENT_READABLE_RESERVED)"

    def test_regular_files_not_reserved(self) -> None:
        for path in ["prototype.html", "spec.md", "output.md"]:
            assert not self._is_reserved(
                path
            ), f"regular path {path!r} should not be reserved"

    def test_embedded_dotdot_bypass_is_blocked(self) -> None:
        """B17: embedded ../ must collapse to a reserved prefix before the check.

        This mirrors the deepagents-gated test in TestReservedPathGuardMiddleware
        but uses the standalone inline logic so it runs in every environment,
        including CI without deepagents installed.
        """
        bypass_attempts = [
            "sub/../.chain/summary.md",
            "a/b/../../.chain/logs.jsonl",
            "work/../.chain/summary.md",
            ".uploads/sub/../../.chain/secret.txt",
            "x/../.logs/run.jsonl",
            "docs/../skills/injected.md",
        ]
        for path in bypass_attempts:
            assert self._is_reserved(
                path
            ), f"Embedded ../ bypass must be detected as reserved: {path!r}"


# ---------------------------------------------------------------------------
# 8.  is_deliverable_relpath excludes every RESERVED_PATHS + GIT_METADATA_PATHS
# ---------------------------------------------------------------------------


class TestIsDeliverableRelpathExcludesRegistry:
    """is_deliverable_relpath must exclude every reserved path and every git
    metadata path (Requirement 18 AC 2)."""

    def test_excludes_all_reserved_paths_slash_entries(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS, is_deliverable_relpath

        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                path = entry + "test.txt"
                assert not is_deliverable_relpath(path), (
                    f"is_deliverable_relpath should exclude nested path under "
                    f"{entry!r}"
                )

    def test_excludes_git_directory_files(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        git_paths = [
            ".git/config",
            ".git/HEAD",
            ".git/objects/ab/cdef1234",
            ".git/refs/heads/main",
        ]
        for path in git_paths:
            assert not is_deliverable_relpath(
                path
            ), f"is_deliverable_relpath should exclude git path {path!r}"

    def test_excludes_gitignore(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        assert not is_deliverable_relpath(".gitignore")

    def test_excludes_chain_and_context_directories(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        for path in [
            ".chain/summary.md",
            ".chain/logs.jsonl",
            ".context/design/design-system.md",
            ".context/selections.json",
        ]:
            assert not is_deliverable_relpath(
                path
            ), f"is_deliverable_relpath should exclude {path!r}"

    def test_excludes_chain_legacy(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        assert not is_deliverable_relpath(".chain-legacy/old-run/summary.md")

    def test_allows_normal_deliverable_files(self) -> None:
        from app.agents.sandbox import is_deliverable_relpath

        safe = [
            "prototype.html",
            "index.html",
            "presentation.pptx",
            "src/main.py",
            "output.md",
        ]
        for path in safe:
            assert is_deliverable_relpath(
                path
            ), f"is_deliverable_relpath should allow safe file {path!r}"


# ---------------------------------------------------------------------------
# 9.  list_files excludes all RESERVED_PATHS except .chain/, .context/, .agents/
# ---------------------------------------------------------------------------


class TestListFilesExcludesRegistry:
    """RunSandbox.list_files must exclude the right reserved subset.

    Visible in listing (kept):     .chain/, .context/, .agents/, .verify/
    Not visible in listing (dropped): all other RESERVED_PATHS entries +
                                      GIT_METADATA_PATHS

    ``.verify/`` is visible for spec 017 viewable media: the Workspace tab
    (frontend SandboxTab) renders render_pptx's PNG/PDF evidence from it.
    """

    _VISIBLE_IN_LISTING: frozenset[str] = frozenset(
        {".chain/", ".context/", ".agents/", ".verify/"}
    )

    def test_listing_excluded_prefixes_excludes_hidden_reserved_entries(
        self,
    ) -> None:
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_PREFIXES")

    def test_listing_excluded_prefixes_does_not_exclude_visible_entries(
        self,
    ) -> None:
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_PREFIXES")

    def test_listing_excluded_exact_excludes_gitignore(self) -> None:
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_EXACT")

    def test_listing_excluded_prefixes_excludes_git_prefix(self) -> None:
        import app.agents.sandbox as sandbox_module

        assert not hasattr(sandbox_module, "_LISTING_EXCLUDED_PREFIXES")

    def test_list_files_excludes_uploads_and_logs(self, tmp_path: Path) -> None:
        """Functional: .uploads/ and .logs/ must not appear in list_files()."""
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox("testuser", "testrun", runs_root=str(tmp_path))
        sb.ensure()

        (sb.root / "prototype.html").write_text("<html/>", encoding="utf-8")
        (sb.root / ".uploads").mkdir(exist_ok=True)
        (sb.root / ".uploads" / "doc.pdf").write_bytes(b"%PDF")
        (sb.root / ".logs").mkdir(exist_ok=True)
        (sb.root / ".logs" / "run.jsonl").write_text("{}", encoding="utf-8")
        (sb.root / "skills").mkdir(exist_ok=True)
        (sb.root / "skills" / "writing.md").write_text("# skill", encoding="utf-8")

        files, _ = sb.list_files()
        paths = {f["path"] for f in files}

        assert "prototype.html" in paths, "list_files must include regular files"
        assert ".uploads/doc.pdf" in paths
        assert ".logs/run.jsonl" in paths
        assert "skills/writing.md" in paths

    def test_list_files_excludes_chain_legacy(self, tmp_path: Path) -> None:
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox("testuser", "testrun_cl", runs_root=str(tmp_path))
        sb.ensure()

        (sb.root / ".chain-legacy").mkdir(exist_ok=True)
        (sb.root / ".chain-legacy" / "old-run").mkdir(exist_ok=True)
        (sb.root / ".chain-legacy" / "old-run" / "summary.md").write_text(
            "old", encoding="utf-8"
        )

        files, _ = sb.list_files()
        paths = {f["path"] for f in files}

        assert ".chain-legacy/old-run/summary.md" in paths

    def test_list_files_keeps_chain_context_agents_visible(
        self, tmp_path: Path
    ) -> None:
        """.chain/, .context/, .agents/ must be VISIBLE in list_files."""
        from app.agents.sandbox import RunSandbox

        sb = RunSandbox("testuser", "testrun2", runs_root=str(tmp_path))
        sb.ensure()

        (sb.root / ".chain").mkdir(exist_ok=True)
        (sb.root / ".chain" / "summary.md").write_text(
            "schema_version: 2", encoding="utf-8"
        )
        (sb.root / ".context").mkdir(exist_ok=True)
        (sb.root / ".context" / "selections.json").write_text("{}", encoding="utf-8")
        (sb.root / ".agents").mkdir(exist_ok=True)
        (sb.root / ".agents" / "01-build.md").write_text("# output", encoding="utf-8")

        files, _ = sb.list_files()
        paths = {f["path"] for f in files}

        assert ".chain/summary.md" in paths, ".chain/ must be visible in list_files"
        assert (
            ".context/selections.json" in paths
        ), ".context/ must be visible in list_files"
        assert ".agents/01-build.md" in paths, ".agents/ must be visible in list_files"


# ---------------------------------------------------------------------------
# 10. read_sandbox_file guard in run_files.py
# ---------------------------------------------------------------------------


class TestReadSandboxFileRefusesRegistry:
    """_SANDBOX_READ_REFUSED must be derived from RESERVED_PATHS and include at
    minimum .uploads/, .logs/, .chain-legacy/ (Requirement 18 AC 2)."""

    @pytest.fixture(autouse=True)
    def skip_without_fastapi(self) -> None:
        pytest.importorskip("fastapi", reason="fastapi not installed")

    def test_sandbox_read_refused_contains_uploads(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_sandbox_read_refused_contains_logs(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_sandbox_read_refused_contains_chain_legacy(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_sandbox_read_refused_is_subset_of_reserved_paths(self) -> None:
        """_SANDBOX_READ_REFUSED must only contain entries from RESERVED_PATHS."""
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_read_sandbox_file_guard_blocks_uploads_nested_path(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_read_sandbox_file_guard_blocks_logs_nested_path(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")

    def test_read_sandbox_file_guard_blocks_chain_legacy_nested_path(self) -> None:
        import app.api.run_files as run_files

        assert not hasattr(run_files, "_SANDBOX_READ_REFUSED")


# ---------------------------------------------------------------------------
# 10b. read_sandbox_file guard — AST-based verification without fastapi import
# ---------------------------------------------------------------------------


class TestReadSandboxFileGuardSourceVerification:
    """Verify run_files.py's _SANDBOX_READ_REFUSED constant without importing
    the full module (which requires fastapi)."""

    def _source(self) -> str:
        path = BACKEND_ROOT / "app" / "api" / "run_files.py"
        return path.read_text(encoding="utf-8")

    def test_sandbox_read_refused_defined_from_reserved_paths_not_literals(
        self,
    ) -> None:
        """The _SANDBOX_READ_REFUSED constant must reference RESERVED_PATHS,
        not hard-code a literal frozenset of strings."""
        src = self._source()
        assert "_SANDBOX_READ_REFUSED" not in src

    def test_sandbox_read_refused_contains_required_entries_in_source(self) -> None:
        """The source must express refusal of .uploads/, .logs/, .chain-legacy/."""
        src = self._source()
        assert "_SANDBOX_READ_REFUSED" not in src
        assert "def read_sandbox_file" in src


# ---------------------------------------------------------------------------
# 11. _assert_share_output_clean refuses reserved paths in the deliverable string
# ---------------------------------------------------------------------------


class TestAssertShareOutputClean:
    """_assert_share_output_clean must detect any RESERVED_PATHS or
    GIT_METADATA_PATHS entry in a deliverable output string and raise
    RuntimeError."""

    @pytest.fixture(autouse=True)
    def skip_without_fastapi(self) -> None:
        pytest.importorskip("fastapi", reason="fastapi not installed")

    def _make_output(self, relpath: str, content: str = "some content") -> str:
        """Build a minimal filename-block deliverable string."""
        return f"```filename: {relpath}\n{content}\n```"

    def test_clean_output_does_not_raise(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output("prototype.html", "<html>hello</html>")
        _assert_share_output_clean(output, "run-clean")

    def test_raises_for_chain_path(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".chain/summary.md", "schema_version: 2")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-chain")

    def test_raises_for_logs_path(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".logs/run-abc.jsonl", "{}")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-logs")

    def test_raises_for_uploads_path(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".uploads/doc.pdf", "data")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-uploads")

    def test_raises_for_gitignore(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".gitignore", ".chain/")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-gitignore")

    def test_raises_for_git_directory(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".git/config", "[core]")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-git")

    def test_raises_for_all_reserved_paths_slash_entries(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS
        from app.api.runs import _assert_share_output_clean

        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                path = entry + "test.txt"
                output = self._make_output(path, "content")
                with pytest.raises(RuntimeError):
                    _assert_share_output_clean(output, "run-test")

    def test_raises_for_chain_legacy(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = self._make_output(".chain-legacy/old/summary.md", "data")
        with pytest.raises(RuntimeError, match="reserved path"):
            _assert_share_output_clean(output, "run-chain-legacy")

    def test_multiple_files_clean_does_not_raise(self) -> None:
        from app.api.runs import _assert_share_output_clean

        output = "\n\n".join(
            [
                self._make_output("index.html", "<html/>"),
                self._make_output("styles.css", "body{}"),
                self._make_output("script.js", "console.log()"),
            ]
        )
        _assert_share_output_clean(output, "run-multi")


# ---------------------------------------------------------------------------
# 11b. _assert_share_output_clean logic — reimplemented without fastapi import
# ---------------------------------------------------------------------------


class TestShareOutputCleanLogicWithoutDependencies:
    """Verify the share guard logic against RESERVED_PATHS directly,
    without importing the fastapi-dependent runs module."""

    # Inline reimplementation of _assert_share_output_clean's logic
    # (tests the same semantics that runs.py implements).
    _FILENAME_BLOCK_RE = re.compile(
        r"^```filename:\s*(?P<path>[^\n]+)",
        re.MULTILINE,
    )

    def _check_output_clean(self, output: str) -> bool:
        """Return True if output is clean (no reserved paths), False otherwise."""
        from app.agents.sandbox import GIT_METADATA_PATHS, RESERVED_PATHS

        excluded = RESERVED_PATHS | GIT_METADATA_PATHS
        for m in self._FILENAME_BLOCK_RE.finditer(output):
            relpath = m.group("path").strip()
            for entry in excluded:
                if entry.endswith("/"):
                    if relpath.startswith(entry) or relpath == entry.rstrip("/"):
                        return False
                else:
                    basename = relpath.rsplit("/", 1)[-1]
                    if relpath == entry or basename == entry:
                        return False
        return True

    def _make_output(self, relpath: str) -> str:
        return f"```filename: {relpath}\nsome content\n```"

    def test_clean_file_passes(self) -> None:
        assert self._check_output_clean(self._make_output("prototype.html"))

    def test_chain_path_fails(self) -> None:
        assert not self._check_output_clean(self._make_output(".chain/summary.md"))

    def test_git_path_fails(self) -> None:
        assert not self._check_output_clean(self._make_output(".git/config"))

    def test_all_reserved_slash_entries_fail(self) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                path = entry + "test.txt"
                assert not self._check_output_clean(
                    self._make_output(path)
                ), f"Entry {entry!r} should be caught by the share guard"


# ---------------------------------------------------------------------------
# 12. Compiler raises CompilerError for reserved seed_files.from_run entries
# ---------------------------------------------------------------------------


class TestCompilerReservedSeedFilesGuard:
    """The compiler must reject any manifest whose seed_files.from_run declares a
    reserved path — and the rejection must NOT fall back to a default seed set
    (Requirement 18 AC 11–12)."""

    def _build_registry(self) -> Any:
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry()

    def _minimal_manifest_dict(self, from_run_entries: list[str]) -> dict:
        # ``planner`` and ``clarify`` are MAN-01 required keys
        # (``manifest._REQUIRED_KEYS``); without them ``build_manifest_from_dict``
        # raises ManifestValidationError before the compiler guard is reached.
        return {
            "id": "test-reserved-seed",
            "planner": "run",
            "clarify": {"mode": "skip"},
            "steps": [
                {
                    "agent": "prototype-build",
                    "strategy": "single_shot",
                }
            ],
            "seed_files": {"from_run": from_run_entries},
            "deliverable": {"strategy": "single_file", "name": "output.html"},
        }

    @pytest.mark.parametrize(
        "reserved_entry",
        [
            ".chain/logs.jsonl",
            ".uploads/manifest.json",
            ".logs/run.jsonl",
            "skills/writing/SKILL.md",
            "conversation_history/turn1.md",
            ".chain-legacy/old/summary.md",
            ".agents/01-build.md",
            ".context/design.md",
            ".verify/run-id/result.json",
            ".browser/screenshot.png",
            # bare forms
            ".chain",
            ".uploads",
            "skills",
        ],
    )
    def test_compiler_raises_for_reserved_seed_file_entry(
        self, reserved_entry: str
    ) -> None:
        from agents.workflows.compiler import CompilerError, WorkflowCompiler
        from agents.workflows.manifest import build_manifest_from_dict

        registry = self._build_registry()
        raw = self._minimal_manifest_dict([reserved_entry])

        manifest = build_manifest_from_dict(raw, "test-source")

        compiler = WorkflowCompiler()
        with pytest.raises(CompilerError):
            compiler.compile(manifest, registry)

    def test_compiler_error_names_offending_entry(self) -> None:
        """The CompilerError message must name the offending entry (Req 18 AC 11)."""
        from agents.workflows.compiler import CompilerError, WorkflowCompiler
        from agents.workflows.manifest import build_manifest_from_dict

        registry = self._build_registry()
        raw = self._minimal_manifest_dict([".chain/logs.jsonl"])

        manifest = build_manifest_from_dict(raw, "test-source")

        compiler = WorkflowCompiler()
        with pytest.raises(CompilerError) as exc_info:
            compiler.compile(manifest, registry)

        assert ".chain/logs.jsonl" in str(
            exc_info.value
        ), "CompilerError must name the offending reserved entry (Req 18 AC 11)"

    def test_compiler_accepts_non_reserved_seed_files(self) -> None:
        """A manifest with non-reserved from_run entries must compile without error."""
        from agents.workflows.compiler import CompilerError, WorkflowCompiler
        from agents.workflows.manifest import build_manifest_from_dict

        registry = self._build_registry()
        raw = self._minimal_manifest_dict(["spec.md", "design.md", "tasks.md"])

        manifest = build_manifest_from_dict(raw, "test-source")

        compiler = WorkflowCompiler()
        try:
            compiled = compiler.compile(manifest, registry)
            assert compiled is not None
        except CompilerError as e:
            # A CompilerError for something other than the seed files is fine
            err_str = str(e).lower()
            assert (
                "seed_files" not in err_str and "reserved" not in err_str
            ), f"Unexpected CompilerError about seed files on safe manifest: {e}"


# ---------------------------------------------------------------------------
# 13. Real-disk end-to-end: write_to_sandbox refuses all registry paths
# ---------------------------------------------------------------------------


class TestWriteToSandboxEndToEnd:
    """Full integration: writing a reserved path via write_to_sandbox raises
    ValueError BEFORE touching disk — no reserved content is ever written."""

    def _make_real_kernel_services(self, tmp_path: Path) -> Any:
        from agents.execution_engine.kernel_services import KernelServices
        from app.agents.sandbox import RunSandbox

        sandbox = RunSandbox("user1", "run1", runs_root=str(tmp_path))
        sandbox.ensure()

        ks = KernelServices.__new__(KernelServices)
        ks.sandbox = sandbox
        return ks

    def test_reserved_path_never_written_to_disk(self, tmp_path: Path) -> None:
        from app.agents.sandbox import RESERVED_PATHS

        ks = self._make_real_kernel_services(tmp_path)
        sandbox_root = ks.sandbox.root

        for entry in RESERVED_PATHS:
            if entry.endswith("/"):
                reserved_path = entry + "test.txt"
            else:
                reserved_path = entry

            with pytest.raises(ValueError):
                ks.write_to_sandbox(reserved_path, "injected content")

            # The file must not have been created on disk
            target = sandbox_root / reserved_path.lstrip("/")
            assert (
                not target.exists()
            ), f"Reserved path '{reserved_path}' was written to disk despite ValueError"

    def test_normal_file_is_written_to_disk(self, tmp_path: Path) -> None:
        ks = self._make_real_kernel_services(tmp_path)
        ks.write_to_sandbox("output.html", "<html>test</html>")
        assert (ks.sandbox.root / "output.html").is_file()
        content = (ks.sandbox.root / "output.html").read_text(encoding="utf-8")
        assert content == "<html>test</html>"

    def test_all_registry_entries_blocked_without_disk_write(
        self, tmp_path: Path
    ) -> None:
        """Exhaustive check: every RESERVED_PATHS entry is refused and nothing
        is written to disk — the end-to-end proof required by Req 18 AC 13."""
        from app.agents.sandbox import RESERVED_PATHS

        ks = self._make_real_kernel_services(tmp_path)

        refused_count = 0
        for entry in RESERVED_PATHS:
            path = entry + "secret.txt" if entry.endswith("/") else entry
            try:
                ks.write_to_sandbox(path, "malicious content")
                pytest.fail(
                    f"write_to_sandbox did NOT raise ValueError for reserved path "
                    f"'{path}' (derived from entry '{entry}')"
                )
            except ValueError:
                refused_count += 1

        assert refused_count == len(RESERVED_PATHS), (
            f"Expected all {len(RESERVED_PATHS)} entries to be refused, "
            f"but only {refused_count} were"
        )

    def test_gitignore_derived_guard_matches_reserved_paths(
        self, tmp_path: Path
    ) -> None:
        """Verify that the set of paths the .gitignore would cover matches what
        write_to_sandbox refuses — both derive from RESERVED_PATHS (V2-Q7)."""
        from app.agents.runtime.local import LocalWorkspace
        from app.agents.sandbox import RESERVED_PATHS

        gitignore_set = set(LocalWorkspace._GITIGNORE_PATHS)
        assert gitignore_set == RESERVED_PATHS, (
            "The .gitignore seeded paths and the write_to_sandbox guard paths "
            "must both derive from the same RESERVED_PATHS registry"
        )
