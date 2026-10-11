"""agents/workflows/permission_caps.py — the ONLY place a permission is decided.

Every permission question in the system is answered here:

  * what a class of manifest may ever request  → ``PERMISSION_CAP_INDEX``
  * what a step actually gets                  → ``apply_cap``
  * which tools that translates to             → ``denied_tools``
  * how a decision is reported                 → ``log_decision``

Nothing outside this module may decide, widen, narrow, or reinterpret a
permission. Consumers CONSUME:

    compiler.py   effective = apply_cap(step_grant, trust)   ← applies the cap
    factory.py    denied    = denied_tools(step.tools)       ← maps to tool names
    engine.py     (nothing — it only carries Step.tools to the factory)
    runner        excludes the names it was handed

If you find yourself writing ``if perms.write_files`` anywhere else, the logic
belongs in this file instead.

THE MODEL
---------
A step asks; the cap bounds; the result is what binds.

    step ``tools:``  ──intersect──▶  cap[trust]  ──▶  effective  ──▶  tool names

The intersection is a pure AND (``plan.intersect_permissions``), so a cap can
only ever narrow a request — never widen one. A step asking for ``exec: true``
under an untrusted cap resolves to False; that is not an error, it is the cap
doing its job.

WHAT IS CAPPED, AND WHY
-----------------------
``write_files`` is permitted under BOTH caps. Writes are confined to the run's
own sandbox by ``FilesystemBackend(virtual_mode=True)``, so a user-authored
workflow granting write cannot reach anything outside its run — and a Composer
workflow that cannot grant write cannot produce files at all. Permitted by the
cap is NOT granted: a step still has to ask, and ``ToolPermissions.write_files``
defaults False.

``exec``, ``spawn_subagents``, ``network`` and ``git`` escape the sandbox or
multiply cost, so they are trust-gated — engineer-authored manifests may request
them, user-authored ones cannot obtain them at all.

``spawn_subagents`` is worth stating precisely because its name misleads: it does
NOT give the model deepagents' native sub-agent dispatch (that ``task`` tool is
excluded unconditionally — the engine orchestrates sub-agents itself). It binds
``app.agents.tools.runner_tools.spawn_subagents``, a request EMITTER that returns
a JSON string; the ENGINE reads that tool-result event and performs the fan-out
through the single kernel spawn path. It is trust-gated because a user manifest
emitting fan-out requests multiplies run cost, not because the model can spawn.

``network`` is OFF under both caps — nothing binds it yet. ``git`` is OFF for
the untrusted cap and ON for the trusted cap (Task 4.1 / Requirement 42): the
engine's step-boundary commit fires through ``commit_all()`` directly — there is
no agent-callable git tool in the capability registry. The cap flag accurately
reflects the engine's git-enabled sandbox posture (``has_git=True`` default).
"""

from __future__ import annotations

import logging

from agents.workflows.plan import ToolPermissions, intersect_permissions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. The caps
# ---------------------------------------------------------------------------

#: Trust levels that count as engineer-authored. Anything else — ``user``
#: or an unrecognised value — is untrusted: an unknown trust level must
#: never resolve to the more permissive cap.
TRUSTED_TRUST_LEVELS: frozenset[str] = frozenset({"file", "builtin"})

#: Saved-workflow trust (Composer rows, saved step overrides — ADR-0054). Its own
#: cap: the budget half of trust (``spawn_subagents``) without anything that
#: reaches the host (exec / network / secrets / git).
SAVED_TRUST_LEVEL: str = "db"

