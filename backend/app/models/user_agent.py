"""UserAgent SQLAlchemy model — a user-authored custom agent saved for reuse.

A ``custom-agent`` instance composed on the workflow canvas (spec 012) lives only
inside that one workflow's manifest: its ``display_name``, ``prompt`` and
``skills`` are per-step fields on ``Step`` (``agents/workflows/plan.py``), so the
moment the user builds a second workflow they have to type it all again. This
table is where they can keep one.

WHY A NEW TABLE rather than reusing ``workflows`` the way Phase 21 did for saved
workflows: a saved workflow IS a workflow — same manifest shape, same launch
path, so reuse was free. A saved agent is not a workflow and shares none of
those columns; folding it in would mean a second nullable-column cluster on
``workflows`` plus a discriminator, for rows that never take the workflow code
paths. The cost of a new table is one additive migration; the cost of the
overload is permanent ambiguity in every ``workflows`` query.

WHAT IS DELIBERATELY NOT HERE. ``AgentSpec`` (``agents/loader.py``) carries
fifteen-odd fields; almost none belong on a reusable, user-authored agent:

  * ``pipeline_type`` / ``order`` are WORKFLOW-STRUCTURE, not agent identity —
    a reusable agent has no fixed pipeline or position. Storing them would
    re-create the exact coupling that makes a filesystem agent usable in only
    one workflow (see specs/012-per-agent-skills-custom-agents/reports/
    agent-vs-workflow-config.md).
  * ``max_tokens`` is dead config — ``settings.MAX_OUTPUT_TOKENS`` always wins
    (``app/agents/model_factory.py``).
  * ``context_from`` is vestigial (``backend/CLAUDE.md``).
  * ``produces`` / ``consumes`` cannot describe N differently-purposed instances
    of one template, which is precisely why the ``custom-agent`` template
    declares neither.

That leaves what the canvas actually lets a user author: a name, a prompt, and
a set of skills. Adding a column later is additive and cheap; removing one that
turned out to be meaningless is not.

OWNERSHIP (INV-8, default-deny). Rows are owner-scoped and read through the
``_owned`` filter in ``app/api/user_agents.py`` — a cross-owner id returns 404,
never 403, so the endpoint does not confirm the existence of another user's
agent. ``owner_id``/``workspace_id`` are stamped alongside ``user_id`` per the
project's additive-migration rule (every new table carries both).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.models.database import Base


class UserAgent(Base):
    """A user-authored custom agent, reusable across workflows."""

    __tablename__ = "user_agents"
    __table_args__ = (
        # Backs the owner-scoped list query, which is the only hot read.
        Index("ix_user_agents_user", "user_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # AUTHZ-01 — carried on every new table. Stamped to the creating user; the
    # query filter keys on `user_id`, these exist so the row is scopeable the
    # same way every other owned row is.
    owner_id = Column(String, nullable=True)
    workspace_id = Column(String, nullable=True)

    # What the canvas actually lets a user author.
    name = Column(String, nullable=False)
    prompt = Column(Text, nullable=False)
    # list[str] of skill IDS — the same shape as `Step.skills` and
    # `manifest_json["steps"][i]["skills"]`, NOT the {id,name,content} payload
    # shape used by run-level `attached_skills`. Ids are resolved against the
    # catalog at compose time (`agents/factory.py::_resolve_step_skills`), so a
    # skill deleted from the catalog degrades to "not staged" rather than to a
    # stale inlined copy of its body.
    skills = Column(JSON, nullable=True)

    # Presentation only — never read by the execution path.
    icon = Column(String, nullable=True)
    description = Column(String, nullable=True)

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
