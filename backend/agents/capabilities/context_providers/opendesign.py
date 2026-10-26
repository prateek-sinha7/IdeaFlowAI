"""agents/capabilities/context_providers/opendesign.py — the ``opendesign`` provider.

Composes the ``{block-name -> content}`` map the engine's L12 od / template /
example injection branches build today (engine.py:3306-3386) as a declared
``ContextProvider`` capability (PARITY-03). The block-name keys + ordering match
the engine verbatim so the generic injector (07-04) reproduces the same context
message:

  1. ``ACTIVE DESIGN SYSTEM: <ds_id>``        -> ds_body
  2. ``ACTIVE TEMPLATE (SKILL.md): <id>``      -> template_body
  3. ``TEMPLATE EXAMPLE (example.html): <id>`` -> example.html (capped in od_context.get_example_html)
  4. ``get_template_injection_parts`` blocks   -> seed + reference files

Heavy-dep boundary (Assumption A6 / import-linter): the ``od_loader`` disk reads
are NOT performed here — the capability layer must not import ``app.*`` nor the
kernel. Instead the provider composes its blocks FROM the pre-built ``od_context``
dict carried on ``ctx`` (built at the WS / NDJSON boundary by
``agents/execution_engine/od_context.py`` — the relocated loaders' new home) and
reaches the template seed/reference parts + example.html through the ``ctx.runner``
handle (``template_injection_parts`` / ``template_example``), which the kernel
backs with the relocated loaders in 07-04. The capability stays import-pure.
"""

from __future__ import annotations

from typing import Any

from agents.capabilities.registry import register

# Sentinel key-prefix marking a PRE-WRAPPED (raw) provider block (CR-04). The
# legacy L12 injection-parts already carry their own ``=== TEMPLATE SEED ... ===``
# envelope, so the engine appended them RAW (``parts.append(part)``) — it did NOT
# re-wrap them in a ``=== {block_name} ===`` outer envelope. The provider port is
# ``dict[str, str]``; to signal "append RAW, do not re-wrap" without changing the
# port shape we prefix the block-name key with this sentinel. The generic injector
# (engine._compose_context_message) strips the sentinel and appends the content
# verbatim. A non-prefixed key is wrapped as before (the legacy non-part blocks).
RAW_BLOCK_PREFIX = "\x00RAW\x00"


