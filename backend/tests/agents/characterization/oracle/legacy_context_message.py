"""Engine-independent ORACLE of the pre-Phase-7 (acd1636) assembled ``context_message``.

GROUND TRUTH — captured verbatim from baseline ``acd1636``:
    * ``git show acd1636:backend/agents/execution_engine/engine.py`` lines 3243-3470
      (``ExecutionEngine._build_context_message`` — the od/template/example injection
      branch, the CURRENT TASK block, the CURRENT PROTOTYPE skeleton block, the CURRENT
      HTML block, and the unconditional TEMPLATE COMPLIANCE block).
    * ``git show acd1636:backend/agents/prototype/context.py`` lines 104-152
      (``get_template_injection_parts`` — the TEMPLATE SEED + TEMPLATE REFERENCE block
      formatting).

CAPTURE MECHANISM — PINNED-BYTES (not PINNED-OLD-ENGINE):
The legacy ``_build_context_message`` is a method that reaches ``self._load_template_example``,
``self._latest_typed_content``, ``self._filter_consumed_outputs`` and the live ``od_loader``
disk reads — running it at test time would re-couple the oracle to the engine (the very
thing this oracle must be independent of) and to template-folder contents that change. So we
instead PIN the legacy block strings verbatim (each with a ``# provenance: acd1636:...``
comment) and assemble them with the legacy ``"\n".join(parts)`` order against a SMALL,
deterministic ``od_context`` fixture (short bodies, so the assembled bytes are reviewable).
The assembly honors every acd1636 gate verbatim (see ``build_oracle_message``).

BASELINE RESOLUTION (must_haves.truths[3] / T-07-08-02):
This oracle pins to ``acd1636`` (the baseline the 07-REVIEW-DEEP.md deep review used). The
07-06 gap-closure reasoned against ``1d9234b^``. The two refs differ in unrelated areas, but
the load-bearing gate for the example.html injection — the ``_is_builder`` tool-set gate
(``set(spec.tools) & {"prototype_emit_only", "prototype"}``) — is PRESENT at BOTH refs. So the
choice of baseline does NOT affect the example gate this oracle encodes: planning agents
(``prototype-specify`` / ``prototype-plan``, ``tools=[]``) get NO example at either ref.

THE acd1636 GATES this oracle encodes (verbatim with the legacy source):
    * per-``injects`` gate: the DS block requires ``"design_system" in injects``; the
      template/example/injection-parts require ``"template" in injects``.
    * ``is_build_task_2_plus = (spec.id == "prototype-build" and task not in ("", "1"))``
      suppresses the DS body, the template body, the example, and the non-seed injection
      parts (task 2+ injects ONLY the TEMPLATE SEED part).
    * ``_is_builder`` example gate: example.html is injected ONLY when
      ``set(spec.tools) & {"prototype_emit_only", "prototype"}`` AND it is NOT a build task 2+.
    * RAW ``parts.append(part)`` for the injection parts (NOT re-wrapped) — the parts already
      carry their own ``=== TEMPLATE SEED ... ===`` / ``=== END TEMPLATE SEED ===`` envelope.
    * BARE ``=== END ACTIVE DESIGN SYSTEM ===`` / ``=== END ACTIVE TEMPLATE ===`` /
      ``=== END TEMPLATE EXAMPLE ===`` markers (NO ``: {id}`` suffix on the END marker).
    * the task-2+ skeleton wrapper ``=== CURRENT PROTOTYPE (skeleton — call
      read_file('prototype.html') for full content before editing) ===`` + its
      ``=== END CURRENT PROTOTYPE ===`` close, with the ``[Error:`` suppression.
    * the UNCONDITIONAL ``=== TEMPLATE COMPLIANCE ===`` block on EVERY ``prototype-build``
      task.

The four captured agent classes (must_haves.truths[2]):
    "prototype-specify"      injects=[template, design_system], tools=[],                    task=""
    "prototype-plan"         injects=[template, design_system], tools=[],                    task=""
    "prototype-build" task 1 injects=[template, design_system], tools=["prototype_emit_only"], task="1"
    "prototype-build" task 2 injects=[template, design_system], tools=["prototype_emit_only"], task="2"
"""

from __future__ import annotations

# ===========================================================================
# Deterministic repro fixture — small, short-body od_context + per-class inputs.
# Kept tiny so the assembled oracle bytes are human-reviewable in the test.
# ===========================================================================

# The repro od_context. Field shapes mirror the live ExecutionContext.od_context
# (agents/execution_engine/context.py:111-138) + the legacy load_prototype_context
# return dict (context.py@acd1636). Short bodies on purpose.
ORACLE_OD_CONTEXT: dict[str, str | None] = {
    "template_id": "web-prototype",
    "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
    "ds_id": "default",
    "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
    "is_design_system_required": None,  # prototype always requires DS (acd1636 loader)
}

