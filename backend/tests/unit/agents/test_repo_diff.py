"""``repo_diff`` — unified-diff parsing + the no-shelling source guard (Phase 09 / REPO-04).

What is left here after the Batch 6 split needs no git and no filesystem beyond the
resolver's own source:

  * the resolver reads diffs via the ``Workspace`` handle and never shells git itself
    (D-10 — the Workspace is the single git owner), asserted against the source;
  * ``_split_per_file`` / ``_path_from_header`` never silently DROP a changed file:
    an unparseable (quoted / rename) ``diff --git`` header lands under a synthetic
    ``__unparsed_N__`` key (IN-03);
  * the deliverable is registered.

The end-to-end half — clone the ``local_git_fixture``, branch, edit, resolve, and prove
the resolver commits and pushes nothing — moved to
``tests/integration/agents/test_repo_diff_external.py``.
"""

from __future__ import annotations

from pathlib import Path

from agents.capabilities.registry import CapabilityRegistry, discover


def test_repo_diff_resolver_does_not_shell_git() -> None:
    """The resolver source contains no ``git commit``/``git push`` and never shells
    git (it reads via the Workspace handle) — REPO-04 / D-10 acceptance."""
    # tests/unit/agents/<this file> -> backend/ is parents[3]; the module lives under
    # backend/agents/capabilities/deliverables/repo_diff.py.
    backend_root = Path(__file__).resolve().parents[3]
    src = backend_root / "agents" / "capabilities" / "deliverables" / "repo_diff.py"
    assert src.is_file(), f"repo_diff.py not found at {src}"
    text = src.read_text(encoding="utf-8")
    # No git commit / push (diff-only, N4); no subprocess shelling of git.
    assert "git commit" not in text
    assert "git push" not in text
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "Popen" not in text


def test_repo_diff_registered() -> None:
    discover()
    assert CapabilityRegistry().is_registered("deliverable", "repo_diff")


# ── IN-03: synthetic-key fallback for unparseable diff --git headers ──────────
# A quoted/rename `diff --git` header is unparseable by `_path_from_header`
# (returns None). Before the IN-03 fix `_split_per_file._flush` dropped such a
# block silently (it only wrote when `current_path is not None`), losing a
# changed file. The fix keys the block under a synthetic `__unparsed_N__` so no
# changed file is ever silently dropped (Phase 9 review IN-03).
from agents.capabilities.deliverables.repo_diff import RepoDiffResolver  # noqa: E402


def test_repo_diff_quoted_header_survives_under_synthetic_key() -> None:
    """A quoted `diff --git "a/has space.py" "b/has space.py"` header is
    unparseable; the block must NOT be dropped — it appears under a synthetic key."""
    quoted = (
        'diff --git "a/has space.py" "b/has space.py"\n'
        "index 1111111..2222222 100644\n"
        '--- "a/has space.py"\n'
        '+++ "b/has space.py"\n'
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    # Confirm the header is genuinely unparseable (precondition for the fix).
    header = quoted.splitlines()[0]
    assert RepoDiffResolver._path_from_header(header) is None, header

    per_file = RepoDiffResolver._split_per_file(quoted)
    assert per_file, "the unparseable block was silently dropped (IN-03 regression)"
    keys = list(per_file.keys())
    assert all(k.startswith("__unparsed_") for k in keys), keys
    # The block content (the edit) survives under the synthetic key.
    assert "+new" in per_file[keys[0]]


def test_repo_diff_rename_header_survives_under_synthetic_key() -> None:
    """A rename-style header `_path_from_header` cannot resolve still keeps its block."""
    rename = (
        "diff --git\n"  # malformed/rename header with no a/<p> b/<p> tokens
        "similarity index 100%\n"
        "rename from old/name.py\n"
        "rename to new/name.py\n"
    )
    assert RepoDiffResolver._path_from_header(rename.splitlines()[0]) is None

    per_file = RepoDiffResolver._split_per_file(rename)
    assert per_file, "the rename block was silently dropped (IN-03 regression)"
    assert all(k.startswith("__unparsed_") for k in per_file)
    assert "rename to new/name.py" in next(iter(per_file.values()))


def test_repo_diff_normal_header_keys_by_path_unchanged() -> None:
    """Parity: a normal `diff --git a/x.py b/x.py` still keys under `x.py` (no synthetic key)."""
    normal = (
        "diff --git a/x.py b/x.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
    )
    per_file = RepoDiffResolver._split_per_file(normal)
    assert "x.py" in per_file, per_file
    assert not any(k.startswith("__unparsed_") for k in per_file)


def test_repo_diff_multiple_unparseable_blocks_get_distinct_keys() -> None:
    """Two unparseable blocks must get DISTINCT synthetic keys (no collision/overwrite)."""
    two = (
        'diff --git "a/one.py" "b/one.py"\n'
        "@@ -1 +1 @@\n"
        "-one_old\n"
        "+one_new\n"
        'diff --git "a/two.py" "b/two.py"\n'
        "@@ -1 +1 @@\n"
        "-two_old\n"
        "+two_new\n"
    )
    per_file = RepoDiffResolver._split_per_file(two)
    keys = list(per_file.keys())
    assert len(keys) == 2, f"two unparseable blocks collided/overwrote: {keys}"
    assert len(set(keys)) == 2, f"synthetic keys collided: {keys}"
    assert all(k.startswith("__unparsed_") for k in keys), keys
    # Each block kept its own distinct content (no overwrite).
    blobs = "".join(per_file.values())
    assert "one_new" in blobs and "two_new" in blobs


def test_repo_diff_mixed_parseable_and_unparseable() -> None:
    """A normal block + an unparseable block: the normal keys by path, the unparseable by synthetic key."""
    mixed = (
        "diff --git a/normal.py b/normal.py\n"
        "@@ -1 +1 @@\n"
        "-n_old\n"
        "+n_new\n"
        'diff --git "a/odd one.py" "b/odd one.py"\n'
        "@@ -1 +1 @@\n"
        "-o_old\n"
        "+o_new\n"
    )
    per_file = RepoDiffResolver._split_per_file(mixed)
    assert "normal.py" in per_file
    synth = [k for k in per_file if k.startswith("__unparsed_")]
    assert len(synth) == 1, per_file
    assert "o_new" in per_file[synth[0]]
