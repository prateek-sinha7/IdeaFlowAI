#!/usr/bin/env python3
"""Audit the skills catalog for structural and content violations.

`cursor` is deliberately NOT a provenance pattern. Every occurrence in this
catalog is a CSS or screen-reader cursor (e.g. the accessibility skill's
"visibility of the keyboard/screen reader cursor"), not a reference to the
Cursor IDE. A blind `cursor` regex produces only false positives.
"""

import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

import frontmatter

AUDIT_DIR = Path(__file__).resolve().parents[1] / "skills" / "global"
PROVENANCE_PATTERNS = [
    "claude",
    "ecc",
    "superpowers",
    "obra",
    "anthropic",
    "openai",
    "gpt-4",
    "chatgpt",
    "copilot",
]

@dataclass(frozen=True)
class Violation:
    skill_id: str
    kind: str
    detail: str


def audit(root: Path = AUDIT_DIR) -> list[Violation]:
    """Audit all skills in root for violations."""
    violations = []

    if not root.exists():
        return violations

    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_id = skill_dir.name
        skill_md = skill_dir / "SKILL.md"

        # Check: SKILL.md exists
        if not skill_md.exists():
            violations.append(
                Violation(skill_id, "frontmatter", "SKILL.md not found")
            )
            continue

        # Parse frontmatter
        try:
            with open(skill_md, encoding="utf-8") as f:
                post = frontmatter.load(f)
        except Exception as e:
            violations.append(
                Violation(skill_id, "frontmatter", f"frontmatter parse failed: {e}")
            )
            continue

        # Check: name and description present
        if "name" not in post.metadata:
            violations.append(
                Violation(skill_id, "frontmatter", "missing 'name' in frontmatter")
            )
        if "description" not in post.metadata:
            violations.append(
                Violation(
                    skill_id, "frontmatter", "missing 'description' in frontmatter"
                )
            )

        # Check: name matches directory
        if "name" in post.metadata and post.metadata["name"] != skill_id:
            violations.append(
                Violation(
                    skill_id,
                    "frontmatter",
                    f"name '{post.metadata['name']}' does not match directory '{skill_id}'",
                )
            )

        # Check: description length
        if "description" in post.metadata:
            desc = post.metadata["description"]
            if len(desc) > 200:
                violations.append(
                    Violation(
                        skill_id,
                        "frontmatter",
                        f"description length {len(desc)} > 200",
                    )
                )

        # Check: forbidden keys
        forbidden_keys = {"compatible_agents", "source", "sourceLabel"}
        for key in forbidden_keys:
            if key in post.metadata:
                violations.append(
                    Violation(
                        skill_id, "frontmatter", f"forbidden key '{key}' present"
                    )
                )

        # Check: identity (first 200 chars)
        body = post.content[:200]
        if re.search(r"\byou are an?\b", body, re.IGNORECASE):
            violations.append(
                Violation(
                    skill_id,
                    "identity",
                    "body begins with 'you are a/an' pattern",
                )
            )

        # Check: tooling (execute tool)
        body_full = post.content
        if re.search(
            r"\b(call|use|invoke|run)\s+(the\s+)?`?execute`?",
            body_full,
            re.IGNORECASE,
        ):
            violations.append(
                Violation(skill_id, "tooling", "body mentions 'execute' tool")
            )

        # Check: provenance (body)
        body_lower = body_full.lower()
        for pattern in PROVENANCE_PATTERNS:
            # Letter-boundary match: matches adjacent to `_`/digits (e.g.
            # OPENAI_API_KEY) but not inside a longer alphabetic word (e.g.
            # openairline).
            regex = rf"(?<![A-Za-z]){re.escape(pattern)}(?![A-Za-z])"
            if re.search(regex, body_lower):
                count = len(re.findall(regex, body_lower))
                violations.append(
                    Violation(
                        skill_id,
                        "provenance",
                        f"'{pattern}' found ({count} occurrence{'s' if count != 1 else ''})",
                    )
                )

        # Check: provenance (description) — the description is advertised to every
        # agent in every run and is the entire basis on which the model decides
        # whether to open the skill body, so provenance here is the most visible
        # possible leak.
        desc_lower = str(post.metadata.get("description", "")).lower()
        for pattern in PROVENANCE_PATTERNS:
            regex = rf"(?<![A-Za-z]){re.escape(pattern)}(?![A-Za-z])"
            if re.search(regex, desc_lower):
                violations.append(
                    Violation(
                        skill_id,
                        "provenance",
                        f"'{pattern}' in description",
                    )
                )

        # Check: provenance (sibling *.md files) — prose/markdown files next to
        # SKILL.md in the same skill directory can carry provenance leaks too
        # (e.g. a CREATION-LOG.md). Scope is deliberately markdown-only, not
        # .ts/.sh/other extensions.
        for sibling in sorted(skill_dir.glob("*.md")):
            if sibling.name == "SKILL.md":
                continue
            try:
                sibling_text = sibling.read_text(encoding="utf-8").lower()
            except Exception:
                continue
            for pattern in PROVENANCE_PATTERNS:
                regex = rf"(?<![A-Za-z]){re.escape(pattern)}(?![A-Za-z])"
                if re.search(regex, sibling_text):
                    count = len(re.findall(regex, sibling_text))
                    violations.append(
                        Violation(
                            skill_id,
                            "provenance",
                            f"'{pattern}' found in {sibling.name} "
                            f"({count} occurrence{'s' if count != 1 else ''})",
                        )
                    )

    return violations


