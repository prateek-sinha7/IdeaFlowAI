"""app/agents/skill_staging.py — stage user-attached skills into the run sandbox.

The deepagents library (pinned 0.6.7) scans directory *sources* for
``<source>/<skill-name>/SKILL.md`` files, parses YAML frontmatter, and
advertises each skill (name + description, two lines) in the system prompt.
The body is never injected — the model reads it on demand via the sandbox
filesystem tools.

User-attached skills arrive as ``{"id": ..., "name": ..., "content": ...}``
payloads, where ``content`` is ``GlobalSkillEntry.content`` —
``frontmatter.loads(...).content``, i.e. the skill BODY ONLY, frontmatter
already stripped by the catalog loader (see ``app/agents/skills_catalog.py``).
There is therefore no frontmatter anywhere in the input, and a staged
``SKILL.md`` must SYNTHESIZE one: deepagents silently drops any staged file
whose frontmatter fails to parse, so a missing/malformed ``name``/
``description`` block means the skill just never shows up, with no error
surfaced anywhere.

``/skills`` is a POSIX path resolved by the runner's ``FilesystemBackend``
against the sandbox root (not a real host path) — it is what
``sources=[...]`` gets set to for deepagents once anything is staged.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_DESCRIPTION = 1024


@dataclass(frozen=True)
class SkillsDelivery:
    sources: list[str]
    staged: list[str]
    errors: list[str]
    est_tokens: int


def _escape_yaml_double_quoted(text: str) -> str:
    collapsed = " ".join(text.split())
    return collapsed.replace("\\", "\\\\").replace('"', '\\"')


def stage_skills(
    sandbox,
    attached_skills: list[dict] | None,
    *,
    agent_id: str | None = None,
    prune_scope: list[str] | None = None,
) -> SkillsDelivery:
    """Write each attached skill as ``<sandbox>/skills/<id>/SKILL.md``.

    Never raises. Each call wipes ``<sandbox>/skills/`` before staging, so
    only THIS call's attached skills exist on disk afterward -- the sandbox
    is shared across a run's steps and staging is otherwise cumulative, so
    without the wipe a later step could read an earlier step's skills.

    ``prune_scope`` (ADR-0006 Consequences) widens the KEEP set without widening
    what gets STAGED. The prune below deletes every directory not attached to
    THIS step, which is correct while the step loop is serial but deletes a
    concurrent sibling's skill the moment two steps share the sandbox — see
    ``parallel_group``, where N siblings run under one ``asyncio.gather`` against
    the same ``RunSandbox`` (the shared_read isolation path, taken whenever the
    run grants no exec workspace). Passing the union of every concurrently-
    dispatched step's skill ids keeps each sibling's directory alive while still
    pruning genuinely stale ones. ``None`` ⇒ the KEEP set is this step's attached
    ids alone, i.e. the exact pre-existing behaviour for every serial step.
    """
    # Agent prefix for trace lines: "emoji-picker:" or "" when the caller did
    # not supply an id. No trailing space -- every use sits between two "%s"
    # gaps already, so a trailing space would double up.
    who = f"{agent_id}:" if agent_id else ""

    # Trace-only: what's already on disk in the staging dir BEFORE this call
    # stages anything — the clarifying parenthetical makes clear this is the
    # full on-disk listing, not the (usually smaller) attached/staged set.
    skills_dir = "skills"
    resolved_skills_dir = None
    on_disk: list[str] = []
    try:
        resolved_skills_dir = sandbox.path_for("skills")
        skills_dir = resolved_skills_dir
        if resolved_skills_dir.is_dir():
            on_disk = sorted(p.name for p in resolved_skills_dir.iterdir() if p.is_dir())
    except Exception:  # noqa: BLE001 - trace-only, must never raise
        resolved_skills_dir = None
        on_disk = []
    logger.debug(
        "skills_on_disk %s everything that EXISTS in %s: %s (not what's attached — see skills_staged below)",
        who,
        skills_dir,
        on_disk,
    )

    # ── Per-step skill scoping (spec 012 R-01, ADR-0006) ──────────────────
    # The skills/ dir is shared across a run and staging only ever wrote, so a step
    # could read a skill left behind by an earlier one. Prune the stale dirs rather
    # than wiping the tree, so re-attached skills keep their files.
    #
    # CONCURRENCY (ADR-0006): the prune set was this step's ids only, so two
    # concurrent steps deleted each other's skills. The KEEP set is now the
    # caller-supplied `prune_scope` — the union of every concurrently-dispatched
    # step's skill ids — falling back to this step's own ids when the caller
    # passes none (every serial step: same set, same behaviour as before).
    #
    # `or []` is load-bearing: this runs before the no-skills early return, so a
    # None caller reaches it and iterating None would break the never-raises contract.
    _attached_ids = {
        (payload.get("id") or payload.get("name"))
        for payload in (attached_skills or [])
    }
    _attached_ids.discard(None)
    # The KEEP set is a SUPERSET of the attached ids, never a replacement: a
    # scope that somehow omits an id this step is about to stage must not cause
    # that id to be pruned out from under it.
    _keep_ids = _attached_ids | {s for s in (prune_scope or []) if s}
    if resolved_skills_dir is not None and resolved_skills_dir.is_dir():
        try:
            stale = [
                d
                for d in resolved_skills_dir.iterdir()
                if d.is_dir() and d.name not in _keep_ids
            ]
            for d in stale:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:  # noqa: BLE001 - must never raise
            pass
        else:
            if stale:
                logger.info(
                    "skill staging %s pruned skills not attached to this step: %s",
                    who,
                    sorted(d.name for d in stale),
                )

    if not attached_skills:
        return SkillsDelivery([], [], [], 0)

    errors: list[str] = []
    try:
        from app.agents.skills_catalog import list_global_skills

        catalog = {entry.id: entry for entry in list_global_skills()}
    except Exception as exc:  # noqa: BLE001 - must never raise
        catalog = {}
        errors.append(f"skills catalog unavailable: {exc}")

    staged: list[str] = []
    for payload in attached_skills:
        skill_id = payload.get("id") or payload.get("name")
        name = payload.get("name") or skill_id
        content = payload.get("content") or ""

        if not skill_id:
            errors.append("skipped skill with no id or name")
            continue
        if not re.match(r'^[A-Za-z0-9._-]+$', skill_id) or skill_id in ('.', '..'):
            errors.append(f"{skill_id}: unsafe skill id")
            continue
        if not content.strip():
            errors.append(f"{skill_id}: skipped, empty content")
            continue

        catalog_entry = catalog.get(skill_id)
        description = catalog_entry.description if catalog_entry else f"{name} skill."
        if len(description) > _MAX_DESCRIPTION:
            description = description[:_MAX_DESCRIPTION]
            errors.append(f"{skill_id}: description clamped to {_MAX_DESCRIPTION} chars")

        description_yaml = _escape_yaml_double_quoted(description)
        escaped_id = _escape_yaml_double_quoted(skill_id)
        body = content.strip()
        file_text = f'---\nname: "{escaped_id}"\ndescription: "{description_yaml}"\n---\n\n{body}\n'

        try:
            target = sandbox.path_for(f"skills/{skill_id}/SKILL.md")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not (target.exists() and target.read_text() == file_text):
                target.write_text(file_text)
            staged.append(skill_id)
        except (OSError, ValueError) as exc:
            errors.append(f"{skill_id}: failed to stage ({exc})")
            continue

    sources = ["/skills"] if staged else []
    est_tokens = 464 + 66 * len(staged) if staged else 0

    for error in errors:
        logger.warning("skill staging: %s", error)
    logger.info("skill staging %s staged=%s est_tokens=%d", who, staged, est_tokens)
    if staged:
        # What the deepagents preamble will actually advertise to the model —
        # the most useful line for debugging why a skill was or wasn't chosen.
        advertised = [
            (skill_id, (catalog[skill_id].description if skill_id in catalog else f"{skill_id} skill.")[:80])
            for skill_id in staged
        ]
        logger.debug("skills_block %s model will see %s", who, advertised)

    audit_log = getattr(sandbox, "audit_log", None)
    if audit_log is not None:
        audit_data: dict[str, object] = {"catalog": on_disk, "staged": staged}
        if agent_id is not None:
            audit_data["agent"] = agent_id
        audit_log("skills_staged", audit_data)

    return SkillsDelivery(sources, staged, errors, est_tokens)
