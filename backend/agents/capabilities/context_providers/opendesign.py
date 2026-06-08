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

        # (1) Design system block — the L12 "ACTIVE DESIGN SYSTEM" branch. The
        # engine includes it unless a deck explicitly marks it not required; for
        # the prototype pipeline is_design_system_required is None -> include.
        ds_body = od.get("ds_body")
        if ds_body:
            is_deck_conditional = od.get("is_design_system_required")
            include_ds = True if is_deck_conditional is None else bool(is_deck_conditional)
            if include_ds:
                blocks[f"ACTIVE DESIGN SYSTEM: {ds_id}"] = ds_body

        # (2) Template (SKILL.md) block — the L12 "ACTIVE TEMPLATE" branch.
        template_body = od.get("template_body")
        if template_body:
            blocks[f"ACTIVE TEMPLATE (SKILL.md): {template_id}"] = template_body

            # (3) Example.html block — only present when the template body is
            # injected (the engine nests the example inside the template branch).
            example_html = None
            if runner is not None and hasattr(runner, "template_example"):
                example_html = runner.template_example(template_id)
            if example_html:
                truncated = example_html[:8000]
                if len(example_html) > 8000:
                    truncated = truncated + "...[truncated]"
                blocks[f"TEMPLATE EXAMPLE (example.html): {template_id}"] = truncated

            # (4) Pre-injected template reference files (seed + layouts + checklist).
            if runner is not None and hasattr(runner, "template_injection_parts"):
                for i, part in enumerate(runner.template_injection_parts(template_id) or []):
                    blocks[f"TEMPLATE INJECTION PART {i}: {template_id}"] = part

        return blocks