#: THE CAP INDEX. Every ceiling in the system is one of these three rows.
PERMISSION_CAP_INDEX: dict[str, ToolPermissions] = {
    # Engineer-authored manifests: may request the privileged capabilities.
    "trusted": ToolPermissions(
        read_files=True,
        write_files=True,
        exec=True,
        spawn_subagents=True,
        network=False,
        git=True,  # Task 4.1 (Requirement 42): engine's own commit bypasses this cap
        # via commit_all() directly — no agent-callable git tool exists in
        # the capability registry. Flipped here in the same change as the
        # first declared git hook so the cap accurately reflects the engine's
        # new git-enabled sandbox posture (has_git=True global default).
        tool_sets=[
            "workspace",
            "prototype",
            "prototype_emit_only",
            "planning",
            "internet",
            "pptx",
            "playwright",
            "file_extract",
            "spawn_subagents",
            "ask_user",
        ],
    ),
    # User-authored (Composer) manifests: sandbox-confined work only.
    # ``tool_sets`` is the allow-list for the Composer's per-step tool-pack
    # toggles: only sets that write inside the run sandbox belong here. This
    # list — not the registry's ``user_allowed`` flag — is what binds for a
    # grant-declared set (``playwright`` is user_allowed=False on the palette
    # but deliberately grantable per-step here: it drives a browser against
    # the run's own artifacts).
    "untrusted": ToolPermissions(
        read_files=True,
        write_files=True,
        exec=False,
        spawn_subagents=False,
        network=False,
        git=False,
        tool_sets=["file_extract", "playwright"],
    ),
    # Saved (db-trust) manifests — ADR-0054. The untrusted cap plus exactly what
    # a Composer copy of a built-in needs: ``spawn_subagents`` (fan-out request
    # emitter; the engine performs the spawn, bounded by the saved Limits
    # ceiling) and the sandbox-confined tool sets built-in manifests grant
    # (``prototype_emit_only`` = store-free report_task_complete; ``ask_user`` =
    # the HITL question). No exec / network / secrets / git: those reach the host.
    "saved": ToolPermissions(
        read_files=True,
        write_files=True,
        exec=False,
        spawn_subagents=True,
        network=False,
        git=False,
        tool_sets=["file_extract", "playwright", "prototype_emit_only", "ask_user"],
    ),
}

# ---------------------------------------------------------------------------
# 2. Permission → the tools it gates
# ---------------------------------------------------------------------------

#: THE MAPPING TABLE. A permission that is OFF denies exactly these tool names.
#: A tool absent from every row is gated by no permission.
#:
#: ``spawn_subagents`` is absent deliberately: it binds a custom tool through the
#: tool-provider registry rather than gating a native one, and deepagents' own
#: ``task`` tool is excluded unconditionally by the runner.
PERMISSION_TOOLS: dict[str, frozenset[str]] = {
    "read_files": frozenset({"read_file", "ls", "glob", "grep"}),
    "write_files": frozenset({"write_file", "edit_file"}),
    "exec": frozenset({"execute"}),
}

#: Every native tool a permission can gate.
GATED_TOOLS: frozenset[str] = frozenset().union(*PERMISSION_TOOLS.values())

# ---------------------------------------------------------------------------
# 2b. The permission vocabulary — what a manifest may name
# ---------------------------------------------------------------------------

#: The grant keys a manifest step's ``tools:`` block may declare. DERIVED from
#: ``ToolPermissions`` rather than hand-listed, so adding a permission there
#: cannot leave a stale copy behind that silently rejects the new key.
GRANT_BOOL_FIELDS: tuple[str, ...] = ToolPermissions._BOOL_FIELDS
GRANT_LIST_FIELDS: tuple[str, ...] = ToolPermissions._LIST_FIELDS
ALLOWED_GRANT_KEYS: frozenset[str] = frozenset(GRANT_BOOL_FIELDS) | frozenset(
    GRANT_LIST_FIELDS
)


def parse_grant(raw: dict) -> ToolPermissions:
    """Build a step's REQUESTED permissions from a manifest ``tools:`` mapping.

    Pure data → typed request. Unknown keys are the CALLER's error to raise (the
    compiler owns manifest diagnostics); this only reads the keys it knows.
    Absent keys keep the ``ToolPermissions`` defaults, so a partial block such as
    ``{write_files: true}`` still gets the default ``read_files: True``.
    """
    kwargs: dict = {}
    for field_name in GRANT_BOOL_FIELDS:
        if field_name in raw:
            kwargs[field_name] = bool(raw[field_name])
    for field_name in GRANT_LIST_FIELDS:
        if field_name in raw:
            kwargs[field_name] = list(raw[field_name] or [])
    return ToolPermissions(**kwargs)


