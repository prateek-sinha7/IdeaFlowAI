"""T1 — the advisor's structured advice must survive to disk as JSON.

`prompt_advisor` builds a typed `PromptAdvice` and, before this, rendered it to
markdown and dropped the object. `apply-advice` needs the structure: matching a
`current_text` verbatim against a prompt body is only safe when the text arrives
unrendered. Re-parsing prose back out of fenced markdown blocks is exactly the
fuzzy behaviour spec R-06 forbids.

These tests pin the contract: a JSON sidecar next to the markdown, round-tripping
into an equal model, with paths owned by `artifacts.py` (005 §3).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from evals.grading import artifacts
from evals.grading.model import judge, prompt_advisor
from evals.grading.model.prompt_advisor import PromptAdvice, PromptEdit


# The advisor keys its report filenames on the *token*, not the agent id —
# `_token("prototype-build") == "prototype_build"`. Derived rather than hardcoded
# so this test tracks the real convention if it ever changes.
_TOKEN = prompt_advisor._token("prototype-build")


def _advice() -> PromptAdvice:
    """A PromptAdvice with the awkward content: quotes, newlines, unicode, fences."""
    return PromptAdvice(
        summary="The prompt never tells the agent to re-read design.md.",
        deviations=[
            {
                "description": 'Agent ignored the "ACTIVE TEMPLATE" block after task 3.',
                "row_ids": ["billing_console", "fleet_ops"],
                "prompt_gap": "not covered",
            }
        ],
        edits=[
            PromptEdit(
                action="add",
                section="Step 2 — Analyze the request and plan (MANDATORY)",
                current_text="",
                proposed_text="Re-read `design.md` before each task.\n\nUse ```fenced``` blocks.",
                reason="Rows billing_console, fleet_ops drifted from the design system.",
            ),
            PromptEdit(
                action="modify",
                section="Tools",
                current_text='`write_file("prototype.html", content)` — overwrite the entire file.',
                proposed_text='`write_file("prototype.html", content)` — create-only.',
                reason="write_file cannot overwrite under the deepagents backend.",
            ),
            PromptEdit(
                action="remove",
                section="What to preserve",
                current_text="You may skip design.md if unchanged.",
                proposed_text="",
                reason="Contradicts the mandatory re-read.",
            ),
        ],
        keep=["Surgical edit_file usage", "Single self-contained HTML file — 单文件"],
    )


class TestAdviceJsonPath:
    def test_lands_in_reports_next_to_the_markdown(self, tmp_path):
        path = artifacts.advice_json_path(tmp_path, "prototype-build")

        assert path.parent == tmp_path / "reports"
        assert path.name == "prompt_advice_prototype-build.json"

    def test_markdown_path_helper_matches_the_existing_filename(self, tmp_path):
        """The advisor's markdown filename must not change — only its owner does."""
        path = artifacts.advice_markdown_path(tmp_path, "prototype-build")

        assert path.parent == tmp_path / "reports"
        assert path.name == "prompt_advice_prototype-build.md"

    def test_json_and_markdown_are_siblings_differing_only_by_suffix(self, tmp_path):
        as_json = artifacts.advice_json_path(tmp_path, "prototype-specify")
        as_md = artifacts.advice_markdown_path(tmp_path, "prototype-specify")

        assert as_json.with_suffix(".md") == as_md


class TestRoundTrip:
    def test_written_json_reloads_into_an_equal_model(self, tmp_path):
        original = _advice()

        artifacts.write_advice_json(tmp_path, "prototype-build", original.model_dump())
        restored = PromptAdvice(**artifacts.read_advice_json(tmp_path, "prototype-build"))

        assert restored == original

    def test_verbatim_text_survives_exactly(self, tmp_path):
        """The whole point: `current_text` must come back byte-identical.

        Quotes, embedded newlines, backticks and non-ASCII all pass through a
        JSON round-trip untouched — which markdown rendering does not guarantee.
        """
        original = _advice()

        artifacts.write_advice_json(tmp_path, "prototype-build", original.model_dump())
        restored = PromptAdvice(**artifacts.read_advice_json(tmp_path, "prototype-build"))

        assert restored.edits[1].current_text == original.edits[1].current_text
        assert "```fenced```" in restored.edits[0].proposed_text
        assert "\n\n" in restored.edits[0].proposed_text
        assert restored.keep[1] == "Single self-contained HTML file — 单文件"

    def test_file_is_readable_json_ending_in_a_newline(self, tmp_path):
        artifacts.write_advice_json(tmp_path, "prototype-build", _advice().model_dump())

        raw = artifacts.advice_json_path(tmp_path, "prototype-build").read_text(encoding="utf-8")

        assert raw.endswith("\n")
        assert json.loads(raw)["edits"][0]["action"] == "add"

    def test_non_ascii_is_not_escaped(self, tmp_path):
        """Matches `_write_json`'s ensure_ascii=False — advice is read by humans too."""
        artifacts.write_advice_json(tmp_path, "prototype-build", _advice().model_dump())

        raw = artifacts.advice_json_path(tmp_path, "prototype-build").read_text(encoding="utf-8")

        assert "单文件" in raw


