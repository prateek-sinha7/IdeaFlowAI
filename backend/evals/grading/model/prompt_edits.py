"""Pure: apply the advisor's proposed edits to an AGENT.md prompt body.

No I/O, no model calls, nothing imported from this package — text in, text out.
The caller reads and writes the files; this module decides only *what the new
text should be*. That is what makes the risky part — anchor matching and the
frontmatter split — testable in milliseconds with no fixtures.

Two rules drive every decision here:

**The frontmatter is never edited.** It is the engine's contract (`id`,
`pipeline_type`, `order`, `produces`/`consumes`, `tools`, `gate`, `injects`,
`model`), read at import time to build `PIPELINE_AGENTS` and validated as a DAG.
So it is split off as an opaque string and handed back untouched. Note what is
*not* used: `frontmatter.dumps()` would re-serialise through PyYAML and reorder
keys, restyle quotes and drop comments — silently rewriting that contract while
claiming to have edited only prose.

**An ambiguity fails.** A `current_text` that matches zero times, or twice, or an
`add` whose anchor cannot be resolved, raises rather than guessing. A misplaced
edit looks applied, changes how an agent behaves, and is invisible to a skimmed
diff review; a failed command costs one re-run.
"""

from __future__ import annotations

import re

# `AGENT.vN.md` — the archived bodies. N ascends; the live prompt is AGENT.md.
_ARCHIVE_PATTERN = re.compile(r"^AGENT\.v(\d+)\.md$")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_DELIMITER = "---"
# How much of an edit's text is echoed to the terminal. The file gets all of it.
_DISPLAY_LIMIT = 160


class PromptFileError(Exception):
    """An AGENT.md that cannot be split into frontmatter and body."""


class EditError(Exception):
    """An edit that cannot be applied unambiguously. Nothing is written."""