# ---------------------------------------------------------------------------
# 3. The decisions
# ---------------------------------------------------------------------------


def cap_key_for_trust(trust: str | None) -> str:
    """Map a manifest trust level to its cap key. Unknown ⇒ ``untrusted``."""
    if (trust or "") in TRUSTED_TRUST_LEVELS:
        return "trusted"
    if trust == SAVED_TRUST_LEVEL:
        return "saved"
    return "untrusted"


def cap_for_trust(trust: str | None) -> ToolPermissions:
    """The cap bounding a manifest at this trust level. Fails closed."""
    return PERMISSION_CAP_INDEX[cap_key_for_trust(trust)]


def apply_cap(
    step_grant: ToolPermissions,
    trust: str | None,
    *,
    workflow: str = "",
    agent: str = "",
) -> ToolPermissions:
    """Resolve a step's EFFECTIVE permissions: what it asked for, bounded by the cap.

    This is the whole compile-time decision. ``compiler.py`` calls this and stores
    the result on ``Step.tools``; it does not construct a ceiling or perform an
    intersection itself.
    """
    cap = cap_for_trust(trust)
    effective = intersect_permissions(cap, cap, step_grant)
    log_decision(
        "cap",
        workflow,
        agent,
        describe(step_grant),
        describe(effective),
        detail=f"cap={cap_key_for_trust(trust)} trust={trust or '?'}",
    )
    return effective


def denied_tools(perms: ToolPermissions | None) -> frozenset[str]:
    """Native tool names a permission set does NOT grant.

    ``None`` means no compiled step is bound for this invocation — a revision
    agent, a fix agent, a direct ``create_runner`` call in a test. Those paths
    narrow nothing, so code that never opted into the permission system keeps
    behaving exactly as it did before it existed.
    """
    if perms is None:
        return frozenset()
    denied: set[str] = set()
    for permission, tools in PERMISSION_TOOLS.items():
        if not getattr(perms, permission, False):
            denied |= tools
    return frozenset(denied)


def granted_tools(perms: ToolPermissions | None) -> frozenset[str]:
    """The complement of :func:`denied_tools` — what the step may actually use."""
    if perms is None:
        return GATED_TOOLS
    return GATED_TOOLS - denied_tools(perms)


# ---------------------------------------------------------------------------
# 4. Reporting
# ---------------------------------------------------------------------------


def describe(perms: ToolPermissions | None) -> str:
    """One-line rendering of a permission set — what is ON, not every flag.

    ``-`` when nothing is granted; ``unrestricted(no-step)`` when no step is bound
    (which is a materially different situation from "granted nothing" and must not
    read the same in a log).
    """
    if perms is None:
        return "unrestricted(no-step)"
    on = [f for f in ToolPermissions._BOOL_FIELDS if getattr(perms, f, False)]
    return ",".join(on) if on else "-"


def log_decision(
    seam: str,
    workflow: str,
    agent: str,
    requested: str,
    granted: str,
    *,
    detail: str = "",
) -> None:
    """Emit a permission decision in the one shared format.

    Every seam logs through here so the format is defined once:

        tool_permission: <seam> : <workflow> : <agent> : requested=… : granted=… [detail]

    ``seam`` names the call site ("cap" for the compile-time ceiling,
    "resolve" for the bind-time resolution) so the two decisions are
    distinguishable in a trace — they were previously indistinguishable
    because the parameter was accepted and then dropped on the floor.

    ``granted`` always states what IS permitted rather than what was excluded —
    an exclusion set is a double negative and has been misread before (ISS-004).
    """
    logger.info(
        "tool_permission: %s : %s : %s : requested=%s : granted=%s%s",
        seam or "?",
        workflow or "?",
        agent or "?",
        requested,
        granted,
        f" ({detail})" if detail else "",
    )