class TestMissingAdvice:
    def test_read_raises_naming_the_advise_command(self, tmp_path):
        """A run graded before the sidecar existed has only the .md.

        The error has to name the fix, because the fix is not obvious: re-running
        `advise` on an existing run costs one judge call and no agent dispatches.
        """
        with pytest.raises(FileNotFoundError) as excinfo:
            artifacts.read_advice_json(tmp_path, "prototype-build")

        message = str(excinfo.value)
        assert "advise" in message
        assert "prompt_advice_prototype-build.json" in message

    def test_empty_edit_list_round_trips(self, tmp_path):
        """An advisor that proposes nothing is valid, and must not read as missing."""
        advice = PromptAdvice(summary="No changes needed.", deviations=[], edits=[], keep=[])

        artifacts.write_advice_json(tmp_path, "prototype-build", advice.model_dump())

        assert PromptAdvice(**artifacts.read_advice_json(tmp_path, "prototype-build")).edits == []


def _stub_advise_stage(monkeypatch, *, parsed, error=None):
    """Neutralise everything in `_advise_stage` except the write path."""
    monkeypatch.setattr(prompt_advisor.config, "load_rubric", lambda *a, **k: {"judge": {}})
    monkeypatch.setattr(prompt_advisor, "_gather_evidence", lambda *a, **k: {})
    monkeypatch.setattr(prompt_advisor, "_build_advisor_prompt", lambda *a, **k: "prompt")
    monkeypatch.setattr(judge, "resolve_judge_model", lambda *a, **k: _FakeModel())
    monkeypatch.setattr(judge, "_unpack_reply", lambda reply: (parsed, error, 11, 22))


class _FakeModel:
    """Stands in for the judge model — never called for its content."""

    def with_structured_output(self, *_args, **_kwargs):
        return self

    async def ainvoke(self, *_args, **_kwargs):
        return {}


class TestAdvisorWritesBoth:
    """The wiring: `_advise_stage` must persist markdown AND json, from one object."""

    def test_both_files_land_in_reports(self, tmp_path, monkeypatch):
        _stub_advise_stage(monkeypatch, parsed=_advice())

        result = asyncio.run(
            prompt_advisor._advise_stage(
                {"agent_id": "prototype-build"},
                run_dir=tmp_path,
                workflow_dir=tmp_path,
                judge_overrides={},
            )
        )

        assert artifacts.advice_markdown_path(tmp_path, _TOKEN).exists()
        assert artifacts.advice_json_path(tmp_path, _TOKEN).exists()
        assert result["errored"] is False
        assert result["edits"] == 3

    def test_json_matches_the_advice_the_markdown_rendered(self, tmp_path, monkeypatch):
        """One object, two files — they cannot drift."""
        original = _advice()
        _stub_advise_stage(monkeypatch, parsed=original)

        asyncio.run(
            prompt_advisor._advise_stage(
                {"agent_id": "prototype-build"},
                run_dir=tmp_path,
                workflow_dir=tmp_path,
                judge_overrides={},
            )
        )

        restored = PromptAdvice(**artifacts.read_advice_json(tmp_path, _TOKEN))
        assert restored == original

    def test_advice_path_still_reports_the_markdown(self, tmp_path, monkeypatch):
        """The result key and its event payload are unchanged by this task."""
        _stub_advise_stage(monkeypatch, parsed=_advice())

        result = asyncio.run(
            prompt_advisor._advise_stage(
                {"agent_id": "prototype-build"},
                run_dir=tmp_path,
                workflow_dir=tmp_path,
                judge_overrides={},
            )
        )

        assert result["advice_path"].endswith(f"prompt_advice_{_TOKEN}.md")

    def test_an_errored_advisor_writes_neither_file(self, tmp_path, monkeypatch):
        """No half-written sidecar: a failed advise leaves the run folder clean."""
        _stub_advise_stage(monkeypatch, parsed=None, error="model returned nothing")

        result = asyncio.run(
            prompt_advisor._advise_stage(
                {"agent_id": "prototype-build"},
                run_dir=tmp_path,
                workflow_dir=tmp_path,
                judge_overrides={},
            )
        )

        assert result["errored"] is True
        assert not artifacts.advice_markdown_path(tmp_path, _TOKEN).exists()
        assert not artifacts.advice_json_path(tmp_path, _TOKEN).exists()
