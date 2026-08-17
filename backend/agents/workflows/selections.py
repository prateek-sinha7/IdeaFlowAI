"""agents/workflows/selections.py — synthesize a WorkflowManifest from a saved
compact per-step capability-selections map (EMP-01/02/03, Plan 22-04).

A *saved workflow* persists a COMPACT per-step selections map in the reused
``workflows.manifest_json`` column (D-11). The shape (the contract the FE composer
authors and BOTH the save endpoint AND the launch handler read) is::

    {
      "<agent_id>": {
        "validators": ["<name>", ...],   # optional — declared registered validators
        "gates":      ["<name>", ...],   # optional — declared gate capabilities
        "model":      "<model_id>",      # optional — a non-default per-step model
        "retry":      {"max_attempts": N, "backoff_seconds": F},  # optional
        ...                              # any future user-allowed lever key
      },
      ...
    }

``synthesize_manifest`` turns ``{base_pipeline_type, agent_ids, selections}`` into a
typed ``WorkflowManifest`` whose raw step dicts carry each agent's selected levers,
so the SAME thin no-DSL ``WorkflowCompiler.compile(..., trust="user")`` path
(``_check_trust``, compiler.py) re-validates the selections at BOTH save (the CAP-03
server backstop) AND launch (re-validate a possibly-tampered row — Pitfall 3). It is
the SINGLE synthesis seam (no duplicated synth logic between save and launch).

EMP-04 (D-07) coupling: when a step selects ≥1 ``validators`` the synthesized step
auto-attaches the ``validation`` gate (so the compiled step's validators actually
fire at run time — the validation gate is the registered seam that runs a step's
declared validators). The compiler's own §13 coupling backstop stays enforced.

Pure data (INV-5): this module synthesizes a manifest dataclass + raw step dicts ONLY
— no control flow, no kernel/web import. It depends only on
``agents.workflows.manifest`` (the typed shape) — the legal hexagonal direction.
"""

from __future__ import annotations

from agents.workflows.manifest import WorkflowManifest

# The selections-map lever keys this synth understands (every other key is carried
# verbatim onto the raw step dict so the compiler's strict-key rejection — INV-5 —
# names it, never this module). Kept aligned with compiler._ALLOWED_STEP_KEYS.
_LEVER_KEYS: frozenset[str] = frozenset(
    {"validators", "gates", "model", "retry", "injects", "compaction", "post_step",
     "fix", "fanout", "on_conflict", "tools", "hooks", "task_source", "depends_on",
     # ADR-0010 — per-agent skills, the composer's replacement for run-level
     # ``attached_skills``.
     "skills"}
)


def _coerce_retry(retry: object) -> dict | None:
    """Coerce a per-step ``retry`` selection into the compiler's mapping shape (CR-02).

    The FE emits ``retry`` as a bare value (a ``<select>`` ``e.target.value`` string,
    or a number once coerced FE-side). The compiler's ``_compile_retry_policy`` requires
    a ``{"max_attempts": N, ...}`` mapping. This bridges the two shapes at the SINGLE
    synth seam so save and launch behave identically:

      - an ``int``/``float`` (or a numeric ``str``) → ``{"max_attempts": int(n)}``;
        ``0`` (or a non-positive value) → ``None`` (no retry — omit the key).
      - a ``dict`` → passed through unchanged (the compiler validates/strict-key-checks
        it; an explicit ``{"max_attempts": 0}`` keeps the compiler's own semantics).
      - anything else → passed through unchanged so the compiler raises NAMING it
        (this module never silently drops an unknown shape — INV-5).
    """
    if isinstance(retry, bool):  # bool is an int subclass — never a retry count
        return retry  # type: ignore[return-value]  # let the compiler reject it
    if isinstance(retry, (int, float)):
        n = int(retry)
        return {"max_attempts": n} if n > 0 else None
    if isinstance(retry, str):
        try:
            n = int(retry.strip())
        except (ValueError, AttributeError):
            return retry  # type: ignore[return-value]  # non-numeric → compiler rejects
        return {"max_attempts": n} if n > 0 else None
    return retry  # type: ignore[return-value]  # dict (or other) → compiler handles


