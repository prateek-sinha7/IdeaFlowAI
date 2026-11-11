#!/usr/bin/env python3
"""Score a workflow manifest against a deliverable playbook (docs/playbooks/).

The requirement-fit check for generated workflows. It is deterministic and offline: it
reports which expert stages of the playbook the manifest covers, through the files its prompts
name, its human gates and its validators. It does not judge prompt quality. Pair it with a real
run on the reference requests (docs/evals/reference-requests.md).

Usage (from the skill folder or with the absolute path):

  python scripts/playbook_fit.py <manifest.json> --playbook ui-prototype --depth full
  python scripts/playbook_fit.py <manifest.json> --playbook requirements-document --depth lite --json

Exit status: 0 when every expected stage is covered, 1 when some are missing, 2 for bad input.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
PLAYBOOKS = ("ui-prototype", "requirements-document")
DEPTHS = ("full", "lite")
HUMAN_GATES = frozenset({"human", "before-human"})
HTML_VALIDATORS = frozenset({"html_static", "html_render"})


@dataclass(frozen=True)
class Stage:
    """One playbook stage and how the manifest shows it.

    Attributes:
        key: Stage name used in the report.
        label: Human-readable description.
        full_only: True when the Lite depth merges or drops the stage.
        covered: Predicate over the list of top-level step mappings.
    """

    key: str
    label: str
    full_only: bool
    covered: Callable[[list[Mapping[str, Any]]], bool]


def _prompts(steps: list[Mapping[str, Any]]) -> Iterator[str]:
    for step in steps:
        prompt = step.get("prompt")
        if isinstance(prompt, str):
            yield prompt


def _mentions(steps: list[Mapping[str, Any]], *needles: str) -> bool:
    return any(needle in prompt for prompt in _prompts(steps) for needle in needles)


def _gated_on_gap_questions(steps: list[Mapping[str, Any]]) -> bool:
    """A human-family gate on a step whose prompt names the gap or question list."""
    for step in steps:
        gates = step.get("gates") or []
        prompt = str(step.get("prompt") or "")
        if HUMAN_GATES & set(gates) and ("gaps" in prompt or "question" in prompt.lower()):
            return True
    return False


def _has_html_checks(steps: list[Mapping[str, Any]]) -> bool:
    return any(HTML_VALIDATORS & set(step.get("validators") or []) for step in steps)


def _has_critic_loop(steps: list[Mapping[str, Any]]) -> bool:
    for step in steps:
        route = step.get("route")
        if isinstance(route, Mapping) and route.get("outcomes"):
            return True
    return False


UI_PROTOTYPE: tuple[Stage, ...] = (
    Stage("read", "Read the uploads into notes", False,
          lambda s: _mentions(s, "notes/")),
    Stage("analyze", "Analyze into numbered requirements", False,
          lambda s: _mentions(s, "requirements.md")),
    Stage("clarify", "Ask the open questions at a human gate", False,
          _gated_on_gap_questions),
    Stage("spec", "Write the spec with screens, journeys and states", False,
          lambda s: _mentions(s, "spec.md")),
    Stage("design", "Design layout, tokens and components", True,
          lambda s: _mentions(s, "design.md", "screens.json")),
    Stage("build", "Build the prototype file with HTML checks", False,
          lambda s: _has_html_checks(s)),
    Stage("qa", "Review the build with a critic loop", True,
          _has_critic_loop),
)

REQUIREMENTS_DOCUMENT: tuple[Stage, ...] = (
    Stage("read", "Read the uploads into notes", False,
          lambda s: _mentions(s, "notes/")),
    Stage("analyze", "Analyze into numbered requirements", False,
          lambda s: _mentions(s, "requirements.md")),
    Stage("clarify", "Ask the open questions at a human gate", False,
          _gated_on_gap_questions),
    Stage("stories", "Write user stories with acceptance criteria", True,
          lambda s: _mentions(s, "stories.md")),
    Stage("nfr", "Write non-functional requirements with targets", True,
          lambda s: _mentions(s, "nfr.md")),
    Stage("assemble", "Assemble the spec, PRD or backlog", False,
          lambda s: _mentions(s, "spec.md", "prd.md", "backlog.md")),
    Stage("review", "Review the document with a critic loop", True,
          _has_critic_loop),
)

PLAYBOOK_STAGES: Mapping[str, tuple[Stage, ...]] = {
    "ui-prototype": UI_PROTOTYPE,
    "requirements-document": REQUIREMENTS_DOCUMENT,
}


def score(manifest: Mapping[str, Any], playbook: str, depth: str) -> dict[str, Any]:
    """Return the stage coverage of ``manifest`` for ``playbook`` at ``depth``.

    Args:
        manifest: A parsed workflow manifest with a top-level ``steps`` list.
        playbook: One of :data:`PLAYBOOKS`.
        depth: ``full`` expects every stage; ``lite`` skips the ``full_only`` stages.

    Returns:
        A dict with ``covered``, ``missing`` (stage keys), ``expected`` count and ``percent``.
    """
    steps = [s for s in manifest.get("steps") or [] if isinstance(s, Mapping)]
    expected = [
        stage for stage in PLAYBOOK_STAGES[playbook]
        if depth == "full" or not stage.full_only
    ]
    covered = [stage.key for stage in expected if stage.covered(steps)]
    missing = [stage.key for stage in expected if stage.key not in covered]
    percent = round(100 * len(covered) / len(expected)) if expected else 100
    return {
        "playbook": playbook,
        "depth": depth,
        "expected": len(expected),
        "covered": covered,
        "missing": missing,
        "percent": percent,
    }


def _load(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"playbook_fit: cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"playbook_fit: {path} must hold one JSON object (the manifest)")
    return data


def main(argv: list[str] | None = None) -> int:
    """Run the scorer from the command line and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--playbook", choices=PLAYBOOKS, required=True)
    parser.add_argument("--depth", choices=DEPTHS, default="full")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)

    result = score(_load(args.manifest), args.playbook, args.depth)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.playbook} ({args.depth}): {result['percent']} % of {result['expected']} stages")
        print(f"  covered: {', '.join(result['covered']) or '-'}")
        print(f"  missing: {', '.join(result['missing']) or '-'}")
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
