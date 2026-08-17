"""T26 — Derive `compatible_agents` candidates for the skills catalog by script.

Traces to R-32, R-33, RISK-01 (specs/012-per-agent-skills-custom-agents).

`compatible_agents` was deliberately stripped from all 182 SKILL.md files in
commit 9b93a0d5. This script proposes a replacement list per skill by matching
the skill's own `name` + `description` against each agent's `id` + `name` +
`role` + `description`, using plain normalized-token overlap — no LLM call.

The matching is intentionally simple and explainable:

1. Tokenize both sides (skill and agent) into a lowercase, stopword-filtered
   word set.
2. Score = raw token overlap count between the two sets.
3. An agent is a *candidate* for a skill when the overlap clears a minimum
   bar (``MIN_OVERLAP`` shared, meaningful tokens *and* covers a minimum
   fraction of the skill's own vocabulary, ``MIN_COVERAGE``).
4. A skill's overall *confidence* combines how strong its best candidate
   match is with how narrow (specific) the candidate list is — a skill that
   "matches" half the agent roster is not a confident match, it is a generic
   skill, and generic is exactly the case where the safe default (absent =
   compatible with everything, R-33) is correct.

Only skills whose confidence clears ``HIGH_CONFIDENCE`` get the frontmatter
field written (and only when run with ``--apply``); every other skill is left
with the field absent — a wrong list is worse than no list (F-08): it makes a
skill silently invisible in the picker with no error anywhere.

Usage:
    python scripts/derive_compatible_agents.py --dry-run   # default; touches nothing
    python scripts/derive_compatible_agents.py --apply     # T27 only — writes frontmatter
"""

from __future__ import annotations

import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.registry import get_all_agents_flat  # noqa: E402
from app.agents.skills_catalog import (  # noqa: E402
    GlobalSkillEntry,
    list_global_skills,
)