_TOP_LEVEL_KEY_RE = re.compile(r"^([^\s:][^:]*):")


def _is_top_level_key_line(line: str) -> bool:
    """True if line is an unindented `key:` line (start of a frontmatter field)."""
    if not line or line[0] in (" ", "\t"):
        return False
    return bool(_TOP_LEVEL_KEY_RE.match(line.rstrip("\r\n")))


def _top_level_key(line: str) -> str | None:
    m = _TOP_LEVEL_KEY_RE.match(line.rstrip("\r\n"))
    return m.group(1) if m else None


def _is_continuation(line: str) -> bool:
    """True if line belongs to the preceding key: more-indented, or a flush-left
    `- item` list entry."""
    stripped = line.rstrip("\r\n")
    if stripped == "":
        return False
    if line[0] in (" ", "\t"):
        return True
    if stripped == "-" or stripped.startswith("- "):
        return True
    return False


def _strip_forbidden_keys(text: str, forbidden_keys: set[str]) -> tuple[str, bool]:
    """Remove forbidden top-level frontmatter keys (+ continuation lines) from raw
    SKILL.md text, byte-for-byte otherwise. Returns (new_text, changed)."""
    lines = text.splitlines(keepends=True)

    if not lines or lines[0].rstrip("\r\n") != "---":
        return text, False

    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            closing_idx = i
            break
    if closing_idx is None:
        return text, False

    body = lines[1:closing_idx]
    out: list[str] = []
    removed = False
    i = 0
    while i < len(body):
        line = body[i]
        if _is_top_level_key_line(line) and _top_level_key(line) in forbidden_keys:
            removed = True
            i += 1
            while i < len(body) and _is_continuation(body[i]):
                i += 1
            continue
        out.append(line)
        i += 1

    if not removed:
        return text, False

    new_lines = lines[:1] + out + lines[closing_idx:]
    return "".join(new_lines), True


def fix(root: Path = AUDIT_DIR) -> int:
    """Remove forbidden keys from all skills' raw frontmatter text (no
    reserialization). Returns number of files changed."""
    changed = 0
    forbidden_keys = {"compatible_agents", "source", "sourceLabel"}

    if not root.exists():
        return changed

    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            with open(skill_md, encoding="utf-8", newline="") as f:
                text = f.read()
        except Exception:
            continue

        new_text, did_change = _strip_forbidden_keys(text, forbidden_keys)
        if not did_change:
            continue

        with open(skill_md, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)

        changed += 1

    return changed


def main() -> int:
    """Main entry point."""
    parser = ArgumentParser(description="Audit skills catalog for violations")
    parser.add_argument("--fix", action="store_true", help="Fix violations")
    args = parser.parse_args()

    if args.fix:
        changed = fix()
        print(f"Fixed {changed} file(s)")

    violations = audit()
    skill_count = len([d for d in AUDIT_DIR.iterdir() if d.is_dir()])

    # Print summary
    print(f"scanned {skill_count} skills, {len(violations)} violations")

    # Print violations
    for v in sorted(violations, key=lambda x: (x.skill_id, x.kind)):
        print(f"{v.skill_id} [{v.kind}] {v.detail}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
