"""The builder's Server_Gate and ``POST /api/user-workflows`` agree on a manifest.

``ServerGate`` is built here with its production validator, the real
``_validated_manifest``, so nothing in the save check is stubbed: the compiler, the
capability registry and the trust wall all run. Two things are checked:

* the real save check, called directly at ``user`` and at ``db`` trust, accepts and
  refuses each manifest the way the compiler's rules say it should;
* for the trust a tier saves at (``_saved_row_trust``), the gate's verdict equals the
  verdict of ``POST /api/user-workflows`` for the same manifest, and a refusal
  carries the same message.

The router runs against the testcontainers PostgreSQL ``db_session``; the engine
compile needs no network and no model. Docker is not available on every developer
machine, so these tests run on the Docker-capable CI runner.

Requirements: 23.3, 48.5.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.workflow_builder.events import TargetTrust
from app.api.run_engine import _saved_row_trust
from app.api.user_workflows import _validated_manifest
from app.api.user_workflows import router as user_workflows_router
from app.api.workflow_builder.gate import ServerGate
from app.core.dependencies import get_current_principal, get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition
from tests.fakes.principal import principal_for

_LABEL_PREFIX = "workflow:"

# The tier that saves at each trust, and the base pipeline it may name on a save.
# ``custom`` (the Composer) is enterprise only, so ``pro`` saves at ``user`` trust.
_TIER_AT_TRUST: dict[TargetTrust, str] = {"user": "pro", "db": "enterprise"}
_BASE_PIPELINE = {"pro": "ppt", "enterprise": "custom"}


def _step(**extra: Any) -> dict[str, Any]:
    return {
        "agent": "custom-agent",
        "instance_id": "draft",
        "name": "Draft",
        "prompt": "Write the draft.",
        **extra,
    }


@dataclass(frozen=True)
class _Case:
    """A manifest and the trusts the real save check accepts it at."""

    manifest: dict[str, Any]
    passes_at_user: bool
    passes_at_db: bool

    def passes_at(self, trust: str) -> bool:
        return self.passes_at_user if trust == "user" else self.passes_at_db


_CASES: dict[str, _Case] = {
    "valid": _Case({"steps": [_step()]}, passes_at_user=True, passes_at_db=True),
    # A raised Limits cap is a trusted-source privilege: ``db`` compiles it, ``user`` does not.
    "raised_limit": _Case(
        {"steps": [_step()], "limits": {"max_subagents": 50}},
        passes_at_user=False,
        passes_at_db=True,
    ),
    "unknown_gate": _Case(
        {"steps": [_step(gates=["no-such-gate"])]},
        passes_at_user=False,
        passes_at_db=False,
    ),
    "path_in_instance_id": _Case(
        {"steps": [_step(instance_id="../escape")]},
        passes_at_user=False,
        passes_at_db=False,
    ),
    "no_steps": _Case({"steps": []}, passes_at_user=False, passes_at_db=False),
}
_CASE_PARAMS = [pytest.param(case, id=name) for name, case in _CASES.items()]


@pytest.fixture
def make_client(db_session: Session) -> Callable[[str], TestClient]:
    """Build a client for the saved-workflows router as a caller of the given tier.

    The caller is a real ``users`` row on PostgreSQL, and the principal carries the
    Cognito group a token for that tier would, so ``effective_tier`` and
    ``_saved_row_trust`` take their production paths.
    """

    def build(tier: str) -> TestClient:
        user = User(
            id=f"gate-{tier}",
            email=f"gate-{tier}@example.com",
            cognito_sub=f"sub-gate-{tier}",
            tier=tier,
        )
        db_session.add(user)
        db_session.commit()
        app = FastAPI()
        app.include_router(user_workflows_router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_principal] = lambda: (
            user,
            principal_for(user),
        )
        app.dependency_overrides[get_db] = lambda: db_session
        return TestClient(app)

    return build


def _gate(tier: str, name: str) -> ServerGate:
    """The gate for ``tier`` with the production validator (no ``validate=``)."""
    return ServerGate(
        tier=tier,
        max_trust=cast(TargetTrust, _saved_row_trust(tier)),
        step_models=(),
        label=f"{_LABEL_PREFIX}{name}",
    )


def _post(client: TestClient, tier: str, name: str, manifest: dict[str, Any]) -> Any:
    return client.post(
        "/api/user-workflows",
        json={
            "name": name,
            "base_pipeline_type": _BASE_PIPELINE[tier],
            "agent_ids": ["custom-agent"],
            "manifest": manifest,
        },
    )


def test_saved_row_trust_is_the_trust_the_tests_assume_when_tier_is_pro_or_enterprise() -> (
    None
):
    assert _saved_row_trust("pro") == "user"
    assert _saved_row_trust("enterprise") == "db"


# --- The real save check, directly --------------------------------------------------


@pytest.mark.parametrize("trust", ["user", "db"])
@pytest.mark.parametrize("case", _CASE_PARAMS)
def test_validated_manifest_follows_the_compiler_when_trust_is_user_or_db(
    case: _Case, trust: TargetTrust
) -> None:
    label = f"{_LABEL_PREFIX}direct"

    if case.passes_at(trust):
        assert _validated_manifest(case.manifest, label, trust=trust) == case.manifest
        return
    with pytest.raises(HTTPException) as refused:
        _validated_manifest(case.manifest, label, trust=trust)
    assert refused.value.status_code == 422
    assert label in str(refused.value.detail)


# --- Gate and POST give the same verdict ---------------------------------------------


@pytest.mark.parametrize("trust", ["user", "db"])
@pytest.mark.parametrize("case", _CASE_PARAMS)
async def test_check_matches_post_verdict_when_requested_trust_is_the_tier_trust(
    make_client: Callable[[str], TestClient],
    db_session: Session,
    case: _Case,
    trust: TargetTrust,
) -> None:
    tier = _TIER_AT_TRUST[trust]
    name = "same-verdict"
    client = make_client(tier)

    posted = _post(client, tier, name, case.manifest)
    verdict = await _gate(tier, name).check(case.manifest, requested_trust=trust)

    assert posted.status_code == (201 if case.passes_at(trust) else 422), posted.text
    assert verdict.accepted is (posted.status_code == 201)
    stored = db_session.query(WorkflowDefinition).filter_by(name=name).count()
    assert stored == (1 if verdict.accepted else 0)


_REFUSALS = [
    pytest.param(case, trust, id=f"{name}-{trust}")
    for name, case in _CASES.items()
    for trust in _TIER_AT_TRUST
    if not case.passes_at(trust)
]


@pytest.mark.parametrize(("case", "trust"), _REFUSALS)
async def test_check_reports_the_post_message_when_both_refuse(
    make_client: Callable[[str], TestClient], case: _Case, trust: TargetTrust
) -> None:
    tier = _TIER_AT_TRUST[trust]
    name = "same-message"
    client = make_client(tier)

    posted = _post(client, tier, name, case.manifest)
    verdict = await _gate(tier, name).check(case.manifest, requested_trust=trust)

    assert posted.status_code == 422
    assert verdict.accepted is False
    assert verdict.trust is None
    assert [(i.rule, i.message) for i in verdict.issues] == [
        ("save_check", posted.json()["detail"])
    ]


@pytest.mark.parametrize("tier", ["pro", "enterprise"])
async def test_check_accepts_at_user_when_a_manifest_compiles_at_user(
    tier: str,
) -> None:
    verdict = await _gate(tier, "least-privilege").check(
        _CASES["valid"].manifest, requested_trust="db"
    )

    assert (verdict.accepted, verdict.trust) == (True, "user")


async def test_check_accepts_at_db_when_only_db_compiles_and_the_tier_may_save_there(
    make_client: Callable[[str], TestClient],
) -> None:
    manifest = _CASES["raised_limit"].manifest
    client = make_client("enterprise")

    verdict = await _gate("enterprise", "db-only").check(manifest, requested_trust="db")

    assert (verdict.accepted, verdict.trust) == (True, "db")
    assert _post(client, "enterprise", "db-only", manifest).status_code == 201


async def test_check_refuses_with_a_hint_when_only_db_compiles_and_user_was_requested() -> (
    None
):
    """G-13: the gate never gives more trust than the agent asked for."""
    verdict = await _gate("enterprise", "no-hint").check(
        _CASES["raised_limit"].manifest, requested_trust="user"
    )

    assert verdict.accepted is False
    assert verdict.issues[-1].rule == "save_check"
    assert "target_trust='db'" in verdict.issues[-1].message


async def test_check_refuses_without_trying_db_when_the_tier_may_only_save_at_user(
    make_client: Callable[[str], TestClient],
) -> None:
    manifest = _CASES["raised_limit"].manifest
    client = make_client("pro")

    verdict = await _gate("pro", "pro-limit").check(manifest, requested_trust="db")

    assert verdict.accepted is False
    assert all("target_trust='db'" not in i.message for i in verdict.issues)
    assert _post(client, "pro", "pro-limit", manifest).status_code == 422
