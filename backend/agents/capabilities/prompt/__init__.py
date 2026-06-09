"""agents/capabilities/prompt/ — the PromptAssemblyPolicy capability package (08-05 / F1 / §30).

Importing this package imports ``policy``, firing its
``@register("prompt", "default")`` decorator so ``discover()`` (which best-effort
imports this package) binds the default prompt-assembly policy into the registry.

F1 lift (D-08 / INV-12): the factory's hardcoded inline block-append order
(``injects → guardrails → skills → hooks → constitution → prompt_body``, joined with
``"\\n\\n"``) becomes a declared, registry-resolved ``PromptAssemblyPolicy``. The default
policy reproduces that order + join BYTE-IDENTICALLY (the 5 characterization snapshots
gate it — NEVER re-baseline). F4 (the constitution block) plugs into this policy's
``constitution`` slot in 08-06; this plan leaves the slot wired to the factory's existing
``_inject_constitution`` output.

Import purity (import-linter): imports ONLY the registry decorator + stdlib typing —
NO ``app.*`` import, NO kernel-engine import.
"""

from __future__ import annotations

from agents.capabilities.prompt import policy  # noqa: F401 — import side effect: @register

__all__ = ["policy"]
