"""Server_Gate: the adapter that checks a Composer draft the way Save does (design 3.5.1).

:class:`ServerGate` implements :class:`~app.agents.workflow_builder.ports.GatePort`
for one turn. It is built with the caller's effective tier, the most trust the
tier may save at, the tier's Step_List and the label the save check puts in its
messages.

A check has three parts, in this order:

1. The Builder_Rules (:func:`builder_rules.check`) and the model entitlement
   gate (``_model_entitlement_error``). Both are pure or cheap, and a draft that
   breaks either is refused before the compiler runs.
2. The save check, ``_validated_manifest``, which is the function Save calls and
   which reaches ``_compile_check_manifest``. The engine import therefore stays
   where it already is (Req 48.5, 48.6). The callable is injected so a property
   test can stub it; production always passes ``_validated_manifest``.
3. The trust decision (G-13): the draft gets the least trust that works.

Every part is synchronous and CPU bound, so the whole check runs in
``asyncio.to_thread`` and never blocks the event loop.

Issue messages come from the rules, the entitlement gate and the compiler. They
name identifiers and never repeat prompt text (Req 23.10). Details that are not
text, or that run long, are cut before they reach the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Final, Protocol

from fastapi import HTTPException, status

from app.agents.workflow_builder import builder_rules, fact_checks, irreversible_gate
from app.agents.workflow_builder.fact_checks import IntakeFacts
from app.agents.workflow_builder.ports import GateIssue, GateResult
from app.api.run_engine import _model_entitlement_error
from app.api.user_workflows import _validated_manifest

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from agents.capabilities.model_catalog import ModelEntry
    from app.agents.workflow_builder.events import TargetTrust

__all__ = ["ManifestValidator", "ServerGate"]

logger = logging.getLogger(__name__)

_MAX_DETAIL_CHARS: Final = 1_000
_EMPTY_MANIFEST: Final = "The manifest is empty. It needs a non-empty 'steps' list."
_UNREADABLE_FILE: Final = "The manifest file could not be read."
_NOT_JSON: Final = "The manifest file is not valid JSON (line {line}, column {column})."
_NOT_OBJECT: Final = "The manifest file must hold one JSON object."
_DB_HINT: Final = (
    "This compiles at db trust. If a requirement needs it, call propose_draft "
    "again with target_trust='db' and say which requirement."
)
_DETAIL_NOT_TEXT: Final = "The workflow manifest was refused."


class ManifestValidator(Protocol):
    """The save check as the gate calls it (``_validated_manifest``)."""

    def __call__(
        self, manifest: dict[str, Any] | None, source_label: str, *, trust: str
    ) -> object:
        """Return normally when ``manifest`` passes at ``trust``.

        Raises:
            HTTPException: With status 422 when the manifest is refused.
        """
        ...


def _clip(text: str) -> str:
    return text if len(text) <= _MAX_DETAIL_CHARS else text[:_MAX_DETAIL_CHARS] + "..."


class ServerGate:
    """Checks a draft like Save does and decides the trust it is accepted at."""

    def __init__(
        self,
        *,
        tier: str,
        max_trust: TargetTrust,
        step_models: Sequence[ModelEntry],
        label: str,
        validate: ManifestValidator = _validated_manifest,
        check_irreversible: bool = False,
        intake_facts: Callable[[], IntakeFacts] | None = None,
    ) -> None:
        """Create the gate for one turn.

        Args:
            tier: The caller's effective tier (``effective_tier(user, principal)``).
            max_trust: The most trust the tier may save at, which is
                ``_saved_row_trust(tier)``. ``db`` is only ever used when this
                is ``db``.
            step_models: The tier's Step_List (``BuilderModelView.step``).
            label: The source label the save check puts in its messages.
            validate: The save check. Injected for tests; production uses
                ``_validated_manifest``.
            check_irreversible: Also refuse a draft with a step that posts or
                writes outside the run and has no gate directly before it
                (``irreversible_gate.check``). On only with the intake flag;
                ``False`` keeps the check exactly as before.
            intake_facts: Returns the settled intake brief's facts at check time
                (intake flag on). Each concrete identifier must appear in the
                draft (``fact_checks.check_facts``) and no prompt may insert a
                placeholder for a missing fact (``fact_checks.check_placeholders``).
                ``None`` skips both.
        """
        self._tier = tier
        self._max_trust: TargetTrust = max_trust
        self._step_models = tuple(step_models)
        self._label = label
        self._validate = validate
        self._check_irreversible = check_irreversible
        self._intake_facts = intake_facts

    async def check(
        self, manifest: dict[str, Any], *, requested_trust: TargetTrust
    ) -> GateResult:
        """Check ``manifest`` the way Save does, plus the Builder_Rules.

        Args:
            manifest: The parsed workflow manifest.
            requested_trust: The trust the agent asked for. The result is never
                above it and never above ``max_trust``.

        Returns:
            The verdict. ``trust`` is the least trust the draft compiles at.
        """
        return await asyncio.to_thread(self._check_sync, manifest, requested_trust)

    async def dry_run(
        self, manifest_path: Path, *, requested_trust: TargetTrust
    ) -> GateResult:
        """Read the file at ``manifest_path`` and run the same check.

        Stores nothing and sends no event. A file that cannot be read, is not
        JSON or is not an object gives a rejected result, not an exception.
        """
        return await asyncio.to_thread(
            self._dry_run_sync, manifest_path, requested_trust
        )

    def _dry_run_sync(
        self, manifest_path: Path, requested_trust: TargetTrust
    ) -> GateResult:
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return _rejected(GateIssue("save_check", "", _UNREADABLE_FILE))
        try:
            manifest = json.loads(text)
        except json.JSONDecodeError as exc:
            # Position only: the decoder's message can quote file content.
            message = _NOT_JSON.format(line=exc.lineno, column=exc.colno)
            return _rejected(GateIssue("save_check", "", message))
        if not isinstance(manifest, dict):
            return _rejected(GateIssue("save_check", "", _NOT_OBJECT))
        return self._check_sync(manifest, requested_trust)

    def _check_sync(
        self, manifest: dict[str, Any], requested_trust: TargetTrust
    ) -> GateResult:
        from agents.registry import allowed_custom_agent_ids

        if not manifest:
            return _rejected(GateIssue("save_check", "", _EMPTY_MANIFEST))
        issues = builder_rules.check(
            manifest,
            step_models=self._step_models,
            allowed_agent_ids=allowed_custom_agent_ids("custom"),
        )
        entitlement = _model_entitlement_error(self._tier, manifest=manifest)
        if entitlement is not None:
            issues.append(GateIssue("model_entitlement", "", _clip(entitlement[1])))
        if self._check_irreversible:
            issues.extend(irreversible_gate.check(manifest))
        if self._intake_facts is not None:
            facts = self._intake_facts()
            issues.extend(fact_checks.check_facts(manifest, facts.required))
            issues.extend(fact_checks.check_placeholders(manifest, facts.missing))
        if issues:
            return _rejected(*issues)
        return self._trust_check(manifest, requested_trust)

    def _trust_check(
        self, manifest: dict[str, Any], requested_trust: TargetTrust
    ) -> GateResult:
        """Accept at the least trust that works (G-13).

        ``user`` when the save check passes there, whatever was asked. ``db``
        only when ``user`` fails, ``db`` was asked for, the tier may save at
        ``db`` and the check passes there. Otherwise the draft is refused with
        the errors of the trust that was tried last, plus a hint when it would
        have compiled at ``db`` and the agent had not asked for it.
        """
        user_issues = self._save_check(manifest, "user")
        if not user_issues:
            return GateResult(True, "user", ())
        if self._max_trust != "db":
            return _rejected(*user_issues)
        db_issues = self._save_check(manifest, "db")
        if requested_trust == "db":
            if not db_issues:
                return GateResult(True, "db", ())
            return _rejected(*db_issues)
        if not db_issues:
            return _rejected(*user_issues, GateIssue("save_check", "", _DB_HINT))
        return _rejected(*user_issues)

    def _save_check(
        self, manifest: dict[str, Any], trust: TargetTrust
    ) -> list[GateIssue]:
        """Run the save check at ``trust``; a 422 becomes one ``save_check`` issue."""
        try:
            self._validate(manifest, self._label, trust=trust)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT:
                raise
            detail = exc.detail if isinstance(exc.detail, str) else _DETAIL_NOT_TEXT
            return [GateIssue("save_check", "", _clip(detail))]
        return []


def _rejected(*issues: GateIssue) -> GateResult:
    return GateResult(False, None, tuple(issues))