# The fixed user brief (the cross-pipeline ORIGINAL USER REQUEST). For non-first agents
# the legacy code strips the chain context, but our fixture brief has none, so it is
# passed through verbatim for every agent class.
ORACLE_USER_MESSAGE = "Build me a thing for managing tasks."

# The fixed template injection-part bytes (what get_template_injection_parts returns
# for the fixture template). Reproduced verbatim from the legacy formatting; seed and
# ONE reference file, short bodies. These are RAW parts — they already carry their own
# block envelope and the legacy engine appended them un-rewrapped.
# provenance: acd1636:backend/agents/prototype/context.py:104-128 (get_template_injection_parts)
_ORACLE_TEMPLATE_SEED_BODY = "<!doctype html><html><body><!-- web-prototype seed --></body></html>"
_ORACLE_TEMPLATE_REF_NAME = "layouts"
_ORACLE_TEMPLATE_REF_BODY = "Use a 12-column grid. Cards snap to the grid gutters."

# provenance: acd1636:context.py:113-119 — TEMPLATE SEED part (assets/template.html)
_INJECTION_PART_SEED = (
    "=== TEMPLATE SEED (assets/template.html) ===\n"
    "This is the starter HTML for this template. Use it as your base.\n"
    f"{_ORACLE_TEMPLATE_SEED_BODY}\n"
    "=== END TEMPLATE SEED ==="
)
# provenance: acd1636:context.py:121-126 — TEMPLATE REFERENCE part (<ref>.md)
_INJECTION_PART_REFERENCE = (
    f"=== TEMPLATE REFERENCE ({_ORACLE_TEMPLATE_REF_NAME}.md) ===\n"
    f"{_ORACLE_TEMPLATE_REF_BODY}\n"
    "=== END REFERENCE ==="
)
# Legacy get_template_injection_parts order: seed first, then reference files.
_ALL_INJECTION_PARTS: list[str] = [_INJECTION_PART_SEED, _INJECTION_PART_REFERENCE]

# The example.html bytes (builder-only). Short, < 8000 chars so no truncation marker.
# provenance: acd1636:context.py:130-148 (get_example_html) + engine.py:3370-3376
_ORACLE_EXAMPLE_HTML = "<!doctype html><html><body><main>example dashboard</main></body></html>"

# The fixture's prior prototype HTML for build task 2 (drives the skeleton block). The
# legacy engine derived a compact skeleton via self._extract_html_skeleton; for the
# oracle we pin a short representative skeleton string (the exact skeleton algorithm is
# engine-internal — the oracle's job is to pin the WRAPPER bytes + the read_file
# instruction, the structural markers CR-* dropped, not to re-run the extractor).
# provenance: acd1636:engine.py:3437-3447 (skeleton wrapper) — wrapper bytes are exact.
_ORACLE_SKELETON = "<body><section data-page='dashboard'>…</section></body>"


# ===========================================================================
# Per-agent-class repro inputs.
# ===========================================================================

# Each agent class -> (injects, tools, task). The DS+template injects are declared on
# all four (the prototype AGENT.md files declare injects=[template, design_system]).
_CLASS_INPUTS: dict[str, dict] = {
    # provenance: prototype-specify AGENT.md — injects=[template, design_system], tools=[]
    "prototype-specify": {"injects": ["template", "design_system"], "tools": [], "task": ""},
    # provenance: prototype-plan AGENT.md — injects=[template, design_system], tools=[]
    "prototype-plan": {"injects": ["template", "design_system"], "tools": [], "task": ""},
    # provenance: prototype-build AGENT.md — injects=[template, design_system],
    #             tools=["prototype_emit_only"]
    "prototype-build:1": {
        "injects": ["template", "design_system"],
        "tools": ["prototype_emit_only"],
        "task": "1",
    },
    "prototype-build:2": {
        "injects": ["template", "design_system"],
        "tools": ["prototype_emit_only"],
        "task": "2",
    },
}

AGENT_CLASSES: tuple[str, ...] = ("prototype-specify", "prototype-plan", "prototype-build")


def _resolve_inputs(agent_class: str, task: str) -> dict:
    """Map (agent_class, task) -> the per-class repro inputs."""
    if agent_class == "prototype-build":
        key = "prototype-build:2" if task not in ("", "1") else "prototype-build:1"
        return _CLASS_INPUTS[key]
    if agent_class in _CLASS_INPUTS:
        return _CLASS_INPUTS[agent_class]
    raise ValueError(
        f"unknown agent_class {agent_class!r}; expected one of {AGENT_CLASSES!r}"
    )