def split_agent_file(text: str) -> tuple[str, str]:
    """Split an AGENT.md into `(prefix, body)` where `prefix + body == text`.

    `prefix` is the frontmatter block *including* its closing `---` line, kept as
    an opaque string so it can be written back byte-for-byte. Only the first
    closing delimiter counts — `---` is also a horizontal rule, and these prompts
    use plenty of them.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIMITER:
        raise PromptFileError(
            "no YAML frontmatter: an AGENT.md must open with a '---' line"
        )
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            return "".join(lines[: index + 1]), "".join(lines[index + 1 :])
    raise PromptFileError(
        "frontmatter is never closed: no second '---' line. Refusing to treat "
        "the whole file as prompt body"
    )


def apply_edits(prefix: str, body: str, edits: list[dict]) -> tuple[str, list[dict]]:
    """Apply every edit to `body`, or raise. Returns `(new_body, refused)`.

    `prefix` is read — never modified — only to recognise an edit that is really
    aiming at the frontmatter. Those are *refused* (returned in `refused`, the
    remaining edits still apply) rather than fatal, because they were never going
    to touch the body. Everything else that cannot be applied raises `EditError`,
    and the caller writes nothing.
    """
    current = body
    refused: list[dict] = []

    for index, edit in enumerate(edits, start=1):
        action = str(edit.get("action") or "").strip().lower()
        section = str(edit.get("section") or "")
        current_text = str(edit.get("current_text") or "")
        proposed_text = str(edit.get("proposed_text") or "")

        reason = _frontmatter_refusal(prefix, current, action, section, current_text)
        if reason is not None:
            refused.append(
                {"index": index, "action": action, "section": section, "reason": reason}
            )
            continue

        if action in ("modify", "remove"):
            replacement = proposed_text if action == "modify" else ""
            current = _replace_once(current, current_text, replacement, index, action)
        elif action == "add":
            current = _insert(current, section, proposed_text, index)
        else:
            raise EditError(
                f"edit {index}: unknown action {action!r} — expected add, remove or modify. "
                "Refusing to skip it silently"
            )

    return current, refused


def next_archive_number(existing_names: list[str]) -> int:
    """`max(N) + 1` over `AGENT.vN.md` names; 1 when there are none.

    Gaps are never filled and numbers never reused: with v1 and v3 present the
    next is v4. Reusing v2 would make the sequence lie about the order the
    prompts were superseded in, which is the only thing the numbering is for.
    """
    numbers = [
        int(match.group(1))
        for match in (_ARCHIVE_PATTERN.match(name) for name in existing_names)
        if match is not None
    ]
    return max(numbers) + 1 if numbers else 1


def archive_name(number: int) -> str:
    """The filename for archive `number` — the inverse of `next_archive_number`."""
    return f"AGENT.v{number}.md"


def render_diff(edits: list[dict], refused: list[dict]) -> str:
    """The terminal summary: what was applied, and what was refused and why."""
    refused_indexes = {item["index"] for item in refused}
    lines: list[str] = []

    for index, edit in enumerate(edits, start=1):
        if index in refused_indexes:
            continue
        action = str(edit.get("action") or "").strip().lower()
        lines.append(f"  [{index}] {action:<7} {edit.get('section') or '(no section)'}")
        if edit.get("reason"):
            lines.append(f"      why: {_clip(str(edit['reason']))}")
        if edit.get("current_text"):
            lines.append(f"      - {_clip(str(edit['current_text']))}")
        if edit.get("proposed_text"):
            lines.append(f"      + {_clip(str(edit['proposed_text']))}")

    if not lines:
        lines.append("  (no edits applied)")

    for item in refused:
        lines.append(
            f"  [{item['index']}] refused {item.get('section') or '(no section)'}"
            f" — {item['reason']}"
        )

    return "\n".join(lines)


# ── internals ─────────────────────────────────────────────────────────────


def _frontmatter_refusal(
    prefix: str, body: str, action: str, section: str, current_text: str
) -> str | None:
    """Is this edit really aiming at the frontmatter? Judged by evidence, not by name.

    Matching field *names* would be wrong: `## Tools` is a legitimate body heading
    in several prompts while `tools:` is a frontmatter key, so a name check would
    refuse a perfectly good edit. The test is whether the text actually lives in
    the frontmatter and nowhere in the body.
    """
    stripped = current_text.strip()
    if stripped and stripped not in body and stripped in prefix:
        return "targets the frontmatter, which is the engine's contract"

    if action == "add":
        key = section.strip().rstrip(":").strip()
        if key and re.fullmatch(r"[a-z_][a-z0-9_]*", key) and key not in body:
            if re.search(rf"^{re.escape(key)}\s*:", prefix, re.MULTILINE):
                return f"section {key!r} is a frontmatter field, not a prompt section"
    return None


def _replace_once(
    body: str, needle: str, replacement: str, index: int, action: str
) -> str:
    """Replace `needle` exactly once, or raise naming the edit and the count."""
    if not needle.strip():
        raise EditError(f"edit {index} ({action}): current_text is empty")

    count = body.count(needle)
    if count != 1:
        raise EditError(
            f"edit {index} ({action}): current_text occurs {count} times in the prompt "
            f"body — expected exactly 1. Nothing was written. Text: {_clip(needle)!r}"
        )
    return body.replace(needle, replacement, 1)


def _insert(body: str, section: str, text: str, index: int) -> str:
    """Insert `text` at the anchor named by `section` (AD-04).

    Unique heading, else unique substring, else raise. There is deliberately no
    end-of-file fallback: an `add` that quietly lands at the bottom of a 9 KB
    prompt is the single most damaging way this command could fail.
    """
    if not text.strip():
        raise EditError(f"edit {index} (add): proposed_text is empty")

    anchor = section.strip()
    if not anchor:
        raise EditError(
            f"edit {index} (add): no section given, so there is no anchor to insert at"
        )

    at = _heading_section_end(body, anchor)
    if at is None:
        at = _paragraph_end(body, anchor, index)

    block = text.strip("\n")
    return body[:at].rstrip("\n") + "\n\n" + block + "\n\n" + body[at:].lstrip("\n")


def _heading_section_end(body: str, anchor: str) -> int | None:
    """Offset at the end of the section owned by a heading equal to `anchor`.

    A section ends at the next heading *or* the next `---` rule, so an insertion
    stays inside the section a reader would say it belongs to.
    """
    lines = body.splitlines(keepends=True)
    starts = [
        i
        for i, line in enumerate(lines)
        if (match := _HEADING_PATTERN.match(line)) and match.group(1) == anchor
    ]
    if len(starts) != 1:
        return None

    offset = sum(len(line) for line in lines[: starts[0] + 1])
    for line in lines[starts[0] + 1 :]:
        if _HEADING_PATTERN.match(line) or line.strip() == _DELIMITER:
            break
        offset += len(line)
    return offset


def _paragraph_end(body: str, anchor: str, index: int) -> int:
    """Offset at the end of the paragraph containing the unique `anchor`."""
    count = body.count(anchor)
    if count != 1:
        raise EditError(
            f"edit {index} (add): anchor {_clip(anchor)!r} matches no heading and occurs "
            f"{count} times in the body — expected exactly 1. Refusing to guess where "
            "this belongs"
        )
    at = body.index(anchor) + len(anchor)
    break_at = body.find("\n\n", at)
    return len(body) if break_at == -1 else break_at


def _clip(text: str) -> str:
    """One line, bounded — the terminal echo, never what is written to the file."""
    flat = " ".join(text.split())
    return flat if len(flat) <= _DISPLAY_LIMIT else flat[: _DISPLAY_LIMIT - 1] + "…"
