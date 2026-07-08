"""agents/capabilities/context_providers/uploaded_files.py — the ``uploaded_files`` provider (UPLD-03 / 30-02).

Surfaces the text extracted from a run's uploaded documents (staged under the
reserved ``.uploads/`` prefix by 30-01) as STICKY agent context: present in every
subsequent ``agent_input`` for a workflow whose agents declare
``injects:[uploaded_files]``. Satisfies the ``ContextProvider`` port (``name`` +
``async load(ctx) -> dict[str, str]``), mirroring ``repo.py`` / ``previous_run.py``.

This provider does NO extraction — 30-01 already extracted each document into a
``.uploads/<name>.txt`` sidecar and recorded a ``.uploads/manifest.json`` entry
(``{name, mime, has_text}``). This capability only READS that stable contract and
composes the sidecar text into one injected context block.

Self-gate (T-30-08): the block is surfaced ONLY when ``"uploaded_files"`` is in
``ctx.current_spec_injects`` — the per-agent DECLARED inject token the engine
threads onto the ExecutionContext inside the injects gate before the
context_provider loop (the SAME mechanism opendesign's per-block gate rides). The
gate keys on the DECLARED capability/inject NAME, NEVER on a workflow name /
spec.id / pipeline_type (INV-1).

Own-run only (T-30-06): disk is reached STRICTLY through the ``ctx.runner`` sandbox
handle — the current run's own ``RunSandbox`` (keyed on this run's ``run_id`` /
``user_id`` at construction by ``execute()``). There is NO ``source_run_id`` /
cross-owner path here (unlike ``repo.py`` / ``previous_run.py``), so no other
owner's uploads are reachable — the highest-risk information-disclosure boundary is
closed by construction.

Degrade-not-crash (mirrors ``repo.py``): a missing / empty / corrupt manifest or an
unreadable sidecar degrades to ``{}`` — a broken upload sidecar must never break the
agent. DORMANT on golden runs: no golden workflow declares ``uploaded_files`` and no
golden run stages a ``.uploads`` sidecar, so the self-gate returns ``{}`` with no
block and no mutation (INV-3 byte/event parity holds).

Import purity (import-linter, 4 kept / 0 broken): this module imports ONLY the
registry decorator + stdlib — NEVER ``app.*`` nor the execution kernel. The
``.uploads`` prefix is a local constant (the ``app.agents.sandbox._UPLOADS_PREFIX``
value, NOT imported — importing it would cross the capability→app boundary).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.capabilities.registry import register

logger = logging.getLogger(__name__)

# The reserved uploads prefix — the SAME literal ``app.agents.sandbox._UPLOADS_PREFIX``
# carries, replicated (not imported) to keep this module import-pure (import-linter:
# the capability layer must not import ``app.*``). 30-01 stages the manifest + each
# ``<name>.txt`` sidecar under this prefix.
_UPLOADS_PREFIX = ".uploads/"
_MANIFEST_REL = f"{_UPLOADS_PREFIX}manifest.json"


@register(
    "context_provider",
    "uploaded_files",
    description="Surface the run's uploaded document text as sticky agent context.",
)
class UploadedFilesProvider:
    """Surface the run's ``.uploads`` sidecar text to agents (``name='uploaded_files'``).

    Returns a ``dict[str, str]`` with a single ``uploaded_files_context`` block
    composing the extracted text of every uploaded document that carries a sidecar.
    Returns ``{}`` when un-gated, when nothing is uploaded, or on any read error.
    """

    name = "uploaded_files"

    async def load(self, ctx: Any) -> dict[str, str]:
        # ── Self-gate (T-30-08) — only an agent that DECLARES the inject sees it ──
        # Gate on the DECLARED inject token, never on spec.id / pipeline_type (INV-1).
        injects = set(getattr(ctx, "current_spec_injects", None) or set())
        if "uploaded_files" not in injects:
            return {}

        # ── Own-run sandbox handle (T-30-06) — the ONLY disk path ────────────────
        # ctx.runner.sandbox is THIS run's own RunSandbox (keyed on run_id/user_id at
        # construction). No source_run_id / cross-owner accessor is consulted.
        runner = getattr(ctx, "runner", None)
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is None:
            return {}

        entries = self._read_manifest(sandbox)
        if not entries:
            return {}

        sections: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            if not entry.get("has_text"):
                continue
            text = self._read_sidecar(sandbox, name)
            if not text:
                continue
            sections.append(f"### {name}\n{text}")

        if not sections:
            return {}

        body = "## Uploaded Files\n\n" + "\n\n".join(sections)
        return {"uploaded_files_context": body}

    # ── disk reads (degrade-not-crash — a broken sidecar never breaks the agent) ──
    @staticmethod
    def _read_manifest(sandbox: Any) -> list:
        """Read + parse ``.uploads/manifest.json`` as a list; ``[]`` on any miss."""
        try:
            raw = sandbox.read(_MANIFEST_REL)
        except Exception as exc:  # noqa: BLE001 — a read error must not break the agent
            logger.warning("uploaded_files: manifest read failed (%s) — no context", exc)
            return []
        if not raw:
            return []
        try:
            entries = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("uploaded_files: manifest is not valid JSON — no context")
            return []
        return entries if isinstance(entries, list) else []

    @staticmethod
    def _read_sidecar(sandbox: Any, name: str) -> str:
        """Read the ``<name>.txt`` sidecar; ``""`` on a miss / empty / read error."""
        try:
            text = sandbox.read(f"{_UPLOADS_PREFIX}{name}.txt")
        except Exception as exc:  # noqa: BLE001 — one bad sidecar must not break the rest
            logger.warning("uploaded_files: sidecar read failed for %s (%s)", name, exc)
            return ""
        return text.strip() if text and text.strip() else ""
