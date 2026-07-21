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

        # ── DISK first (live truth — sticky semantics unchanged on healthy runs) ──
        # ctx.runner.sandbox is THIS run's own RunSandbox (keyed on run_id/user_id at
        # construction). No source_run_id / cross-owner accessor is consulted (T-30-06).
        runner = getattr(ctx, "runner", None)
        sandbox = getattr(runner, "sandbox", None)
        if sandbox is not None:
            entries = self._read_manifest(sandbox)
            if entries:
                # The disk manifest is the live copy — compose from it and NEVER
                # consult the durable mirror (disk wins when both exist).
                return self._compose(
                    entries, read_text=lambda name: self._read_sidecar(sandbox, name)
                )

        # ── DURABLE fallback (RESUME-13) — a wiped / fresh sandbox has no manifest ─
        # Fall back to the durable upload_text mirror via the owner+workspace-scoped
        # ctx.scoped_store (the P33 conversation-provider precedent: kernel-pure,
        # default-deny — a cross-owner run yields [] → {}). Byte-equivalent to the
        # disk path because it flows through the SAME self._compose.
        store = getattr(ctx, "scoped_store", None)
        run_id = getattr(ctx, "run_id", None)
        if store is None or not run_id:
            return {}

        rows = await self._read_upload_rows(store, run_id)
        # Location-keyed max-version selection (the 46-03 idiom): the per-(run,kind)
        # version counter is global, so pick the greatest-version row per location.
        latest = self._max_version_by_location(rows)
        manifest_row = latest.get(_MANIFEST_REL)
        if manifest_row is None:
            return {}
        entries = self._parse_entries(getattr(manifest_row, "content", None))
        return self._compose(
            entries,
            read_text=lambda name: getattr(
                latest.get(f"{_UPLOADS_PREFIX}{name}.txt"), "content", ""
            ) or "",
        )

    def _compose(self, entries: list, *, read_text) -> dict[str, str]:
        """Compose the ``uploaded_files_context`` block from ``entries`` — the ONLY
        place the block format lives, so the disk and durable paths are
        byte-identical by construction. ``read_text(name)`` supplies each doc's
        text (disk sidecar or durable row content)."""
        sections: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            if not entry.get("has_text"):
                continue
            text = (read_text(name) or "").strip()
            if not text:
                continue
            sections.append(f"### {name}\n{text}")
        if not sections:
            return {}
        return {"uploaded_files_context": "## Uploaded Files\n\n" + "\n\n".join(sections)}

    # ── durable reads (degrade-not-crash — a broken store read never breaks the agent) ──
    @staticmethod
    async def _read_upload_rows(store: Any, run_id: str) -> list:
        """Read this run's own durable ``upload_text`` rows via the scoped store;
        ``[]`` on any read error (owner+visibility default-deny — a cross-owner run
        yields ``[]`` by construction)."""
        try:
            rows = await store.list_refs(run_id, kind="upload_text")
        except Exception as exc:  # noqa: BLE001 — a read error must not break the agent
            logger.warning(
                "uploaded_files: durable list_refs failed (%s) — no context", exc
            )
            return []
        return list(rows or [])

    @staticmethod
    def _max_version_by_location(rows: list) -> dict:
        """Return ``{location: row}`` keeping the greatest-version row per location
        (list_refs orders by version ASC, so the last seen per location is its max)."""
        latest: dict = {}
        for row in rows or []:
            location = getattr(row, "location", None)
            if not isinstance(location, str) or not location:
                continue
            prev = latest.get(location)
            if prev is None or getattr(row, "version", 0) >= getattr(prev, "version", 0):
                latest[location] = row
        return latest

    @staticmethod
    def _parse_entries(raw: Any) -> list:
        """Parse a durable manifest row's ``content`` as a JSON list; ``[]`` on any miss
        (the durable sibling of the disk ``_read_manifest`` — kept separate, IN-02)."""
        if not raw:
            return []
        try:
            entries = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(
                "uploaded_files: durable manifest is not valid JSON — no context"
            )
            return []
        return entries if isinstance(entries, list) else []

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
