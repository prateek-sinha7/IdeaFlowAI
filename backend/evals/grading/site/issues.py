"""What a phase got wrong and right, grouped — not every line, one row each.

A phase with five rows produces five judge critiques plus a browser sweep per
row, and printing all of them is how a report becomes unreadable. The same
defect usually appears on several rows, so the useful unit is the *group*: what
it is, how many rows it hit, and which ones.

Two sources, deliberately kept apart because they carry different authority:

- **judge** — the model's opinion. Its `recurring_weaknesses` are already
  clustered by the grader, so those are used as-is rather than re-clustered.
- **code** — the deterministic browser sweep. Reproducible, free, and not a
  matter of opinion, so a console error and a judge's stylistic note never
  merge into one row.

Grouping is exact-after-normalisation, not fuzzy. A cheap similarity metric
that silently merges two different defects is worse than showing both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Normalisation for grouping: fold case and whitespace, drop trailing
# punctuation, and mask the parts that differ per row (quoted strings, numbers,
# selectors) so "3 of 12 buttons" and "5 of 9 buttons" land in one group.
_WHITESPACE = re.compile(r"\s+")
_QUOTED = re.compile(r"[\"'`][^\"'`]{1,80}[\"'`]")
_NUMBERS = re.compile(r"\b\d+(\.\d+)?\b")
_TRAILING = re.compile(r"[\s.;:,]+$")

SOURCE_JUDGE = "judge"
SOURCE_CODE = "code"

# Kinds in the order a reader should meet them: what breaks the artifact first,
# opinion last.
KIND_ORDER = (
    "uncaught exception",
    "console error",
    "dead nav",
    "nav coverage",
    "interaction failure",
    "static issue",
    "static warning",
    "score reduction",
    "weakness",
    "strength",
)


@dataclass(frozen=True)
class IssueGroup:
    """One defect, and every row it appeared on."""

    kind: str
    source: str
    detail: str
    row_ids: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.row_ids)


@dataclass(frozen=True)
class IssueSummary:
    """One phase's findings, split by what a reader does with each.

    Weaknesses are what to fix, strengths are what an edit must not break, and
    code findings are the browser's reproducible verdict. They are counted and
    tabled apart because merging them buries the actionable half.
    """

    weaknesses: tuple[IssueGroup, ...] = ()
    strengths: tuple[IssueGroup, ...] = ()
    code: tuple[IssueGroup, ...] = ()
    rows_total: int = 0

    @property
    def groups(self) -> tuple[IssueGroup, ...]:
        return self.weaknesses + self.code + self.strengths

    @property
    def weakness_count(self) -> int:
        return sum(group.count for group in self.weaknesses)

    @property
    def strength_count(self) -> int:
        return sum(group.count for group in self.strengths)

    @property
    def code_count(self) -> int:
        return sum(group.count for group in self.code)

    @property
    def problem_count(self) -> int:
        """Everything a reader would act on — strengths are not a problem."""
        return self.weakness_count + self.code_count

    @property
    def total(self) -> int:
        return sum(group.count for group in self.groups)

    @property
    def distinct(self) -> int:
        return len(self.groups)

    @property
    def rows_affected(self) -> int:
        return len({
            row_id
            for group in self.weaknesses + self.code
            for row_id in group.row_ids
        })

    @property
    def clean_rows(self) -> int:
        return max(0, self.rows_total - self.rows_affected)


def summarize(stage) -> IssueSummary:
    """Group one stage's findings into weaknesses, strengths and code findings."""
    weak: dict[tuple[str, str, str], list[str]] = {}
    strong: dict[tuple[str, str, str], list[str]] = {}
    code: dict[tuple[str, str, str], list[str]] = {}

    def adder(into):
        def add(kind: str, source: str, detail: str, row_id: str) -> None:
            text = (detail or "").strip()
            if not text:
                return
            key = (kind, source, _normalise(text))
            into.setdefault(key, [])
            if row_id not in into[key]:
                into[key].append(row_id)
        return add

    add_weak, add_strong, add_code = adder(weak), adder(strong), adder(code)

    # The judge's own clusters: already grouped by the grader, with the rows it
    # saw each on. Re-clustering them here would second-guess it.
    for cluster in stage.recurring_weaknesses or []:
        for row_id in cluster.get("row_ids") or []:
            add_weak("weakness", SOURCE_JUDGE, cluster.get("evidence") or "", row_id)
    for cluster in stage.recurring_strengths or []:
        for row_id in cluster.get("row_ids") or []:
            add_strong("strength", SOURCE_JUDGE, cluster.get("evidence") or "", row_id)

    clustered_weak = _cluster_keys(stage.recurring_weaknesses)
    clustered_strong = _cluster_keys(stage.recurring_strengths)

    for row in stage.rows:
        # A per-row note the grader did not cluster is still worth showing; one
        # it did is already represented above.
        for weakness in row.weaknesses or []:
            if _normalise(str(weakness)) not in clustered_weak:
                add_weak("weakness", SOURCE_JUDGE, str(weakness), row.row_id)
        for strength in row.strengths or []:
            if _normalise(str(strength)) not in clustered_strong:
                add_strong("strength", SOURCE_JUDGE, str(strength), row.row_id)
        for dimension, cap in (row.score_caps or {}).items():
            detail = _cap_detail(dimension, cap)
            if detail:
                add_weak("score reduction", SOURCE_JUDGE, detail, row.row_id)
        _add_code_issues(add_code, row)

    return IssueSummary(
        weaknesses=_build(weak, stage),
        strengths=_build(strong, stage),
        code=_build(code, stage),
        rows_total=len(stage.rows),
    )