def _synthesize_step(agent_id: str, sel: dict | None) -> dict:
    """Build ONE raw step dict for ``agent_id`` from its selections (EMP-04 coupling).

    An absent / empty selections entry → a bare ``single_shot`` step (parity with a
    saved workflow that declared no levers). A selections entry projects each lever
    onto the raw step dict; selecting ≥1 validator auto-attaches the ``validation``
    gate (D-07) so the validators fire at run time.
    """
    step: dict = {"agent": agent_id, "strategy": "single_shot"}
    if not sel:
        return step

    if not isinstance(sel, dict):
        # Carry the bad value through as an unknown key so the compiler/manifest
        # validation (not this synth) raises NAMING the offending agent. Defensive:
        # the API schema validates the map shape before this is reached.
        step["__invalid_selection__"] = sel
        return step

    # D5/FANOUT-03: emit the user-selected strategy, overriding the single_shot
    # default (:86). Keyed GENERICALLY on the ``strategy`` lever — no workflow/
    # strategy/agent-name literal (INV-1/SC-001) — so a composed fan-out selection
    # becomes a fan-out step at the trust=user re-compile. An absent / empty /
    # non-string strategy keeps the safe single_shot default. ``fanout``/``task_source``
    # already ride the generic projection loop below (:128-131).
    if isinstance(sel.get("strategy"), str) and sel["strategy"]:
        step["strategy"] = sel["strategy"]

    validators = list(sel.get("validators") or [])
    gates = list(sel.get("gates") or [])

    # EMP-04 (D-07): a validator selection requires the validation gate to run it.
    if validators and "validation" not in gates:
        gates = [*gates, "validation"]

    if validators:
        step["validators"] = validators
    if gates:
        step["gates"] = gates

    # Project the remaining declared levers verbatim (pure data — the compiler
    # coerces/validates each; an unknown nested shape is the compiler's to reject).
    model = sel.get("model")
    if model is not None:
        # The compiler's _compile_model_policy reads a ``{model: <id>}`` mapping.
        step["model"] = {"model": model} if isinstance(model, str) else model

    retry = sel.get("retry")
    if retry is not None:
        # CR-02: the FE emits ``retry`` as a bare scalar (the ``<select>`` value),
        # but the compiler's ``_compile_retry_policy`` requires a mapping. Coerce a
        # numeric (or numeric-string) scalar into the canonical
        # ``{"max_attempts": N}`` shape; pass an explicit dict through unchanged.
        # 0 / empty → "no retry" (omit the key so the RESUME-02 wrapper stays
        # dormant — parity with a step that declared no retry).
        coerced = _coerce_retry(retry)
        if coerced is not None:
            step["retry"] = coerced

    # ADR-0010 — ``skills`` rides this generic projection so a composer-authored
    # per-agent skill selection reaches the run. It has to be here: run-level
    # ``attached_skills`` (the old delivery path for a composed run) is retired,
    # and a saved row's ``manifest_json`` is NEVER the run plan — the engine
    # compiles its own file-backed plan and overlays THIS selections map on top
    # (``engine._apply_selections``). Without ``skills`` in this list a user could
    # tick a skill in the composer, watch it persist, and have it silently never
    # reach the agent. ``skills`` is a plain list of catalog ids with no capability
    # reference, so it carries no trust=user gate.
    for key in ("injects", "compaction", "post_step", "fix", "fanout",
                "on_conflict", "tools", "hooks", "task_source", "depends_on",
                "skills"):
        if sel.get(key) is not None:
            step[key] = sel[key]

    return step


