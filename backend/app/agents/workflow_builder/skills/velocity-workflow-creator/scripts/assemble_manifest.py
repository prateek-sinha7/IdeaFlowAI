#!/usr/bin/env python3
"""Assemble a workflow manifest from a skeleton and one prompt file per step.

A step prompt is a long text. Written inside a JSON string, every line break and quote must be
escaped, which costs tokens and invites mistakes (docs/quick-reference.md §8). Write each prompt
as a plain text file and name it in the skeleton instead:

  <dir>/skeleton.json        the manifest; a step may hold "prompt_file": "prompts/spec.md"
                             in place of "prompt"
  <dir>/prompts/spec.md      the plain text of that step's prompt

  python scripts/assemble_manifest.py <dir> --out <manifest.json>

Every step (nested subagents included) with "prompt_file" gets "prompt" set to that file's text,
and "prompt_file" is removed. Paths are relative to <dir>; absolute paths and paths that leave
<dir> are refused. Exit status: 0 written, 2 on bad input. The output is only parsed, not
validated: run validate_manifest.py on it afterwards. Standard library only.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


class AssembleError(Exception):
    """A skeleton or prompt file cannot be assembled."""


def _resolve_inside(base: Path, relative: str) -> Path:
    """Return ``base / relative`` when it stays inside ``base``; refuse anything else."""
    if Path(relative).is_absolute() or relative.startswith(("/", "\\")):
        raise AssembleError(f"prompt_file must be relative to the manifest folder: {relative!r}")
    target = (base / relative).resolve()
    if base.resolve() not in target.parents:
        raise AssembleError(f"prompt_file leaves the manifest folder: {relative!r}")
    return target


def _assemble_steps(steps: list[Any], base: Path, where: str) -> None:
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        label = f"{where}[{index}]"
        if "prompt_file" in step:
            if "prompt" in step:
                raise AssembleError(f"{label} has both prompt and prompt_file; keep one")
            relative = step.pop("prompt_file")
            if not isinstance(relative, str) or not relative:
                raise AssembleError(f"{label}.prompt_file must be a non-empty string")
            path = _resolve_inside(base, relative)
            try:
                step["prompt"] = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise AssembleError(f"{label}: cannot read {relative!r}: {exc}") from exc
        subagents = step.get("subagents")
        if isinstance(subagents, dict) and isinstance(subagents.get("steps"), list):
            _assemble_steps(subagents["steps"], base, f"{label}.subagents.steps")


def assemble(base: Path) -> dict[str, Any]:
    """Return the manifest in ``base/skeleton.json`` with every prompt file inlined.

    Raises:
        AssembleError: the skeleton is missing or malformed, or a prompt file cannot be used.
    """
    skeleton_path = base / "skeleton.json"
    try:
        manifest = json.loads(skeleton_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssembleError(f"cannot read {skeleton_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise AssembleError("skeleton.json must hold one JSON object")
    manifest = copy.deepcopy(manifest)
    steps = manifest.get("steps")
    if isinstance(steps, list):
        _assemble_steps(steps, base, "steps")
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Assemble the manifest and write it to ``--out``; return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="folder holding skeleton.json and prompts/")
    parser.add_argument("--out", type=Path, required=True, help="where to write the manifest")
    args = parser.parse_args(argv)
    try:
        manifest = assemble(args.folder)
    except AssembleError as exc:
        print(f"assemble_manifest: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