def _cluster_keys(clusters) -> set:
    return {_normalise(cluster.get("evidence") or "") for cluster in clusters or []}


def _build(collected: dict, stage) -> tuple:
    """Collected keys to groups, widest first."""
    groups = [
        IssueGroup(
            kind=kind,
            source=source,
            detail=_display(key_text, stage),
            row_ids=tuple(rows),
        )
        for (kind, source, key_text), rows in collected.items()
    ]
    groups.sort(key=lambda group: (-group.count, _kind_rank(group.kind), group.detail))
    return tuple(groups)


def _add_code_issues(add, row) -> None:
    """The browser sweep's findings for one row — reproducible, not opinion."""
    finding = row.code_finding or {}
    if not finding:
        return
    rendered = finding.get("render") or {}
    interactions = finding.get("interactions") or {}

    for issue in finding.get("issues") or []:
        add("static issue", SOURCE_CODE, str(issue), row.row_id)
    for warning in finding.get("warnings") or []:
        add("static warning", SOURCE_CODE, str(warning), row.row_id)
    for error in rendered.get("console_errors") or []:
        add("console error", SOURCE_CODE, str(error), row.row_id)
    for error in rendered.get("page_errors") or []:
        add("uncaught exception", SOURCE_CODE, str(error), row.row_id)
    for error in rendered.get("coverage_errors") or []:
        add("nav coverage", SOURCE_CODE, str(error), row.row_id)
    for nav in rendered.get("nav_results") or []:
        if not nav.get("ok"):
            add(
                "dead nav",
                SOURCE_CODE,
                f"{nav.get('href')} expected {nav.get('expected')}, "
                f"activated {nav.get('activated')}",
                row.row_id,
            )
    for failure in interactions.get("failures") or []:
        errors = "; ".join(str(error) for error in failure.get("errors") or [])
        add(
            "interaction failure",
            SOURCE_CODE,
            f"{failure.get('action')} {failure.get('target')}: {errors}",
            row.row_id,
        )


def _normalise(text: str) -> str:
    """The grouping key: same defect, different row, one key."""
    folded = _WHITESPACE.sub(" ", str(text).strip().lower())
    folded = _QUOTED.sub("…", folded)
    folded = _NUMBERS.sub("#", folded)
    return _TRAILING.sub("", folded)


def _display(key_text: str, stage) -> str:
    """A readable representative for a group — the first real text, not the key.

    The normalised key has numbers and quotes masked, which is right for
    grouping and wrong for reading, so the group shows an actual example.
    """
    for row in stage.rows:
        for candidate in _row_texts(row):
            if _normalise(candidate) == key_text:
                return candidate
    for clusters in (stage.recurring_weaknesses, stage.recurring_strengths):
        for cluster in clusters or []:
            evidence = cluster.get("evidence") or ""
            if _normalise(evidence) == key_text:
                return evidence
    return key_text


def _row_texts(row) -> list[str]:
    """Every issue string one row produced, for recovering a display example."""
    finding = row.code_finding or {}
    rendered = finding.get("render") or {}
    interactions = finding.get("interactions") or {}
    texts: list[str] = [str(weakness) for weakness in row.weaknesses or []]
    texts += [str(strength) for strength in row.strengths or []]
    texts += [str(issue) for issue in finding.get("issues") or []]
    texts += [str(warning) for warning in finding.get("warnings") or []]
    texts += [str(error) for error in rendered.get("console_errors") or []]
    texts += [str(error) for error in rendered.get("page_errors") or []]
    texts += [str(error) for error in rendered.get("coverage_errors") or []]
    texts += [
        f"{nav.get('href')} expected {nav.get('expected')}, activated {nav.get('activated')}"
        for nav in rendered.get("nav_results") or []
        if not nav.get("ok")
    ]
    texts += [
        f"{failure.get('action')} {failure.get('target')}: "
        + "; ".join(str(error) for error in failure.get("errors") or [])
        for failure in interactions.get("failures") or []
    ]
    texts += [
        detail
        for detail in (
            _cap_detail(dimension, cap)
            for dimension, cap in (row.score_caps or {}).items()
        )
        if detail
    ]
    return texts


def _cap_detail(dimension: str, cap: dict) -> str | None:
    """One dimension's score reduction, across both cap schemas.

    The severity-priced judge writes `final`; the older count-based one wrote
    `capped_to`. A cap that reduced nothing is not an issue and is dropped —
    which is also what keeps a bare "95 → None" off the page when neither key
    is present.
    """
    before = cap.get("reported")
    after = cap.get("final", cap.get("capped_to"))
    if before is None or after is None or before == after:
        return None
    return f"{dimension} reduced {before} → {after}"


def _kind_rank(kind: str) -> int:
    try:
        return KIND_ORDER.index(kind)
    except ValueError:
        return len(KIND_ORDER)