@register(
    "context_provider",
    "opendesign",
    description="Inject OpenDesign template / design-system / craft context into the agent prompt.",
    # CAP-03 / D-02: on the USER palette so a composed workflow can declare it
    # (the composer's Context-provider control). The least privileged of the five
    # registered context providers — it injects PUBLIC catalog content (templates,
    # design systems, craft rules) and nothing owner-scoped: unlike `repo` /
    # `previous_run` it has no `source_run_id` accessor and reaches no other
    # owner's data, and the template/design-system ids arrive on the REQUEST (not
    # the manifest), validated against the catalog at the launch boundary — an
    # unknown id raises LookupError → 400 before a run is minted, so a manifest
    # cannot name an arbitrary path through this capability.
    user_allowed=True,
)
class OpenDesignProvider:
    """Compose the od / template / example injection blocks (``name='opendesign'``).

    Satisfies the ``ContextProvider`` port (``name`` + ``async load``). Reaches the
    heavy ``od_loader`` reads only via the boundary ``od_context`` dict + the runner
    handle (Assumption A6) — no ``app.*`` / kernel import.
    """

    name = "opendesign"

    async def load(self, ctx: Any) -> dict[str, str]:
        od = getattr(ctx, "od_context", None) or {}
        if not od:
            return {}

        blocks: dict[str, str] = {}
        runner = getattr(ctx, "runner", None)

        template_id = od.get("template_id", "") or ""
        ds_id = od.get("ds_id", "custom") or "custom"

        # ── Builder/task gates (CR-02 / CR-03) — read the per-run state the engine
        # threads onto the ExecutionContext (D-03 per-run-state-on-ctx, the same
        # dynamic-attr mechanism as ectx.compiled_context_providers). These gate the
        # provider on the OPAQUE consuming-agent tool set + the build-loop task number
        # exactly as the legacy L12 injection branches did (git fb55699) — NEVER on a
        # workflow name/id (INV-1: the kernel stays name/id-free, the provider is the
        # legitimate home for the opaque-tool-based gate).
        spec_tools = set(getattr(ctx, "current_spec_tools", set()) or set())
        # CR-02 (07-09): the PER-INJECTS per-block gate the legacy L12 branch carried
        # (`if "design_system" in injects ...` / `if "template" in injects ...`). The
        # engine threads the consuming agent's DECLARED injects onto the ctx alongside
        # current_spec_tools (D-03). A block is emitted ONLY when its inject is declared.
        injects = set(getattr(ctx, "current_spec_injects", set()) or set())
        task_num_str = getattr(ctx, "build_task_number", "") or ""
        is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})
        is_build_task_2_plus = task_num_str not in ("", "1")

        # (1) Design system block — the L12 "ACTIVE DESIGN SYSTEM" branch.
        # CR-02: gated on `"design_system" in injects` (the restored per-block gate).
        # CR-03: skip the DS body for builders on task 2+ (the skeleton already has
        # the DS tokens) — mirrors the legacy `... and not is_build_task_2_plus`.
        # CR-01: the block content is the instruction preamble + ds_body (byte-
        # identical to git fb55699), not the bare ds_body.
        ds_body = od.get("ds_body")
        if "design_system" in injects and ds_body and not is_build_task_2_plus:
            is_deck_conditional = od.get("is_design_system_required")
            include_ds = (
                True if is_deck_conditional is None else bool(is_deck_conditional)
            )
            if include_ds:
                # NOTE: the preamble is kept on a SINGLE source line (byte-identical to
                # git fb55699 with spaces after each comma) so the exact-byte parity grep
                # matches the contiguous string; the runtime value is preamble + ds_body.
                ds_preamble = "Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = f"{ds_preamble}{ds_body}"

        # (2) Template (SKILL.md) block — the L12 "ACTIVE TEMPLATE" branch.
        # CR-02: gated on `"template" in injects` (the restored per-block gate; the
        # example + the injection parts share this same template-inject gate).
        # CR-03: the template body + example are nested inside `not is_build_task_2_plus`
        # (the legacy branch skipped the full template body on build tasks 2+).
        template_body = od.get("template_body")
        if "template" in injects and template_body:
            if not is_build_task_2_plus:
                blocks[f"ACTIVE TEMPLATE (SKILL.md): {template_id}"] = template_body

                # (3) Example.html block — only present when the template body is
                # injected AND the consuming agent is a BUILDER (CR-02 example gate —
                # 07-06; DO NOT re-open). Planning agents (prototype-specify /
                # prototype-plan, tools=[]) must NOT see a full working HTML doc — it
                # nudges them to copy/continue it instead of writing the spec /
                # decomposing into tasks.
                # EXTENDED (B-explicit): the composer (ppt-composer) opts into
                # example.html via the DECLARED ``template_example`` inject — NOT the
                # broad ``"workspace" in spec_tools`` proxy KAN-63 (b5f5885e) used. That
                # proxy also swept in the planner-shaped ppt-brief-analyst (it declares
                # tools=[workspace] but is an order-1 planning/strategy agent), re-leaking
                # example.html to a planner and violating the Phase-7 "planners must not
                # see a full working HTML doc" rule above. Keying on the explicit inject
                # lets the composer receive its "Clone example.html" visual reference while
                # the brief-analyst stays example-free. NOTE: ``template_example`` is
                # consumed ONLY by this gate — factory._compose_injection silently ignores
                # unknown inject values, so declaring it injects nothing on its own.
                example_html = None
                if (
                    (is_builder or "template_example" in injects)
                    and runner is not None
                    and hasattr(runner, "template_example")
                ):
                    example_html = runner.template_example(template_id)
                if example_html:
                    # INV-12 single-truncation: the example.html is already capped at the
                    # ONE authoritative point (od_context.get_example_html, EXAMPLE_MAX_CHARS
                    # = 120_000). Inject the runner-capped string DIRECTLY — no redundant
                    # second clip (which had silently re-truncated real deck templates to 8000).
                    blocks[f"TEMPLATE EXAMPLE (example.html): {template_id}"] = (
                        example_html
                    )

            # (4) Pre-injected template reference files (seed + layouts + checklist) —
            # the L12 tool-gated injection-parts branch:
            #   * prototype_emit_only -> all parts on task 1; ONLY the seed part(s)
            #     (those containing "TEMPLATE SEED") on task 2+.
            #   * prototype           -> all parts always.
            #   * tools=[] (planning)  -> NO injection parts (the legacy branch had no
            #     else clause for tools:[]).
            # CR-04 (07-09): the injection-part strings arrive PRE-WRAPPED (each carries
            # its own `=== TEMPLATE SEED ... ===` / `=== END ... ===` envelope), so the
            # legacy engine appended them RAW (`parts.append(part)`) — it did NOT nest
            # them inside a `=== TEMPLATE INJECTION PART N: ... ===` outer wrapper. We
            # mark each with the RAW_BLOCK_PREFIX sentinel so the engine injector appends
            # the content verbatim. The sentinel-prefixed key keeps each part a distinct
            # dict entry (the key is never emitted — only stripped by the injector).
            if runner is not None and hasattr(runner, "template_injection_parts"):
                all_parts = list(runner.template_injection_parts(template_id) or [])
                emitted_parts: list[str] = []
                if "prototype_emit_only" in spec_tools:
                    if is_build_task_2_plus:
                        emitted_parts = [p for p in all_parts if "TEMPLATE SEED" in p]
                    else:
                        emitted_parts = all_parts
                elif "prototype" in spec_tools:
                    emitted_parts = all_parts
                for i, part in enumerate(emitted_parts):
                    blocks[f"{RAW_BLOCK_PREFIX}injection-part-{i}"] = part

        # NOTE: the build-agent CURRENT PROTOTYPE skeleton block (WR-01) and the
        # UNCONDITIONAL TEMPLATE COMPLIANCE block (CR-01) are NOT emitted here — the
        # legacy engine positioned them AFTER the CURRENT TASK block (which the generic
        # injector composes from agnostic build scratch, downstream of the provider
        # blocks). They are emitted by ``_compose_context_message`` in its CURRENT-TASK
        # build region, gated on the same build signal (build_task_number + builder tool
        # set) — NOT a workflow name (INV-1). Keeping them in the engine preserves the
        # legacy byte ORDER (DS/template/example/parts → consumed → CURRENT TASK →
        # skeleton → TEMPLATE COMPLIANCE).

        # (5) Figma Design Reference block — Phase 4 (design-ingestor roadmap).
        # Emitted ONLY when source_type="figma" AND frames.json exists on the sandbox.
        # For ingestor runs, the Design Ingestor agent writes to context/design/
        # (no dot) because .context/ is write-protected for agents. Check both
        # locations: context/design/ first (ingestor writes), then .context/design/
        # (engine/catalog writes) as fallback. This makes Figma work equivalently
        # to catalog — the opendesign provider bridges the path difference.
        source_type = od.get("source_type")
        sandbox = getattr(runner, "sandbox", None) if runner else None
        _sandbox_reader = getattr(sandbox, "read", None) if sandbox else None

        def _read_design_file(relpath_no_dot: str, relpath_dot: str) -> str | None:
            """Read from no-dot (ingestor) path first, fall back to dot (engine) path."""
            if not callable(_sandbox_reader):
                return None
            if source_type in ("figma", "html"):
                val = _sandbox_reader(relpath_no_dot)
                if val:
                    return val
            return _sandbox_reader(relpath_dot)

        # Override ds_body and template_body with ingestor-written content
        # when the engine's od_context is empty (ingestor runs only).
        if source_type in ("figma", "html"):
            # For ingestor runs, the Design Ingestor writes SKILL.md and
            # design-system.md to context/design/ (no dot) because .context/
            # is write-protected for agents. ALWAYS read from disk here —
            # the od_context values are placeholders, not real content.
            real_ds = (
                _read_design_file(
                    "context/design/design-system.md",
                    ".context/design/design-system.md",
                )
                or ""
            )
            if real_ds:
                ds_body = real_ds
            real_skill = (
                _read_design_file(
                    "context/design/template/SKILL.md",
                    ".context/design/template/SKILL.md",
                )
                or ""
            )
            if real_skill:
                template_body = real_skill

            # Phase 7 (defensive): also read tokens.css and components.html
            # from the ingestor's no-dot path so agents that inject via
            # this provider can see the full token set. The sandbox rebuild
            # (od_context_sandbox.py) already handles ds_files for direct
            # sandbox reads; this surfaces them for opendesign-injected agents.
            _real_tokens = _read_design_file(
                "context/design/tokens.css",
                ".context/design/tokens.css",
            )
            _real_components = _read_design_file(
                "context/design/components.html",
                ".context/design/components.html",
            )
            # Append tokens.css to ds_body when present so it is part of the
            # ACTIVE DESIGN SYSTEM block (agents see: DESIGN.md + tokens.css).
            if _real_tokens and ds_body:
                ds_body = f"{ds_body}\n\n## Tokens (tokens.css)\n\n```css\n{_real_tokens.strip()}\n```"
            elif _real_tokens:
                ds_body = _real_tokens

            # Emit DS block with real content
            if ds_body and "design_system" in injects and not is_build_task_2_plus:
                is_deck_conditional = od.get("is_design_system_required")
                if is_deck_conditional is None or bool(is_deck_conditional):
                    ds_preamble = "Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                    blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = f"{ds_preamble}{ds_body}"
            # Emit SKILL.md block with real content
            if template_body and "template" in injects and not is_build_task_2_plus:
                blocks[f"ACTIVE TEMPLATE (SKILL.md): {template_id}"] = template_body

        if source_type == "figma":
            try:
                frames_raw = _read_design_file(
                    "context/design/template/figma/frames.json",
                    ".context/design/template/figma/frames.json",
                )
                if frames_raw:
                    blocks["FIGMA DESIGN REFERENCE"] = (
                        "The Figma screen exports for this run are listed below.\n"
                        "Read each frame PNG via read_file (vision) to see the exact\n"
                        "screens the user designed. Replicate their visual language.\n\n"
                        f"{frames_raw}"
                    )
            except Exception:  # noqa: BLE001 — degrade gracefully
                pass

        return blocks