# ─── Tunables ────────────────────────────────────────────────────────────
MIN_OVERLAP = 2          # raw shared-token count required to consider a candidate
MIN_COVERAGE = 0.20      # overlap / len(skill_tokens) required to consider a candidate
MAX_CANDIDATES = 12      # more than this and the skill reads as generic, not specific
HIGH_CONFIDENCE = 0.55   # confidence at/above this writes the field; below leaves it absent

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your",
    "when", "then", "than", "over", "under", "using", "use", "used",
    "build", "builds", "building", "create", "creates", "creating",
    "design", "designs", "designing", "develop", "develops", "developing",
    "implement", "implements", "implementing", "review", "reviews",
    "reviewing", "best", "practice", "practices", "pattern", "patterns",
    "skill", "skills", "agent", "agents", "workflow", "workflows",
    "code", "codebase", "file", "files", "project", "projects", "task",
    "tasks", "system", "systems", "application", "applications", "app",
    "apps", "data", "user", "users", "make", "making", "help", "helps",
    "helping", "provide", "provides", "providing", "you", "are", "all",
    "any", "can", "should", "will", "not", "each", "per", "via", "based",
    "including", "include", "includes", "across", "within", "without",
    "about", "such", "these", "those", "have", "has", "had", "how",
    "what", "which", "one", "two", "new", "existing", "output", "outputs",
    "input", "inputs", "content", "generate", "generates", "generating",
    "generation", "ensure", "ensures", "ensuring", "process", "processes",
    "processing", "specific", "general", "common", "given", "well",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(*texts: str) -> set[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords/short/numeric tokens."""
    tokens: set[str] = set()
    for text in texts:
        if not text:
            continue
        for raw in _TOKEN_RE.findall(text.lower()):
            if len(raw) < 3:
                continue
            if raw.isdigit():
                continue
            if raw in _STOPWORDS:
                continue
            tokens.add(raw)
    return tokens


@dataclass(frozen=True)
class AgentVocab:
    id: str
    name: str
    role: str
    tokens: frozenset[str]


@dataclass(frozen=True)
class Candidate:
    agent_id: str
    overlap: int
    coverage: float


@dataclass(frozen=True)
class SkillDerivation:
    skill_id: str
    category: str
    candidates: list[Candidate]  # sorted by overlap desc, then coverage desc
    confidence: float
    written: bool  # would-write under the confidence bar (independent of --apply)

    @property
    def compatible_agents(self) -> list[str]:
        return [c.agent_id for c in self.candidates]


def build_agent_vocabs() -> list[AgentVocab]:
    vocabs = []
    for spec in get_all_agents_flat():
        tokens = tokenize(
            spec.id.replace("-", " "),
            spec.name,
            spec.role,
            spec.description,
        )
        vocabs.append(AgentVocab(id=spec.id, name=spec.name, role=spec.role, tokens=frozenset(tokens)))
    return vocabs


def _skill_confidence(candidates: list[Candidate]) -> float:
    """Combine best-match strength with candidate-list specificity into [0, 1]."""
    if not candidates:
        return 0.0
    best_overlap = candidates[0].overlap
    strength = min(1.0, best_overlap / 5.0)
    count = len(candidates)
    specificity = 1.0 if count <= 8 else max(0.3, 8.0 / count)
    return round(strength * specificity, 3)


def derive_for_skill(skill: GlobalSkillEntry, agent_vocabs: list[AgentVocab]) -> SkillDerivation:
    skill_tokens = tokenize(skill.name, skill.id.replace("-", " "), skill.description)

    scored: list[Candidate] = []
    for av in agent_vocabs:
        overlap_tokens = skill_tokens & av.tokens
        overlap = len(overlap_tokens)
        coverage = overlap / len(skill_tokens) if skill_tokens else 0.0
        if overlap >= MIN_OVERLAP and coverage >= MIN_COVERAGE:
            scored.append(Candidate(agent_id=av.id, overlap=overlap, coverage=round(coverage, 3)))

    scored.sort(key=lambda c: (-c.overlap, -c.coverage, c.agent_id))
    if len(scored) > MAX_CANDIDATES:
        scored = scored[:MAX_CANDIDATES]

    confidence = _skill_confidence(scored)
    written = confidence >= HIGH_CONFIDENCE and bool(scored)

    return SkillDerivation(
        skill_id=skill.id,
        category=skill.category or "uncategorized",
        candidates=scored,
        confidence=confidence,
        written=written,
    )


# ─── Frontmatter round-trip (mirrors scripts/skills_audit.py's approach) ──

_TOP_LEVEL_KEY_RE = re.compile(r"^([^\s:][^:]*):")


def _is_top_level_key_line(line: str) -> bool:
    if not line or line[0] in (" ", "\t"):
        return False
    return bool(_TOP_LEVEL_KEY_RE.match(line.rstrip("\r\n")))


def _top_level_key(line: str) -> str | None:
    m = _TOP_LEVEL_KEY_RE.match(line.rstrip("\r\n"))
    return m.group(1) if m else None


def _is_continuation(line: str) -> bool:
    stripped = line.rstrip("\r\n")
    if stripped == "":
        return False
    if line[0] in (" ", "\t"):
        return True
    if stripped == "-" or stripped.startswith("- "):
        return True
    return False


def set_compatible_agents(text: str, agent_ids: list[str]) -> tuple[str, bool]:
    """Insert or replace the `compatible_agents` frontmatter key, byte-for-byte
    otherwise. Returns (new_text, changed)."""
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
    new_field_line = f"compatible_agents: [{', '.join(agent_ids)}]\n"

    out: list[str] = []
    replaced = False
    i = 0
    while i < len(body):
        line = body[i]
        if _is_top_level_key_line(line) and _top_level_key(line) == "compatible_agents":
            replaced = True
            out.append(new_field_line)
            i += 1
            while i < len(body) and _is_continuation(body[i]):
                i += 1
            continue
        out.append(line)
        i += 1

    if not replaced:
        out.append(new_field_line)

    new_lines = lines[:1] + out + lines[closing_idx:]
    return "".join(new_lines), True


_BACKEND_DIR = Path(__file__).resolve().parent.parent
_GLOBAL_SKILL_DIR = _BACKEND_DIR / "skills" / "global"


def apply_write(derivation: SkillDerivation) -> bool:
    """Write the derived compatible_agents list into the skill's SKILL.md. Returns
    True if the file was changed."""
    skill_md = _GLOBAL_SKILL_DIR / derivation.skill_id / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    new_text, changed = set_compatible_agents(text, derivation.compatible_agents)
    if not changed:
        return False
    skill_md.write_text(new_text, encoding="utf-8")
    return True


# ─── Reporting ─────────────────────────────────────────────────────────

def print_summary(derivations: list[SkillDerivation]) -> None:
    total = len(derivations)
    matched = [d for d in derivations if d.written]
    open_ = [d for d in derivations if not d.written]

    print(f"total skills: {total}")
    print(f"got a compatible_agents list: {len(matched)}")
    print(f"left open (absent = compatible with all): {len(open_)}")
    print()

    print("per-category breakdown:")
    categories = sorted({d.category for d in derivations})
    for cat in categories:
        cat_derivations = [d for d in derivations if d.category == cat]
        cat_matched = [d for d in cat_derivations if d.written]
        print(f"  {cat}: {len(cat_matched)}/{len(cat_derivations)} matched")
    print()

    borderline = [d for d in derivations if d.candidates]
    borderline.sort(key=lambda d: d.confidence)
    print("20 lowest-confidence proposed matches (for human review):")
    for d in borderline[:20]:
        status = "WRITE" if d.written else "OPEN "
        agents = ", ".join(d.compatible_agents)
        print(f"  [{status}] {d.skill_id} (confidence={d.confidence}) -> [{agents}]")


def main() -> int:
    parser = ArgumentParser(description="Derive compatible_agents candidates for the skills catalog")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the derivation only; touch nothing (default behavior).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write compatible_agents into SKILL.md for high-confidence skills. "
        "Without this flag, the script never writes to disk.",
    )
    args = parser.parse_args()

    apply_mode = args.apply
    if apply_mode and args.dry_run:
        print("--apply and --dry-run both given; --dry-run wins, nothing will be written.")
        apply_mode = False

    agent_vocabs = build_agent_vocabs()
    skills = list_global_skills()

    derivations = [derive_for_skill(skill, agent_vocabs) for skill in skills]

    if apply_mode:
        changed = 0
        for d in derivations:
            if d.written:
                if apply_write(d):
                    changed += 1
        print(f"applied: wrote compatible_agents to {changed} file(s)")
        print()

    print_summary(derivations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
