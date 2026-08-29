"""BUG-20260828-021300-library-skills — ISS-571.

`hooks_catalog._load_one` only checks that `event` is PRESENT in a `HOOK.md`'s
frontmatter (`missing = [f for f in required if f not in metadata]`), not
that it's non-empty. A `HOOK.md` declaring `event: ""` would pass that check,
survive into `list_global_hooks()`'s returned entries, and then be dropped
out of `hooks.py:33`'s `events = sorted({e.event for e in entries if e.event})`
pill list — exactly ISS-329's "falsy value silently drops out of its own
filter's pill list, but the record still renders" shape, on the Hooks
catalog instead of Skills.

Latent today (0/8 real hooks affected) — this test uses a fixture hooks
directory to trigger the mechanism directly, per the card's own "What would
confirm or refute this" section.

See `bug-hunter/ledger.md`'s `BUG-20260828-021300-library-skills` entry and
`.knowledge/cards/20260829-0004-ISS-571.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import hooks_catalog

FIXTURE_HOOK_MD = """\
---
id: blank-event-hook
name: Blank Event Hook
description: A fixture hook whose event is present but empty, for ISS-571.
event: ""
trigger: something
---

Fixture body.
"""


@pytest.fixture
def blank_event_hooks_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    hooks_dir = tmp_path / "global"
    hook_dir = hooks_dir / "blank-event-hook"
    hook_dir.mkdir(parents=True)
    (hook_dir / "HOOK.md").write_text(FIXTURE_HOOK_MD, encoding="utf-8")

    monkeypatch.setattr(hooks_catalog, "_GLOBAL_HOOKS_DIR", hooks_dir)
    hooks_catalog.clear_cache()
    yield hooks_dir
    hooks_catalog.clear_cache()


@pytest.mark.issue("ISS-571")
def test_a_hook_with_a_blank_event_is_excluded_from_the_catalog(blank_event_hooks_dir):
    """ISS-571 — a HOOK.md with a present-but-empty `event` must not survive
    into the catalog as an entry with no matching pill; the loader should
    reject it the same way it already rejects a MISSING `event` key.
    """
    entries = hooks_catalog.list_global_hooks()
    assert not any(e.id == "blank-event-hook" for e in entries), (
        "a hook with event: \"\" survived into list_global_hooks() — it is "
        "present in the catalog but its event value is falsy, so it can "
        "never match any event pill's filter (hooks.py:33 drops empty "
        "strings from the pill list), reproducing ISS-329's reachability "
        "gap on the Hooks catalog"
    )