def build_oracle_message(
    agent_class: str,
    *,
    task: str = "",
    od_context: "dict[str, str | None] | None" = None,
    user_message: str | None = None,
    injection_parts: "list[str] | None" = None,
    example_html: str | None = None,
    skeleton: str | None = None,
    task_body: str | None = None,
    task_total: str | None = None,
    planning_block: str | None = None,
    consumed_block: str | None = None,
) -> str:
    """Return the EXACT legacy (acd1636) assembled ``context_message`` for an agent class.

    Reconstructs ``ExecutionEngine._build_context_message`` (acd1636:engine.py:3243-3470)
    for the prototype agent classes, honoring every acd1636 gate verbatim (see the module
    docstring). NO live engine import — the GATE LOGIC is pinned from ``git show
    acd1636:...``; only the dynamic CONTENT (od_context bodies, injection-part bytes,
    example.html, the task-2+ skeleton) is parameterizable.

    By default the function assembles against the small deterministic fixtures
    (``ORACLE_OD_CONTEXT`` / ``_ALL_INJECTION_PARTS`` / ``_ORACLE_EXAMPLE_HTML`` /
    ``_ORACLE_SKELETON``) so the structural-marker tests read tiny reviewable bytes.
    The 07-09 byte-equality test against the live routed ``_compose_context_message``
    passes the SAME dynamic inputs the routed path saw (the harness od_context, the real
    ``get_template_injection_parts`` / ``get_example_html`` bytes, the routed skeleton) so
    the comparison is a true byte-equality of the legacy CONTRACT (gate logic + ordering +
    wrapper bytes) over identical content — not a comparison of two different fixtures.

    ``agent_class`` is one of ``AGENT_CLASSES``; ``task`` is the build-loop task number
    ("" for non-build agents, "1" / "2" for build tasks).
    """
    inputs = _resolve_inputs(agent_class, task)
    injects: list[str] = inputs["injects"]
    tools: list[str] = inputs["tools"]
    is_build = agent_class == "prototype-build"
    # acd1636:engine.py:3322 — is_build_task_2_plus gate.
    is_build_task_2_plus = is_build and task not in ("", "1")

    od = ORACLE_OD_CONTEXT if od_context is None else od_context
    all_parts = _ALL_INJECTION_PARTS if injection_parts is None else injection_parts
    the_example = _ORACLE_EXAMPLE_HTML if example_html is None else example_html
    the_skeleton = _ORACLE_SKELETON if skeleton is None else skeleton
    the_user_message = ORACLE_USER_MESSAGE if user_message is None else user_message
    parts: list[str] = []

    # provenance: acd1636:engine.py:3275 — ORIGINAL USER REQUEST block (first agent
    # gets the raw brief; the fixture brief carries no chain context to strip).
    parts.append(
        f"=== ORIGINAL USER REQUEST ===\n{the_user_message}\n=== END REQUEST ==="
    )

    # Planning-context block (workflow-AGNOSTIC, unchanged by Phase 7). The fixture
    # tests omit it (None) to keep the captured bytes focused on the OD/build structure;
    # the 07-09 byte-equality test against the live routed message passes the routed
    # planning block here so the assembled oracle includes it at the legacy position
    # (immediately after the USER REQUEST block, acd1636:engine.py:3290-3304).
    if planning_block:
        parts.append(planning_block)

    # provenance: acd1636:engine.py:3318-3398 — the od/template/example injection branch.
    # ── (1) ACTIVE DESIGN SYSTEM (per-injects gate + task-2+ suppression) ──────────
    # acd1636:engine.py:3337 — `if "design_system" in injects and od.get("ds_body")
    #                            and not is_build_task_2_plus:`
    if "design_system" in injects and od.get("ds_body") and not is_build_task_2_plus:
        ds_id = od.get("ds_id", "custom")
        is_deck_conditional = od.get("is_design_system_required")
        include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
        if include_ds:
            # provenance: acd1636:engine.py:3343-3349 — bare `=== END ACTIVE DESIGN SYSTEM ===`
            parts.append(
                f"=== ACTIVE DESIGN SYSTEM: {ds_id} ===\n"
                f"Apply these tokens to ALL colors, fonts, and spacing. "
                f"Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                f"{od['ds_body']}\n"
                f"=== END ACTIVE DESIGN SYSTEM ==="
            )

    # ── (2) ACTIVE TEMPLATE + example + injection parts (per-injects gate) ─────────
    # acd1636:engine.py:3351 — `if "template" in injects and od.get("template_body"):`
    if "template" in injects and od.get("template_body"):
        template_id = od.get("template_id", "")
        # acd1636:engine.py:3354 — template body + example skipped on build task 2+.
        if not is_build_task_2_plus:
            # provenance: acd1636:engine.py:3356-3360 — bare `=== END ACTIVE TEMPLATE ===`
            parts.append(
                f"=== ACTIVE TEMPLATE (SKILL.md): {template_id} ===\n"
                f"{od['template_body']}\n"
                f"=== END ACTIVE TEMPLATE ==="
            )
            # provenance: acd1636:engine.py:3367-3376 — the `_is_builder` example gate.
            # _is_builder = set(spec.tools) & {"prototype_emit_only", "prototype"}.
            # PRESENT at acd1636 AND 1d9234b^ — planning agents (tools=[]) get NO example.
            _is_builder = bool(set(tools) & {"prototype_emit_only", "prototype"})
            ex = the_example if _is_builder else None
            if ex:
                # provenance: acd1636:engine.py:3370-3376 — bare `=== END TEMPLATE EXAMPLE ===`
                parts.append(
                    f"=== TEMPLATE EXAMPLE (example.html): {template_id} ===\n"
                    f"{ex[:8000]}"
                    f"{'...[truncated]' if len(ex) > 8000 else ''}\n"
                    f"=== END TEMPLATE EXAMPLE ==="
                )

        # provenance: acd1636:engine.py:3382-3398 — the tool-gated injection-parts branch.
        # RAW parts.append(part) — the parts carry their own envelope, NOT re-wrapped.
        if "prototype_emit_only" in tools:
            if is_build_task_2_plus:
                # acd1636:engine.py:3388-3391 — task 2+ injects ONLY the seed part(s).
                seed_parts = [p for p in all_parts if "TEMPLATE SEED" in p]
                for part in seed_parts:
                    parts.append(part)
            else:
                for part in all_parts:
                    parts.append(part)
        elif "prototype" in tools:
            for part in all_parts:
                parts.append(part)
        # tools=[] (planning agents): NO injection parts (acd1636 had no else clause).

    # ── consumed upstream outputs (workflow-AGNOSTIC, unchanged by Phase 7) ───────
    # The fixture reconstruction has none (single-agent); the 07-09 byte-equality test
    # passes the routed consumed-output block here so the assembled oracle carries it at
    # the legacy position (after the injection parts, before the CURRENT TASK block —
    # acd1636:engine.py:3400-3406).
    if consumed_block:
        parts.append(consumed_block)

    # ── (3) build agent: CURRENT TASK + current HTML/skeleton + TEMPLATE COMPLIANCE ─
    # provenance: acd1636:engine.py:3408-3461 — `if spec.id == "prototype-build":`
    if is_build:
        task_num_str = task
        total_str = "2" if task_total is None else task_total  # fixture pipeline = 2 tasks
        if task_num_str:
            # provenance: acd1636:engine.py:3414-3422 — CURRENT TASK block. The body is
            # the planner's `## Task N:` block text (the routed path injects the real
            # task block); default to the legacy fallback wording when none supplied.
            body = (
                "Execute ONLY this task from the task list above."
                if task_body is None else task_body
            )
            parts.append(
                f"\n=== CURRENT TASK ===\n"
                f"Task {task_num_str} of {total_str}\n"
                f"{body}\n"
                f"=== END CURRENT TASK ==="
            )

        # provenance: acd1636:engine.py:3424-3450 — current HTML (task 1) vs skeleton (2+).
        # Task 1 has no prior HTML in the fixture -> no CURRENT HTML block. Task 2+ gets
        # the skeleton wrapper with the read_file instruction + the [Error: suppression.
        if is_build_task_2_plus:
            current_html = the_skeleton
            if current_html and not current_html.startswith("[Error:"):
                # provenance: acd1636:engine.py:3439-3445 — skeleton wrapper + read_file.
                parts.append(
                    f"\n=== CURRENT PROTOTYPE (skeleton — call read_file('prototype.html') "
                    f"for full content before editing) ===\n"
                    f"{current_html}\n"
                    f"=== END CURRENT PROTOTYPE ==="
                )

        # provenance: acd1636:engine.py:3452-3461 — UNCONDITIONAL TEMPLATE COMPLIANCE.
        ds_id = od.get("ds_id", "")
        template_id_val = od.get("template_id", "")
        parts.append(
            f"\n=== TEMPLATE COMPLIANCE ===\n"
            f"Template: {template_id_val} — use ONLY its CSS classes from the TEMPLATE SEED\n"
            f"Design System: {ds_id} — use ONLY :root variables, never raw hex colors\n"
            f"=== END TEMPLATE COMPLIANCE ==="
        )

    # provenance: acd1636:engine.py:3463 — return "\n".join(parts)
    return "\n".join(parts)
