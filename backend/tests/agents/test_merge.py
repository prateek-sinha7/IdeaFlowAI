"""tests/agents/test_merge.py — the MergeStrategy port + 4 registered impls (FANOUT-07).

Drives the 4 merge strategies (``copy_disjoint`` / ``git_3way`` / ``json`` /
``html_fragment``) fully OFFLINE against structural fragment fixtures (no kernel, no
engine, no DB, no git for the pure strategies):

  * copy_disjoint over a disjoint file set is byte-stable + deterministic (run twice);
  * copy_disjoint same-path differing-content yields a REPORTED conflict (never a
    silent overwrite, T-11-03-01);
  * json same-key differing-value yields a reported conflict;
  * html_fragment disjoint sections compose; same-section overlap conflicts;
  * git_3way reaches git ONLY via the runner handle (disjoint→clean, overlap→conflict);
  * all 4 strategies resolve via the registry (``is_registered("merge", name)``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities.merge.base import MergeResult, MergeStrategy
from agents.capabilities.merge.copy_disjoint import CopyDisjointMerge
from agents.capabilities.merge.git_3way import Git3WayMerge
from agents.capabilities.merge.json_merge import JsonMerge
from agents.capabilities.merge.html_fragment import HtmlFragmentMerge


# ---------------------------------------------------------------------------
# Fragment fixtures — the structural shapes the engine adapts a workspace to.
# ---------------------------------------------------------------------------


class _FileFragment:
    """A copy_disjoint fragment: ``name`` + ``files() -> {relpath: content}``."""

    def __init__(self, name, files):
        self.name = name
        self._files = dict(files)

    def files(self):
        return dict(self._files)


class _WritableBase:
    """A merge base that records writes (the live workspace seam)."""

    def __init__(self, files=None):
        self._files = dict(files or {})
        self.written = {}

    def files(self):
        return dict(self._files)

    def write(self, path, content):
        self.written[path] = content


class _SectionFragment:
    def __init__(self, name, sections):
        self.name = name
        self._sections = dict(sections)

    def sections(self):
        return dict(self._sections)


class _JsonFragment:
    def __init__(self, name, doc):
        self.name = name
        self.doc = dict(doc)


# ---------------------------------------------------------------------------
# Port shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("impl", [CopyDisjointMerge, Git3WayMerge, JsonMerge, HtmlFragmentMerge])
def test_impls_satisfy_the_merge_port(impl) -> None:
    inst = impl()
    assert isinstance(inst, MergeStrategy)  # runtime_checkable structural conformance
    assert isinstance(inst.name, str) and inst.name


def test_merge_result_clean_property() -> None:
    assert MergeResult().clean is True
    assert MergeResult(conflicts=[{"path": "a"}]).clean is False


# ---------------------------------------------------------------------------
# copy_disjoint — determinism + conflict-as-first-class
# ---------------------------------------------------------------------------


def test_copy_disjoint_deterministic_over_disjoint_set() -> None:
    strat = CopyDisjointMerge()
    frags = [
        _FileFragment("w1", {"a.txt": "AAA", "b.txt": "BBB"}),
        _FileFragment("w0", {"c.txt": "CCC"}),
    ]
    base1 = _WritableBase()
    base2 = _WritableBase()
    r1 = strat.merge(base1, frags)
    r2 = strat.merge(base2, list(reversed(frags)))  # different input order
    assert r1.clean and r2.clean
    # Byte-stable deterministic result regardless of input order (sorted internally).
    assert r1.applied == r2.applied == ["a.txt", "b.txt", "c.txt"]
    assert base1.written == base2.written == {"a.txt": "AAA", "b.txt": "BBB", "c.txt": "CCC"}


def test_copy_disjoint_overlap_is_a_reported_conflict_not_silent_overwrite() -> None:
    strat = CopyDisjointMerge()
    base = _WritableBase()
    frags = [
        _FileFragment("w0", {"shared.txt": "FROM-W0"}),
        _FileFragment("w1", {"shared.txt": "FROM-W1"}),  # SAME path, DIFFERING content
    ]
    result = strat.merge(base, frags)
    assert not result.clean
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict["path"] == "shared.txt"
    # Both worker provenances present; NEITHER silently applied to the base.
    assert set(conflict["sources"]) == {"w0", "w1"}
    assert "shared.txt" not in base.written
    assert "shared.txt" not in result.applied


def test_copy_disjoint_same_content_overlap_is_idempotent_not_a_conflict() -> None:
    strat = CopyDisjointMerge()
    base = _WritableBase()
    frags = [
        _FileFragment("w0", {"same.txt": "X"}),
        _FileFragment("w1", {"same.txt": "X"}),  # same path, SAME content → no conflict
    ]
    result = strat.merge(base, frags)
    assert result.clean
    assert result.applied == ["same.txt"]


def test_copy_disjoint_overlap_vs_base_since_spawn_conflicts() -> None:
    strat = CopyDisjointMerge()
    base = _WritableBase(files={"base.txt": "ORIGINAL"})
    frags = [_FileFragment("w0", {"base.txt": "CHANGED"})]  # differs from base
    result = strat.merge(base, frags)
    assert not result.clean
    assert result.conflicts[0]["path"] == "base.txt"
    assert "base.txt" not in base.written


# ---------------------------------------------------------------------------
# json — key-level merge + conflict
# ---------------------------------------------------------------------------


def test_json_disjoint_keys_merge() -> None:
    strat = JsonMerge()
    frags = [_JsonFragment("w0", {"a": 1}), _JsonFragment("w1", {"b": 2})]
    result = strat.merge({}, frags)
    assert result.clean
    assert result.applied == ["a", "b"]


def test_json_same_key_differing_value_conflicts() -> None:
    strat = JsonMerge()
    frags = [_JsonFragment("w0", {"k": 1}), _JsonFragment("w1", {"k": 2})]
    result = strat.merge({}, frags)
    assert not result.clean
    assert result.conflicts[0]["path"] == "k"
    assert set(result.conflicts[0]["sources"]) == {"w0", "w1"}


def test_json_writer_backed_base_receives_merged_keys() -> None:
    """WR-08: the merged document EXISTS — non-conflicting keys are written to the
    base; a conflicting key is NEVER written (no silent overwrite)."""
    strat = JsonMerge()

    class _WritableBase:
        def __init__(self):
            self.written: dict = {}

        def write(self, key, value):
            self.written[key] = value

    base = _WritableBase()
    frags = [
        _JsonFragment("w0", {"a": 1, "k": 1}),
        _JsonFragment("w1", {"b": 2, "k": 2}),  # k conflicts
    ]
    result = strat.merge(base, frags)
    assert base.written == {"a": 1, "b": 2}  # the merged doc accumulated
    assert "k" not in base.written  # the conflicting key never landed
    assert result.applied == ["a", "b"]


# ---------------------------------------------------------------------------
# html_fragment — section composition + conflict
# ---------------------------------------------------------------------------


def test_html_fragment_disjoint_sections_compose() -> None:
    strat = HtmlFragmentMerge()
    frags = [
        _SectionFragment("w0", {"header": "<h1>H</h1>"}),
        _SectionFragment("w1", {"footer": "<footer>F</footer>"}),
    ]
    result = strat.merge({}, frags)
    assert result.clean
    assert result.applied == ["footer", "header"]


def test_html_fragment_same_section_overlap_conflicts() -> None:
    strat = HtmlFragmentMerge()
    frags = [
        _SectionFragment("w0", {"main": "<div>A</div>"}),
        _SectionFragment("w1", {"main": "<div>B</div>"}),
    ]
    result = strat.merge({}, frags)
    assert not result.clean
    assert result.conflicts[0]["path"] == "main"


def test_html_fragment_writer_backed_base_receives_sections() -> None:
    """WR-08: composed sections are written to the base via set_section; a
    conflicting section is NEVER written."""
    strat = HtmlFragmentMerge()

    class _SectionBase:
        def __init__(self):
            self.sections_written: dict = {}

        def set_section(self, sid, html):
            self.sections_written[sid] = html

    base = _SectionBase()
    frags = [
        _SectionFragment("w0", {"header": "<h1>H</h1>", "main": "<div>A</div>"}),
        _SectionFragment("w1", {"main": "<div>B</div>"}),  # main conflicts
    ]
    result = strat.merge(base, frags)
    assert base.sections_written == {"header": "<h1>H</h1>"}
    assert "main" not in base.sections_written
    assert result.applied == ["header"]


# ---------------------------------------------------------------------------
# git_3way — reaches git ONLY via the runner handle (no capability-side subprocess)
# ---------------------------------------------------------------------------


class _GitRunner:
    """A fake ctx.runner exposing git_3way_merge (the only git path for git_3way)."""

    def __init__(self, conflicts_for=None):
        self._conflicts_for = conflicts_for or {}
        self.calls = []

    def git_3way_merge(self, branch, base_commit):
        self.calls.append((branch, base_commit))
        conflicts = self._conflicts_for.get(branch, [])
        return {"conflicts": list(conflicts), "snippet": ", ".join(conflicts)}


def test_git_3way_disjoint_branches_merge_clean() -> None:
    runner = _GitRunner()
    strat = Git3WayMerge()
    frags = [
        SimpleNamespace(runner=runner, branch="fanout/s/0", base_commit="abc"),
        SimpleNamespace(runner=runner, branch="fanout/s/1", base_commit="abc"),
    ]
    result = strat.merge(base=None, fragments=frags)
    assert result.clean
    assert result.applied == ["fanout/s/0", "fanout/s/1"]
    # git reached ONLY through the runner handle — both branches merged via the handle.
    assert runner.calls == [("fanout/s/0", "abc"), ("fanout/s/1", "abc")]


def test_git_3way_conflicting_branch_reports_conflict() -> None:
    runner = _GitRunner(conflicts_for={"fanout/s/1": ["index.html"]})
    strat = Git3WayMerge()
    frags = [
        SimpleNamespace(runner=runner, branch="fanout/s/0", base_commit="abc"),
        SimpleNamespace(runner=runner, branch="fanout/s/1", base_commit="abc"),
    ]
    result = strat.merge(base=None, fragments=frags)
    assert not result.clean
    assert result.applied == ["fanout/s/0"]
    assert result.conflicts[0]["path"] == "index.html"


def test_git_3way_no_handle_skips_without_fabricating_a_conflict() -> None:
    # An offline fragment with no runner handle must not invent a conflict.
    strat = Git3WayMerge()
    frags = [SimpleNamespace(runner=None, branch="fanout/s/0", base_commit="")]
    result = strat.merge(base=None, fragments=frags)
    assert result.clean
    assert result.applied == []


# ---------------------------------------------------------------------------
# Registry resolution — all 4 strategies resolve via the registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["copy_disjoint", "git_3way", "json", "html_fragment"])
def test_strategy_registered_and_user_allowed(name) -> None:
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("merge", name) is True
    # The engine picks the strategy, but the palette exposes them (A2 / user_allowed=True).
    assert reg.is_user_allowed("merge", name) is True
    impl = reg.resolve("merge", name)
    assert impl.name == name
