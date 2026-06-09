"""agents/capabilities/context_providers/opendesign.py — the ``opendesign`` provider.

Composes the ``{block-name -> content}`` map the engine's L12 od / template /
example injection branches build today (engine.py:3306-3386) as a declared
``ContextProvider`` capability (PARITY-03). The block-name keys + ordering match
the engine verbatim so the generic injector (07-04) reproduces the same context
message:

  1. ``ACTIVE DESIGN SYSTEM: <ds_id>``        -> ds_body
  2. ``ACTIVE TEMPLATE (SKILL.md): <id>``      -> template_body
  3. ``TEMPLATE EXAMPLE (example.html): <id>`` -> example[:8000]
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
        task_num_str = getattr(ctx, "build_task_number", "") or ""
        is_builder = bool(spec_tools & {"prototype_emit_only", "prototype"})
        is_build_task_2_plus = task_num_str not in ("", "1")

        # (1) Design system block — the L12 "ACTIVE DESIGN SYSTEM" branch. The
        # engine includes it unless a deck explicitly marks it not required; for
        # the prototype pipeline is_design_system_required is None -> include.
        # CR-03: skip the DS body for builders on task 2+ (the skeleton already has
        # the DS tokens) — mirrors the legacy `... and not is_build_task_2_plus`.
        # CR-01: the block content is the instruction preamble + ds_body (byte-
        # identical to git fb55699), not the bare ds_body.
        ds_body = od.get("ds_body")
        if ds_body and not is_build_task_2_plus:
            is_deck_conditional = od.get("is_design_system_required")
            include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
            if include_ds:
                # NOTE: the preamble is kept on a SINGLE source line (byte-identical to
                # git fb55699 with spaces after each comma) so the exact-byte parity grep
                # matches the contiguous string; the runtime value is preamble + ds_body.
                ds_preamble = "Apply these tokens to ALL colors, fonts, and spacing. Map to :root variables: --bg, --fg, --accent, --surface, --border, --muted.\n"
                blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = f"{ds_preamble}{ds_body}"

        # (2) Template (SKILL.md) block — the L12 "ACTIVE TEMPLATE" branch.
        # CR-03: the template body + example are nested inside `not is_build_task_2_plus`
        # (the legacy branch skipped the full template body on build tasks 2+).
        template_body = od.get("template_body")
        if template_body:
            if not is_build_task_2_plus:
                blocks[f"ACTIVE TEMPLATE (SKILL.md): {template_id}"] = template_body

                # (3) Example.html block — only present when the template body is
                # injected AND the consuming agent is a BUILDER (CR-02). Planning
                # agents (prototype-specify / prototype-plan, tools=[]) must NOT see a
                # full working HTML doc — it nudges them to copy/continue it instead
                # of writing the spec / decomposing into tasks.
                example_html = None
                if (
                    is_builder
                    and runner is not None
                    and hasattr(runner, "template_example")
                ):
                    example_html = runner.template_example(template_id)
                if example_html:
                    truncated = example_html[:8000]
                    if len(example_html) > 8000:
                        truncated = truncated + "...[truncated]"
                    blocks[f"TEMPLATE EXAMPLE (example.html): {template_id}"] = truncated

            # (4) Pre-injected template reference files (seed + layouts + checklist) —
            # the L12 tool-gated injection-parts branch:
            #   * prototype_emit_only -> all parts on task 1; ONLY the seed part(s)
            #     (those containing "TEMPLATE SEED") on task 2+.
            #   * prototype           -> all parts always.
            #   * tools=[] (planning)  -> NO injection parts (the legacy branch had no
            #     else clause for tools:[]).
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
                    blocks[f"TEMPLATE INJECTION PART {i}: {template_id}"] = part

        return blocks