def synthesize_manifest(
    base_pipeline_type: str,
    agent_ids: list[str],
    selections: dict | None,
    *,
    deliverable: dict | None = None,
    limits: dict | None = None,
) -> WorkflowManifest:
    """Synthesize a ``WorkflowManifest`` from a saved composition + selections map.

    ``selections`` is the compact ``{agent_id: {levers}}`` map (or ``None`` = no
    selections). The result is compiled with ``trust="user"`` by BOTH the save
    endpoint and the launch handler so a smuggled / tampered ``user_allowed=False``
    capability is server-rejected (CAP-03) at both sites.

    The synthesized manifest is a self-contained compile target (id ==
    ``base_pipeline_type``, ``planner: run`` / ``clarify.mode: auto`` /
    ``deliverable: streamed_text`` defaults) — it is NOT the engine's run plan (the
    engine still compiles its own file-backed plan at run entry). Its sole purpose is
    to drive ``compile(trust="user")`` over the user-authored levers, so the trust
    gate is the authoritative server-side check.
    """
    sel_map = selections or {}
    # A workflow-level ``limits`` lever may live under the reserved ``__workflow__``
    # key of the selections map (or be passed explicitly). The compiler's
    # ``_compile_limits`` rejects a ceiling-raising cap under trust="user" (a user
    # may only LOWER a budget cap) — so this rides the same trust=user backstop.
    wf_limits = limits
    if wf_limits is None and isinstance(sel_map.get("__workflow__"), dict):
        wf_limits = sel_map["__workflow__"].get("limits")
    steps = [
        _synthesize_step(aid, sel_map.get(aid))
        for aid in agent_ids
    ]
    return WorkflowManifest(
        id=base_pipeline_type,
        steps=steps,
        # The deliverable is NOT a user-composed lever — it is a synth artifact that
        # only has to make compile() reach the per-step trust checks. Use a
        # user-allowed deliverable (``single_file``) so it never FALSE-rejects a
        # clean selections map; the real run deliverable comes from the engine's
        # own file-backed plan at run entry (this synthesized manifest never runs).
        # Option B (KAN-112): when the caller passes an explicit ``deliverable``
        # override (the user selected an output type in the custom composer via the
        # reserved ``__deliverable__`` key in selections), use it; otherwise fall back
        # to the safe compile-target default.  The synthesized manifest is ONLY used
        # by the trust=user re-compile — the engine's _apply_selections picks up the
        # override from the selections map directly (not from this manifest).
        deliverable=deliverable or {"strategy": "single_file", "name": "output.md"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        limits=wf_limits,
    )


def validate_selection_model_ids(selections: dict | None) -> str | None:
    """Reject any per-step ``model`` selection not in the ModelCatalog allow-list.

    CR-01 / WR-04 (the model-id allow-list bypass): a per-step ``model`` supplied via
    ``selections`` takes a DIFFERENT route than the ``model_overrides`` map
    (``_synthesize_step`` → ``_compile_model_policy``), which accepts any string id —
    so an unknown / disallowed / unintended-provider id would otherwise flow straight
    into ``build_model``. This walks the selections and enforces the SAME allow-list
    (``ModelCatalog().is_allowed`` — which also consults ``user_allowed``, IN-02) that
    ``_validate_model_overrides`` applies, so save and launch reject identically.

    Returns ``None`` when every selection model is allowed (or none is set), else a
    human-readable error string in the same shape the caller's other rejections use.
    Pure data: imports only the kernel-pure catalog (no app.* reach, INV legal direction).
    """
    if not selections:
        return None
    from agents.capabilities.model_catalog import ModelCatalog

    catalog = ModelCatalog()
    for agent_id, sel in selections.items():
        if not isinstance(sel, dict):
            continue  # malformed per-agent entry — the trust=user compile rejects it
        model = sel.get("model")
        if model is None:
            continue
        if not isinstance(model, str) or not catalog.is_allowed(model):
            return (
                f"selection for {agent_id!r} requests model {model!r}, "
                f"which is not an allowed model"
            )
    return None


def has_selections(selections: dict | None) -> bool:
    """True when ``selections`` carries at least one non-empty per-step lever entry.

    Used to keep the launch path byte-identical for saved workflows that declared no
    selections (``manifest_json IS NULL`` / ``{}`` → no overlay, no re-compile beyond
    the parity default).
    """
    if not selections:
        return False
    return any(bool(v) for v in selections.values())
