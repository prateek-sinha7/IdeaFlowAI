"""Unit tests for ``app.api.runs`` (run-history CRUD / audit / share / restore router).

Isolation notes
---------------
* The router is mounted on a minimal ``FastAPI()`` app (no lifespan, no other routers).
  ``get_current_user`` and ``get_db`` are the only ``Depends`` and are overridden per test;
  the ``_clear_overrides`` autouse fixture empties ``dependency_overrides`` in teardown.
* No engine / session is ever created. ``_db`` builds a ``MagicMock(spec=Session)`` whose
  ``query`` returns pre-built ``_Q`` fakes in call order (an exhausted list fails loudly).
  ``_Q`` records the SQL criteria so the ownership (IDOR) filter can be asserted
  structurally via ``_Q.sql()``.
* ``ScopedStore``, ``RunSandbox``, ``family_lock``, ``commit_in_sandbox``, the PPTX generator,
  ``secrets.token_urlsafe`` and ``datetime`` are patched where the module LOOKS THEM UP.
* Each test carries ``# Plan #<row> | B<ids> | <mutation that must make it fail>``; the
  rows feed the artifacts under ``unit-test-prompt/test-files/app__api__runs/``.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.api.runs as runs_mod
from agents.execution_engine.engine import CommitInSandboxResult
from app.agents.runtime.local import GitCommandError
from app.agents.sandbox import FamilyLockTimeout, RunSandbox
from app.api.runs import (
    FamilyMemberResponse,
    RevisionRootResolved,
    RevisionRootUnresolved,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    _assert_share_output_clean,
    _build_chain_projection,
    _build_finalization_projection,
    _build_lineage_tree,
    _compute_root_ids,
    _extract_chain_context,
    _has_active_family_member,
    _iso_utc,
    _owned_family_members,
    _owner_gate_or_404,
    _run_list_response,
    _run_response,
    _validate_tag_for_restore,
    get_shared_run_by_token,
)
from app.core.dependencies import get_current_user
from app.models.artifact_ref import ArtifactRef
from app.models.database import get_db
from app.models.exec_runs import ExecRun
from app.models.gate_events import GateEvent
from app.models.hook_runs import HookRun
from app.models.run_capabilities import RunCapabilities
from app.models.run_event import RunEvent
from app.models.subagent_run import SubagentRun
from app.models.validation_results import ValidationResult
from app.models.wave_run import WaveRun
from app.models.workflow import WorkflowRun
from app.models.workflow_clarification import WorkflowClarification

USER = SimpleNamespace(id="user-1")
T0 = datetime(2026, 1, 2, 3, 4, 5)  # naive on purpose (KAN-113)
T0_ISO = "2026-01-02T03:04:05+00:00"
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PPTX_CT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
NOT_FOUND = "Workflow run not found"


# --------------------------------------------------------------------------- helpers
class _Q:
    """Chainable fake for a SQLAlchemy ``Query`` that records what the code asked for."""

    def __init__(self, first=None, rows=(), count=0):
        self._first = first
        self._rows = list(rows)
        self._count = count
        self.criteria: list = []
        self.order: list = []
        self.offset_v = None
        self.limit_v = None
        self.deleted = False
        self.delete_kwargs = None
        self.update_args = None

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *order):
        self.order.extend(order)
        return self

    def offset(self, n):
        self.offset_v = n
        return self

    def limit(self, n):
        self.limit_v = n
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)

    def count(self):
        return self._count

    def delete(self, **kwargs):
        self.deleted = True
        self.delete_kwargs = kwargs
        return 0

    def update(self, values, **kwargs):
        self.update_args = (values, kwargs)
        return 0

    def sql(self) -> list[str]:
        return [
            str(c.compile(compile_kwargs={"literal_binds": True}))
            for c in self.criteria
        ]


def _db(*items) -> MagicMock:
    """Session double: the Nth ``query()`` call returns the Nth item (exceptions are raised)."""
    db = MagicMock(spec=Session)
    db.query.side_effect = list(items)
    return db


def _row(**over) -> SimpleNamespace:
    base = dict(
        id="run-1", title="T", type="custom", status="completed", input="in",
        output="out", agent_outputs=None, agent_count=2, duration=1.5, error=None,
        token_usage=None, model_id="m1", deliverable_mimetype=None,
        deliverable_filename=None, parent_run_id=None, source_run_id=None,
        diverted_at_step_id=None, created_at=T0, completed_at=None,
        payload_chainable=None, non_chainable_reason=None, workspace_id="ws-1",
        user_id="user-1", git_tag=None, share_token=None, share_expires_at=None,
    )  # fmt: skip
    base.update(over)
    return SimpleNamespace(**base)


def _fixed_datetime(now: datetime) -> MagicMock:
    fake = MagicMock(spec=datetime)
    fake.now.return_value = now
    return fake


_APPS: list[FastAPI] = []


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    for app in _APPS:
        app.dependency_overrides.clear()
    _APPS.clear()


@pytest.fixture
def make_client():
    def _make(db) -> TestClient:
        app = FastAPI()
        app.include_router(runs_mod.router)
        app.dependency_overrides[get_current_user] = lambda: USER
        app.dependency_overrides[get_db] = lambda: db
        _APPS.append(app)
        return TestClient(app)

    return _make


# =========================================================================== serializers
class TestSerializeDt:
    @pytest.mark.parametrize(
        ("model_cls", "extra"),
        [
            pytest.param(
                WorkflowRunResponse,
                dict(
                    id="a",
                    title="t",
                    type="x",
                    status="s",
                    input="i",
                    agent_count=1,
                    root_run_id="a",
                ),
                id="run-response",
            ),
            pytest.param(
                WorkflowRunListResponse,
                dict(
                    id="a",
                    title="t",
                    type="x",
                    status="s",
                    agent_count=1,
                    root_run_id="a",
                ),
                id="list-response",
            ),
            pytest.param(
                FamilyMemberResponse,
                dict(id="a", title="t", type="x", status="s", revision_index=1),
                id="family-member",
            ),
        ],
    )
    @pytest.mark.parametrize(
        ("created", "completed", "exp_created", "exp_completed"),
        [
            pytest.param(T0, None, T0_ISO, None, id="naive-promoted-and-none"),
            pytest.param(
                datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2))),
                T0, "2026-01-02T03:04:05+02:00", T0_ISO, id="aware-kept-naive-promoted",
            ),
        ],
    )  # fmt: skip
    # Plan #1 | B1,B2 | kills: drop the naive->UTC promotion or the None guard
    def test_serialize_dt_promotes_naive_to_utc_when_dumping(
        self, model_cls, extra, created, completed, exp_created, exp_completed
    ):
        # Arrange
        model = model_cls(created_at=created, completed_at=completed, **extra)
        # Act
        dumped = model.model_dump()
        # Assert
        assert dumped["created_at"] == exp_created
        assert dumped["completed_at"] == exp_completed


class TestIsoUtc:
    # Plan #2 | B3 | kills: return "" instead of None for None
    def test_iso_utc_returns_none_when_value_is_none(self):
        assert _iso_utc(None) is None

    # Plan #3 | B4 | kills: skip replace(tzinfo=utc) for naive values
    def test_iso_utc_appends_utc_offset_when_value_is_naive(self):
        assert _iso_utc(T0) == T0_ISO

    # Plan #4 | B4 | kills: always force UTC even for aware values
    def test_iso_utc_keeps_offset_when_value_is_aware(self):
        aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-5)))
        assert _iso_utc(aware) == "2026-01-02T03:04:05-05:00"


# =========================================================================== _compute_root_ids
class TestComputeRootIds:
    # Plan #5 | B5 | kills: query even when the page is empty
    def test_compute_root_ids_returns_empty_dict_when_no_runs(self):
        db = _db()
        assert _compute_root_ids(db, "user-1", []) == {}
        db.query.assert_not_called()

    # Plan #6 | B5 | kills: run an ancestor query for NULL-parent pages
    def test_compute_root_ids_maps_each_run_to_itself_when_parents_are_null(self):
        db = _db()
        runs = [
            SimpleNamespace(id="a", parent_run_id=None),
            SimpleNamespace(id="b", parent_run_id=None),
        ]
        assert _compute_root_ids(db, "user-1", runs) == {"a": "a", "b": "b"}
        db.query.assert_not_called()

    # Plan #7 | B6,B9 | kills: fail to step into an owned parent / drop owner filter
    def test_compute_root_ids_returns_owned_parent_when_parent_is_owned_root(self):
        q = _Q(rows=[("p", None)])
        db = _db(q)
        runs = [SimpleNamespace(id="c", parent_run_id="p")]
        assert _compute_root_ids(db, "user-1", runs) == {"c": "p"}
        assert db.query.call_count == 1
        assert "workflow_runs.user_id = 'user-1'" in q.sql()

    # Plan #8 | B6,B9 | kills: treat a foreign/missing parent as the root
    def test_compute_root_ids_stops_at_child_when_parent_is_foreign_or_missing(self):
        db = _db(_Q(rows=[]))
        runs = [SimpleNamespace(id="c", parent_run_id="foreign")]
        assert _compute_root_ids(db, "user-1", runs) == {"c": "c"}

    # Plan #9 | B5 | kills: single ancestor pass only (no loop)
    def test_compute_root_ids_walks_multiple_levels_when_chain_is_deep(self):
        db = _db(_Q(rows=[("p", "g")]), _Q(rows=[("g", None)]))
        runs = [SimpleNamespace(id="c", parent_run_id="p")]
        assert _compute_root_ids(db, "user-1", runs) == {"c": "g"}
        assert db.query.call_count == 2

    # Plan #10 | B7 | kills: break the root_cache reuse (second run resolved wrongly)
    def test_compute_root_ids_shares_root_when_two_runs_have_same_parent(self):
        db = _db(_Q(rows=[("p", None)]))
        runs = [
            SimpleNamespace(id="a", parent_run_id="p"),
            SimpleNamespace(id="b", parent_run_id="p"),
        ]
        assert _compute_root_ids(db, "user-1", runs) == {"a": "p", "b": "p"}
        assert db.query.call_count == 1

    # Plan #11 | B8 | kills: remove the visited-set cycle guard (infinite loop)
    def test_compute_root_ids_terminates_when_parent_chain_is_cyclic(self):
        db = _db()
        runs = [
            SimpleNamespace(id="a", parent_run_id="b"),
            SimpleNamespace(id="b", parent_run_id="a"),
        ]
        assert _compute_root_ids(db, "user-1", runs) == {"a": "a", "b": "a"}


# =========================================================================== projections
def _fin(**over):
    base = dict(
        chain_context_installed=True, payload_chainable=None, non_chainable_reason=None
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestBuildChainProjection:
    def _run(self, **over):
        return _row(
            id="r1", payload_chainable=True, non_chainable_reason="orig", **over
        )

    # Plan #12 | B10,B14,B16,B18 | kills: wrong default for any field
    def test_build_chain_projection_returns_defaults_when_no_rows_exist(self):
        db = _db(_Q(), _Q(), _Q())
        result = _build_chain_projection(db, self._run(), "user-1")
        assert result == {
            "source_run_id": None, "chain_source": None, "chain_context_installed": None,
            "payload_chainable": True, "non_chainable_reason": "orig",
            "chain_unavailable_reason": None, "finalization_reason": None,
        }  # fmt: skip
        assert db.query.call_count == 3

    # Plan #13 | B10,B11,B12 | kills: keep run values instead of finalization-row values
    def test_build_chain_projection_prefers_finalization_values_when_row_has_them(self):
        fin = _fin(
            chain_context_installed=False,
            payload_chainable=False,
            non_chainable_reason="fin-reason",
        )
        db = _db(_Q(first=fin), _Q(), _Q())
        result = _build_chain_projection(db, self._run(), "user-1")
        assert result["chain_context_installed"] is False
        assert result["payload_chainable"] is False
        assert result["non_chainable_reason"] == "fin-reason"

    # Plan #14 | B11,B12 | kills: overwrite run values with None when finalization columns are None
    def test_build_chain_projection_keeps_run_values_when_finalization_columns_are_none(
        self,
    ):
        db = _db(_Q(first=_fin()), _Q(), _Q())
        result = _build_chain_projection(db, self._run(), "user-1")
        assert result["chain_context_installed"] is True
        assert result["payload_chainable"] is True
        assert result["non_chainable_reason"] == "orig"

    # Plan #15 | B10 | kills: owner filter removed from finalization query
    def test_build_chain_projection_scopes_finalization_query_by_owner(self):
        q = _Q()
        _build_chain_projection(_db(q, _Q(), _Q()), self._run(), "user-1")
        assert q.sql() == [
            "run_finalizations.run_id = 'r1'",
            "run_finalizations.owner_id = 'user-1'",
        ]

    # Plan #16 | B14 | kills: ignore the degraded status check
    def test_build_chain_projection_sets_finalization_reason_when_run_is_degraded(self):
        deg = SimpleNamespace(non_chainable_reason="deg-reason")
        db = _db(_Q(), _Q(first=deg), _Q())
        result = _build_chain_projection(db, self._run(status="degraded"), "user-1")
        assert result["finalization_reason"] == "deg-reason"

    # Plan #17 | B14 | kills: set finalization_reason for non-degraded runs
    def test_build_chain_projection_leaves_finalization_reason_none_when_not_degraded(
        self,
    ):
        deg = SimpleNamespace(non_chainable_reason="deg-reason")
        db = _db(_Q(), _Q(first=deg), _Q())
        result = _build_chain_projection(db, self._run(status="completed"), "user-1")
        assert result["finalization_reason"] is None

    # Plan #18 | B14 | kills: dereference deg_row without the None guard
    def test_build_chain_projection_leaves_finalization_reason_none_when_degraded_row_missing(
        self,
    ):
        db = _db(_Q(), _Q(first=None), _Q())
        result = _build_chain_projection(db, self._run(status="degraded"), "user-1")
        assert result["finalization_reason"] is None

    # Plan #19 | B16 | kills: wrong column / operation filter for unavailable reason
    def test_build_chain_projection_reports_unavailable_outcome_when_audit_row_exists(
        self,
    ):
        q = _Q(first=SimpleNamespace(outcome="scan_failed"))
        result = _build_chain_projection(_db(_Q(), _Q(), q), self._run(), "user-1")
        assert result["chain_unavailable_reason"] == "scan_failed"
        assert (
            "run_provenance_audits.operation = 'chain_context_unavailable'" in q.sql()
        )

    # Plan #20 | B18,B19 | kills: disclose source without ownership / wrong short_id length
    def test_build_chain_projection_returns_chain_source_when_source_is_owned(self):
        src = SimpleNamespace(
            id="src-12345678-abcd", type="ppt", status="completed", git_tag="v2"
        )
        q = _Q(first=src)
        db = _db(_Q(), _Q(), _Q(), q)
        result = _build_chain_projection(
            db, self._run(source_run_id="src-12345678-abcd"), "user-1"
        )
        assert result["chain_source"] == {
            "id": "src-12345678-abcd", "short_id": "src-1234", "workflow_id": "ppt",
            "published_status": "completed", "visible_tag": "v2",
        }  # fmt: skip
        assert result["source_run_id"] == "src-12345678-abcd"
        assert "workflow_runs.user_id = 'user-1'" in q.sql()

    # Plan #21 | B19 | kills: leak source_run_id when source is cross-owner
    def test_build_chain_projection_hides_source_when_source_not_owned(self):
        db = _db(_Q(), _Q(), _Q(), _Q(first=None))
        result = _build_chain_projection(
            db, self._run(source_run_id="foreign"), "user-1"
        )
        assert result["chain_source"] is None
        assert result["source_run_id"] is None

    # Plan #22 | B18 | kills: query source even without a source_run_id
    def test_build_chain_projection_skips_source_query_when_no_source_run_id(self):
        db = _db(_Q(), _Q(), _Q())
        _build_chain_projection(db, self._run(source_run_id=""), "user-1")
        assert db.query.call_count == 3

    @pytest.mark.parametrize(
        ("failing_index", "field"),
        [
            pytest.param(0, "chain_context_installed", id="finalization-query"),
            pytest.param(1, "finalization_reason", id="degraded-query"),
            pytest.param(2, "chain_unavailable_reason", id="audit-query"),
            pytest.param(3, "chain_source", id="source-query"),
        ],
    )
    # Plan #23 | B13,B15,B17,B20 | kills: remove a try/except so the projection raises
    def test_build_chain_projection_swallows_errors_when_a_query_fails(
        self, failing_index, field
    ):
        items = [
            _Q(first=_fin()),
            _Q(first=SimpleNamespace(non_chainable_reason="x")),
            _Q(first=SimpleNamespace(outcome="o")),
            _Q(first=SimpleNamespace(id="s", type="t", status="s", git_tag=None)),
        ]
        items[failing_index] = RuntimeError("db down")
        run = self._run(status="degraded", source_run_id="s")
        result = _build_chain_projection(_db(*items), run, "user-1")
        assert result[field] is None


class TestBuildFinalizationProjection:
    # Plan #24 | B21 | kills: swap payload_chainable / non_chainable_reason or drop owner filter
    def test_build_finalization_projection_returns_row_values_when_row_exists(self):
        row = SimpleNamespace(
            chain_context_installed=True,
            payload_chainable=False,
            non_chainable_reason="r",
        )
        q = _Q(first=row)
        assert _build_finalization_projection(_db(q), "r1", "user-1") == {
            "chain_context_installed": True, "payload_chainable": False, "non_chainable_reason": "r",
        }  # fmt: skip
        assert q.sql() == [
            "run_finalizations.run_id = 'r1'",
            "run_finalizations.owner_id = 'user-1'",
        ]

    # Plan #25 | B21 | kills: deref None row
    def test_build_finalization_projection_returns_nones_when_no_row(self):
        assert _build_finalization_projection(_db(_Q()), "r1", "user-1") == {
            "chain_context_installed": None, "payload_chainable": None, "non_chainable_reason": None,
        }  # fmt: skip

    # Plan #26 | B22 | kills: remove try/except
    def test_build_finalization_projection_returns_nones_when_query_raises(self):
        assert _build_finalization_projection(_db(RuntimeError("x")), "r1", "user-1") == {
            "chain_context_installed": None, "payload_chainable": None, "non_chainable_reason": None,
        }  # fmt: skip


class TestRunResponse:
    # Plan #27 | B23 | kills: run projection when db missing / forget root injection
    def test_run_response_nulls_computed_fields_when_db_not_supplied(self):
        resp = _run_response(_row(source_run_id="s", payload_chainable=True), "root-9")
        assert resp.root_run_id == "root-9"
        assert resp.source_run_id is None
        assert resp.chain_source is None
        assert resp.payload_chainable is None
        assert resp.id == "run-1"
        assert resp.created_at == T0

    # Plan #28 | B23 | kills: `and` -> `or` on (db, user_id)
    def test_run_response_nulls_computed_fields_when_user_id_missing(self):
        db = _db()
        resp = _run_response(_row(), "root-9", db=db)
        assert resp.chain_context_installed is None
        db.query.assert_not_called()

    # Plan #29 | B23,B24 | kills: skip chain projection when db and user supplied
    def test_run_response_includes_chain_source_when_source_owned(self):
        src = SimpleNamespace(id="src-1", type="ppt", status="completed", git_tag=None)
        db = _db(_Q(), _Q(), _Q(), _Q(first=src))
        resp = _run_response(
            _row(source_run_id="src-1"), "root-9", db=db, user_id="user-1"
        )
        assert resp.source_run_id == "src-1"
        assert resp.chain_source == {
            "id": "src-1", "short_id": "src-1", "workflow_id": "ppt",
            "published_status": "completed", "visible_tag": None,
        }  # fmt: skip

    # Plan #30 | B24 | kills: expose raw ORM source_run_id for cross-owner source
    def test_run_response_hides_source_run_id_when_source_not_owned(self):
        db = _db(_Q(), _Q(), _Q(), _Q(first=None))
        resp = _run_response(
            _row(source_run_id="foreign"), "root-9", db=db, user_id="user-1"
        )
        assert resp.source_run_id is None
        assert resp.chain_source is None


class TestRunListResponse:
    # Plan #31 | B25 | kills: read root_run_id from the row instead of the argument
    def test_run_list_response_injects_root_run_id_when_building_slim_model(self):
        row = _row(parent_run_id="p", diverted_at_step_id="step-3", completed_at=T0)
        resp = _run_list_response(row, "root-7")
        assert resp.root_run_id == "root-7"
        assert resp.parent_run_id == "p"
        assert resp.diverted_at_step_id == "step-3"
        assert resp.agent_count == 2
        assert "output" not in resp.model_dump()


# =========================================================================== list_runs
def _list_row(rid: str, **over) -> SimpleNamespace:
    base = dict(
        id=rid, title=f"T-{rid}", type="custom", status="completed", agent_count=1,
        duration=2.0, error=None, token_usage=None, deliverable_mimetype=None,
        deliverable_filename=None, parent_run_id=None, diverted_at_step_id=None,
        user_id="user-1", created_at=T0, completed_at=None,
    )  # fmt: skip
    base.update(over)
    return SimpleNamespace(**base)


def _list_json(rid: str, **over) -> dict:
    base = {
        "id": rid, "title": f"T-{rid}", "type": "custom", "status": "completed",
        "agent_count": 1, "duration": 2.0, "error": None, "token_usage": None,
        "deliverable_mimetype": None, "deliverable_filename": None,
        "parent_run_id": None, "root_run_id": rid, "diverted_at_step_id": None,
        "created_at": T0_ISO, "completed_at": None,
    }  # fmt: skip
    base.update(over)
    return base


class TestListRuns:
    # Plan #32 | B26,B27 | kills: wrong count/total header, dropped owner filter, wrong order
    def test_list_runs_returns_rows_and_total_header_when_runs_exist(self, make_client):
        q = _Q(rows=[_list_row("a"), _list_row("b")], count=7)
        resp = make_client(_db(q)).get("/api/runs")
        assert resp.status_code == 200
        assert resp.json() == [_list_json("a"), _list_json("b")]
        assert resp.headers["X-Total-Count"] == "7"
        assert q.sql() == ["workflow_runs.user_id = 'user-1'"]
        assert [str(o) for o in q.order] == ["workflow_runs.created_at DESC"]
        assert (q.offset_v, q.limit_v) == (0, 50)

    # Plan #33 | B5 | kills: return None/raise for empty page
    def test_list_runs_returns_empty_list_when_no_runs(self, make_client):
        resp = make_client(_db(_Q(rows=[], count=0))).get("/api/runs")
        assert resp.status_code == 200
        assert resp.json() == []
        assert resp.headers["X-Total-Count"] == "0"

    # Plan #34 | B26,B27 | kills: ignore either filter
    def test_list_runs_applies_type_and_status_filters_when_provided(self, make_client):
        q = _Q(rows=[], count=0)
        make_client(_db(q)).get("/api/runs?type=custom&status_filter=failed")
        assert q.sql() == [
            "workflow_runs.user_id = 'user-1'",
            "workflow_runs.type = 'custom'",
            "workflow_runs.status = 'failed'",
        ]

    # Plan #35 | B26,B27 | kills: `is not None` instead of truthiness
    def test_list_runs_ignores_empty_filters_when_values_are_blank(self, make_client):
        q = _Q(rows=[], count=0)
        make_client(_db(q)).get("/api/runs?type=&status_filter=")
        assert q.sql() == ["workflow_runs.user_id = 'user-1'"]

    # Plan #36 | B28 | kills: ignore limit/offset query params
    def test_list_runs_passes_limit_and_offset_when_within_bounds(self, make_client):
        q = _Q(rows=[], count=0)
        make_client(_db(q)).get("/api/runs?limit=100&offset=5")
        assert (q.offset_v, q.limit_v) == (5, 100)

    @pytest.mark.parametrize(
        ("qs", "field", "err_type"),
        [
            pytest.param(
                "limit=0", "limit", "greater_than_equal", id="limit-below-min"
            ),
            pytest.param("limit=101", "limit", "less_than_equal", id="limit-above-max"),
            pytest.param(
                "offset=-1", "offset", "greater_than_equal", id="offset-negative"
            ),
        ],
    )
    # Plan #37 | B28 | kills: loosen Query bounds
    def test_list_runs_returns_422_when_pagination_out_of_bounds(
        self, make_client, qs, field, err_type
    ):
        resp = make_client(_db()).get(f"/api/runs?{qs}")
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail[0]["loc"] == ["query", field]
        assert detail[0]["type"] == err_type

    # Plan #38 | B6,B9 | kills: forget to pass computed roots into the response
    def test_list_runs_uses_owned_ancestor_as_root_when_row_has_parent(
        self, make_client
    ):
        q = _Q(rows=[_list_row("c", parent_run_id="p")], count=1)
        anc = _Q(rows=[("p", None)])
        resp = make_client(_db(q, anc)).get("/api/runs")
        assert resp.json() == [_list_json("c", parent_run_id="p", root_run_id="p")]


# =========================================================================== export_pptx
@pytest.fixture
def gen():
    with patch("app.services.pptx_export.generate_pptx_from_code", autospec=True) as m:
        m.return_value = b"PPTX-BYTES"
        yield m


def _post_export(client, **body):
    return client.post("/api/runs/export-pptx", json=body)


class TestExportPptx:
    # Plan #39 | B29,B40 | kills: wrong media type / filename / args to generator
    def test_export_pptx_returns_file_when_js_code_supplied(self, make_client, gen):
        db = _db()
        resp = _post_export(make_client(db), js_code="const a = 1;")
        assert resp.status_code == 200
        assert resp.content == b"PPTX-BYTES"
        assert resp.headers["content-type"] == PPTX_CT
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="Presentation.pptx"'
        )
        gen.assert_called_once_with("const a = 1;", title="Presentation")
        db.query.assert_not_called()

    # Plan #40 | B29 | kills: query DB even though js_code was supplied
    def test_export_pptx_skips_db_lookup_when_js_code_and_workflow_id_both_given(
        self, make_client, gen
    ):
        db = _db()
        _post_export(make_client(db), js_code="X", workflow_id="wf-1")
        gen.assert_called_once_with("X", title="Presentation")
        db.query.assert_not_called()

    # Plan #41 | B30,B32 | kills: match wrong agent id / drop owner filter
    def test_export_pptx_uses_ppt_code_generator_output_when_workflow_id_given(
        self, make_client, gen
    ):
        outputs = json.dumps([
            {"agent_id": "app-code-generator", "output": "WRONG"},
            {"agent_id": "ppt-code-generator", "output": "RIGHT"},
        ])  # fmt: skip
        q = _Q(first=SimpleNamespace(agent_outputs=outputs))
        resp = _post_export(make_client(_db(q)), workflow_id="wf-1", title="Deck")
        assert resp.status_code == 200
        gen.assert_called_once_with("RIGHT", title="Deck")
        assert q.sql() == [
            "workflow_runs.id = 'wf-1'",
            "workflow_runs.user_id = 'user-1'",
        ]

    @pytest.mark.parametrize(
        "wr",
        [
            pytest.param(None, id="run-missing-or-foreign"),
            pytest.param(SimpleNamespace(agent_outputs=None), id="no-agent-outputs"),
            pytest.param(
                SimpleNamespace(agent_outputs="{not json"), id="malformed-json"
            ),
            pytest.param(
                SimpleNamespace(
                    agent_outputs=json.dumps([{"agent_id": "other", "output": "z"}])
                ),
                id="no-matching-agent",
            ),
        ],
    )
    # Plan #42 | B30,B31,B32,B38 | kills: fall through to generator / let JSON error escape
    def test_export_pptx_returns_400_when_no_code_found_from_workflow(
        self, make_client, gen, wr
    ):
        resp = _post_export(make_client(_db(_Q(first=wr))), workflow_id="wf-1")
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": "Could not find PptxGenJS code. Try re-running the pipeline."
        }
        gen.assert_not_called()

    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            pytest.param(
                "<html><script>const a=1;</script><script>function generatePresentation(pptx) { if (a) { b(); } }</script></html>",
                "function generatePresentation(pptx) { if (a) { b(); } }",
                id="second-script-nested-braces",
            ),
            pytest.param(
                "<script>async function generatePresentation() { return 1; }</script>",
                "async function generatePresentation() { return 1; }",
                id="async-function",
            ),
            pytest.param(
                "<div>function generatePresentation(){return 2;}</div>",
                "function generatePresentation(){return 2;}",
                id="html-fallback-no-script",
            ),
            pytest.param(
                "<div>function generatePresentation(){ if (a) { b(); } return 1; }</div>",
                "function generatePresentation(){ if (a) { b(); } return 1; }",
                id="html-fallback-nested-braces",
            ),
            pytest.param(
                "<script>x=1</script><p>function generatePresentation(){return 3;}</p>",
                "function generatePresentation(){return 3;}",
                id="html-fallback-after-script-without-function",
            ),
        ],
    )
    # Plan #43 | B33,B34,B35,B36,B37 | kills: wrong brace-depth or regex in extraction
    def test_export_pptx_extracts_function_when_html_contains_generate_presentation(
        self, make_client, gen, html, expected
    ):
        resp = _post_export(make_client(_db()), html=html)
        assert resp.status_code == 200
        gen.assert_called_once_with(expected, title="Presentation")

    @pytest.mark.parametrize(
        "html",
        [
            pytest.param("<p>nothing here</p>", id="no-function"),
            pytest.param(
                "<script>function generatePresentation(){ x </script>",
                id="unbalanced-braces",
            ),
        ],
    )
    # Plan #44 | B35,B37,B38 | kills: accept unbalanced function (end > start guard removed)
    def test_export_pptx_returns_400_when_html_has_no_complete_function(
        self, make_client, gen, html
    ):
        resp = _post_export(make_client(_db()), html=html)
        assert resp.status_code == 400
        gen.assert_not_called()

    # Plan #45 | B38 | kills: generate from empty code
    def test_export_pptx_returns_400_when_nothing_supplied(self, make_client, gen):
        resp = _post_export(make_client(_db()))
        assert resp.status_code == 400
        gen.assert_not_called()

    # Plan #46 | B39 | kills: not truncating / not mapping to 500
    def test_export_pptx_returns_500_with_truncated_message_when_generator_fails(
        self, make_client, gen
    ):
        # ASSUMPTION: surfacing up to 200 chars of the exception text is intended behaviour.
        gen.side_effect = RuntimeError("x" * 300)
        resp = _post_export(make_client(_db()), js_code="J")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Failed to generate PPTX: " + "x" * 200}

    @pytest.mark.parametrize(
        ("title", "filename"),
        [
            pytest.param(
                "My Deck: Q1/2026", "My_Deck__Q1_2026.pptx", id="specials-replaced"
            ),
            pytest.param(
                'x\r\nSet-Cookie: a=b"',
                "x__Set-Cookie__a_b_.pptx",
                id="crlf-and-quote-neutralised",
            ),
            pytest.param("a" * 50, "a" * 40 + ".pptx", id="truncated-to-40"),
            pytest.param("", "Presentation.pptx", id="empty-falls-back"),
        ],
    )
    # Plan #47 | B40 | kills: widen allowed alphabet / drop [:40] / drop `or` default
    def test_export_pptx_sanitises_filename_when_title_has_unsafe_characters(
        self, make_client, gen, title, filename
    ):
        resp = _post_export(make_client(_db()), js_code="J", title=title)
        assert (
            resp.headers["content-disposition"] == f'attachment; filename="{filename}"'
        )

    @pytest.mark.parametrize(
        ("body", "loc"),
        [
            pytest.param({"title": "t" * 121}, ["body", "title"], id="title-too-long"),
            pytest.param(
                {"workflow_id": "w" * 65},
                ["body", "workflow_id"],
                id="workflow-id-too-long",
            ),
            pytest.param(
                {"js_code": "j" * 512_001}, ["body", "js_code"], id="js-too-long"
            ),
        ],
    )
    # Plan #48 | B29 | kills: loosen a max_length
    def test_export_pptx_returns_422_when_field_exceeds_max_length(
        self, make_client, gen, body, loc
    ):
        resp = _post_export(make_client(_db()), **body)
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == loc
        assert resp.json()["detail"][0]["type"] == "string_too_long"


# =========================================================================== get_run / delete_run
class TestGetRun:
    # Plan #49 | B41 | kills: wrong field mapping / missing owner filter
    def test_get_run_returns_full_body_when_run_owned(self, make_client):
        run_q = _Q(first=_row())
        resp = make_client(_db(run_q, _Q(), _Q(), _Q())).get("/api/runs/run-1")
        assert resp.status_code == 200
        assert resp.json() == {
            "id": "run-1", "title": "T", "type": "custom", "status": "completed",
            "input": "in", "output": "out", "agent_outputs": None, "agent_count": 2,
            "duration": 1.5, "error": None, "token_usage": None, "model_id": "m1",
            "deliverable_mimetype": None, "deliverable_filename": None,
            "parent_run_id": None, "root_run_id": "run-1", "source_run_id": None,
            "diverted_at_step_id": None, "created_at": T0_ISO, "completed_at": None,
            "chain_source": None, "chain_context_installed": None,
            "payload_chainable": None, "non_chainable_reason": None,
            "chain_unavailable_reason": None, "finalization_reason": None,
        }  # fmt: skip
        assert run_q.sql() == [
            "workflow_runs.id = 'run-1'",
            "workflow_runs.user_id = 'user-1'",
        ]

    # Plan #50 | B41 | kills: return 403/200 for missing or cross-owner run
    def test_get_run_returns_404_when_run_missing_or_foreign(self, make_client):
        resp = make_client(_db(_Q(first=None))).get("/api/runs/other")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}


_CHILD_MODELS = [
    RunEvent, ArtifactRef, WorkflowClarification, GateEvent, HookRun, ExecRun,
    RunCapabilities, ValidationResult, SubagentRun, WaveRun,
]  # fmt: skip


class TestDeleteRun:
    # Plan #51 | B42 | kills: skip a child table / commit missing / wrong delete order
    def test_delete_run_removes_children_then_parent_when_owned(self, make_client):
        run = _row()
        child_qs = [_Q() for _ in _CHILD_MODELS]
        upd_q = _Q()
        db = _db(_Q(first=run), *child_qs, upd_q)
        resp = make_client(db).delete("/api/runs/run-1")
        assert resp.status_code == 204
        assert resp.content == b""
        queried = [c.args[0] for c in db.query.call_args_list]
        assert queried == [WorkflowRun, *_CHILD_MODELS, WorkflowRun]
        assert all(
            q.deleted and q.delete_kwargs == {"synchronize_session": False}
            for q in child_qs
        )
        values, kwargs = upd_q.update_args
        assert [k.key for k in values] == ["parent_run_id"]
        assert list(values.values()) == [None]
        assert kwargs == {"synchronize_session": False}
        db.delete.assert_called_once_with(run)
        db.commit.assert_called_once_with()

    # Plan #52 | B42 | kills: delete without ownership check
    def test_delete_run_returns_404_and_deletes_nothing_when_not_owned(
        self, make_client
    ):
        db = _db(_Q(first=None))
        resp = make_client(db).delete("/api/runs/other")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}
        assert db.query.call_count == 1
        db.delete.assert_not_called()
        db.commit.assert_not_called()


# =========================================================================== chain context
def _chain_run(**over) -> SimpleNamespace:
    base = dict(
        id="run-1", type="custom", title="T", input="brief line", output="out",
        agent_outputs=None, parent_run_id=None,
    )  # fmt: skip
    base.update(over)
    return SimpleNamespace(**base)


def _agents(**outputs) -> str:
    return json.dumps(
        [{"agent_id": k.replace("_", "-"), "output": v} for k, v in outputs.items()]
    )


_SPEC = (
    '<spec>{"title":"T","audience":"A","tone":"warm","theme_choice":"dark","slides":'
    '[{"index":1,"title":"S1","type":"title","content":"abc"},{"title":"S2"}]}</spec>'
)
_SPEC_TEXT = (
    "Title: T\nAudience: A\nTone: warm\nTheme: dark\n\nSlide Plan (2 slides):\n"
    "  Slide 1: S1 [title]\n    Content: abc\n  Slide ?: S2 []"
)


class TestExtractChainContext:
    # Plan #53 | B59 | kills: wrong block format / ids
    def test_extract_chain_context_builds_context_block_when_summary_present(self):
        ctx = _extract_chain_context(_chain_run())
        assert ctx.workflow_id == "run-1"
        assert ctx.pipeline_type == "custom"
        assert ctx.title == "T"
        assert ctx.brief == "brief line"
        assert ctx.structured_summary == "out"
        assert ctx.agent_summaries == []
        assert ctx.context_block == (
            "=== CONTEXT FROM PREVIOUS PIPELINE (custom) ===\nTitle: T\n"
            "Original Brief: brief line\n\nout\n=== END PREVIOUS CONTEXT ==="
        )

    # Plan #54 | B59 | kills: build a block when there is no summary
    def test_extract_chain_context_returns_empty_block_when_no_summary(self):
        ctx = _extract_chain_context(_chain_run(output=None))
        assert ctx.structured_summary == ""
        assert ctx.context_block == ""

    # Plan #55 | B59 | kills: brief[:200] limit changed
    def test_extract_chain_context_truncates_brief_in_block_when_brief_long(self):
        ctx = _extract_chain_context(_chain_run(input="b" * 300))
        assert ctx.brief == "b" * 300
        assert "Original Brief: " + "b" * 200 + "\n\n" in ctx.context_block

    @pytest.mark.parametrize(
        ("title", "inp", "exp_title", "exp_brief"),
        [
            pytest.param("Plain", "Hello world\nsecond", "Plain", "Hello world", id="plain"),
            pytest.param("=== REVISION REQUEST ===\nMake it blue\n=== END ===", "x", "Make it blue", "x", id="title-revision-marker"),
            pytest.param("=== CTX ===\nReal title", "x", "Real title", "x", id="title-marker-stripped"),
            pytest.param("=== ONLY ===", "x", "=== ONLY ===", "x", id="title-only-marker-kept"),
            pytest.param("T", "=== REVISION REQUEST ===\nFix it\n=== END REQUEST ===", "T", "Fix it", id="brief-revision-marker"),
            pytest.param("T", "=== X ===\nreal brief", "T", "real brief", id="brief-marker-stripped"),
            pytest.param(None, None, "", "", id="none-values"),
        ],
    )  # fmt: skip
    # Plan #56 | B43,B44,B45,B46,B47 | kills: alter marker regex / fallbacks
    def test_extract_chain_context_cleans_title_and_brief_when_markers_present(
        self, title, inp, exp_title, exp_brief
    ):
        ctx = _extract_chain_context(_chain_run(title=title, input=inp))
        assert (ctx.title, ctx.brief) == (exp_title, exp_brief)

    # Plan #57 | B48 | kills: let JSON error escape
    def test_extract_chain_context_ignores_agent_outputs_when_json_malformed(self):
        ctx = _extract_chain_context(
            _chain_run(type="ppt", agent_outputs="{bad", output="fallback")
        )
        assert ctx.structured_summary == "fallback"
        assert ctx.agent_summaries == []

    # Plan #58 | B49 | kills: KeyError when agent has no output key
    def test_extract_chain_context_treats_missing_output_key_as_empty(self):
        outs = json.dumps([{"agent_id": "ppt-brief-analyst"}])
        ctx = _extract_chain_context(
            _chain_run(type="ppt", agent_outputs=outs, output=None)
        )
        assert ctx.structured_summary == ""

    @pytest.mark.parametrize("ptype", ["ppt", "ppt_revision"])
    # Plan #59 | B50,B51 | kills: wrong spec formatting or summary trimming
    def test_extract_chain_context_formats_slide_plan_when_ppt_spec_valid(self, ptype):
        ctx = _extract_chain_context(
            _chain_run(type=ptype, agent_outputs=_agents(ppt_brief_analyst=_SPEC))
        )
        assert ctx.structured_summary == "Presentation Slide Plan:\n" + _SPEC_TEXT
        assert ctx.agent_summaries == [
            {"agent": "Presentation Strategist", "summary": _SPEC_TEXT}
        ]

    # Plan #60 | B50 | kills: emit optional lines when absent
    def test_extract_chain_context_emits_only_title_when_spec_is_empty_object(self):
        outs = _agents(ppt_brief_analyst="<spec>{}</spec>")
        ctx = _extract_chain_context(_chain_run(type="ppt", agent_outputs=outs))
        assert ctx.structured_summary == "Presentation Slide Plan:\nTitle: "

    # Plan #61 | B50 | kills: drop the JSON-failure fallback
    def test_extract_chain_context_uses_raw_spec_text_when_spec_json_invalid(self):
        outs = _agents(ppt_brief_analyst="<spec>not json</spec>")
        ctx = _extract_chain_context(_chain_run(type="ppt", agent_outputs=outs))
        assert ctx.structured_summary == "Presentation Slide Plan:\nnot json"

    # Plan #62 | B51 | kills: ignore analyst text when no spec tags
    def test_extract_chain_context_uses_analyst_text_when_no_spec_tags(self):
        outs = _agents(ppt_brief_analyst="a" * 3500)
        ctx = _extract_chain_context(_chain_run(type="ppt", agent_outputs=outs))
        assert ctx.structured_summary == "a" * 3000
        assert ctx.agent_summaries == [
            {"agent": "Presentation Strategist", "summary": "a" * 500}
        ]

    @pytest.mark.parametrize(
        ("outputs", "output", "summary", "agents"),
        [
            pytest.param(dict(backlog_compiler="C" * 5000), "ignored", "C" * 4000, [{"agent": "Backlog Compiler", "summary": "C" * 500}], id="compiler"),
            pytest.param({}, "final text", "final text", [{"agent": "Backlog Compiler", "summary": "final text"}], id="falls-back-to-run-output"),
            pytest.param({}, None, "", [], id="nothing"),
        ],
    )  # fmt: skip
    # Plan #63 | B52 | kills: wrong agent id / truncation / fallback
    def test_extract_chain_context_summarises_backlog_when_user_stories(
        self, outputs, output, summary, agents
    ):
        run = _chain_run(
            type="user_stories", agent_outputs=_agents(**outputs), output=output
        )
        ctx = _extract_chain_context(run)
        assert ctx.structured_summary == summary
        assert ctx.agent_summaries == agents

    @pytest.mark.parametrize(
        ("outputs", "summary", "agents"),
        [
            pytest.param(dict(prototype_specify="<spec>  # Spec body  </spec>"), "Prototype Specification:\n# Spec body", [{"agent": "Spec Writer", "summary": "# Spec body"}], id="tagged"),
            pytest.param(dict(prototype_specify="plain spec"), "Prototype Specification:\nplain spec", [{"agent": "Spec Writer", "summary": "plain spec"}], id="untagged"),
            pytest.param(dict(prototype_plan="<spec>P</spec>"), "Prototype Specification:\nP", [{"agent": "Spec Writer", "summary": "P"}], id="plan-fallback"),
            pytest.param(dict(prototype_specify="x" * 4000), "Prototype Specification:\n" + "x" * 3500, [{"agent": "Spec Writer", "summary": "x" * 500}], id="truncated"),
        ],
    )  # fmt: skip
    # Plan #64 | B53 | kills: wrong agent ids / limits
    def test_extract_chain_context_uses_spec_writer_when_prototype(
        self, outputs, summary, agents
    ):
        run = _chain_run(
            type="prototype", agent_outputs=_agents(**outputs), output=None
        )
        ctx = _extract_chain_context(run)
        assert ctx.structured_summary == summary
        assert ctx.agent_summaries == agents

    @pytest.mark.parametrize(
        "ptype",
        [
            "prototype_revision",
            "prototype_large_revision",
            "prototype_feature_revision",
        ],
    )
    # Plan #65 | B53 | kills: revision fallback regex / missing type
    def test_extract_chain_context_uses_revision_instruction_when_revision_has_no_spec(
        self, ptype
    ):
        inp = "=== REVISION REQUEST ===\nMake header sticky\n=== END REQUEST ==="
        ctx = _extract_chain_context(_chain_run(type=ptype, input=inp, output=None))
        assert ctx.structured_summary == "Prototype Revision: Make header sticky"
        assert ctx.agent_summaries == [
            {"agent": "Revision Specialist", "summary": "Make header sticky"}
        ]

    # Plan #66 | B53 | kills: crash when markers missing
    def test_extract_chain_context_returns_empty_when_revision_input_has_no_markers(
        self,
    ):
        ctx = _extract_chain_context(
            _chain_run(type="prototype_revision", input="no markers", output=None)
        )
        assert ctx.structured_summary == ""
        assert ctx.agent_summaries == []

    # Plan #67 | B53 | kills: apply revision fallback to non-revision prototype
    def test_extract_chain_context_returns_empty_when_plain_prototype_has_no_spec(self):
        inp = "=== REVISION REQUEST ===\nMake header sticky\n=== END REQUEST ==="
        ctx = _extract_chain_context(
            _chain_run(type="prototype", input=inp, output=None)
        )
        assert ctx.structured_summary == ""

    @pytest.mark.parametrize(
        ("outputs", "summary", "agents"),
        [
            pytest.param(dict(app_user_stories="S" * 2000, app_system_design="D" * 2000), "User Stories:\n" + "S" * 1500 + "\n\nSystem Design:\n" + "D" * 1500, [{"agent": "App User Stories", "summary": "S" * 300}, {"agent": "System Design", "summary": "D" * 300}], id="both"),
            pytest.param(dict(app_system_design="D"), "System Design:\nD", [{"agent": "System Design", "summary": "D"}], id="design-only"),
            pytest.param(dict(app_user_stories="S"), "User Stories:\nS", [{"agent": "App User Stories", "summary": "S"}], id="stories-only"),
            pytest.param({}, "", [], id="neither"),
        ],
    )  # fmt: skip
    # Plan #68 | B54 | kills: swap order / limits
    def test_extract_chain_context_joins_parts_when_app_builder(
        self, outputs, summary, agents
    ):
        run = _chain_run(
            type="app_builder", agent_outputs=_agents(**outputs), output=None
        )
        ctx = _extract_chain_context(run)
        assert ctx.structured_summary == summary
        assert ctx.agent_summaries == agents

    @pytest.mark.parametrize(
        ("outputs", "summary"),
        [
            pytest.param(dict(mulesoft_inventory="I" * 2500, mulesoft_decomposition="M" * 2500), "Mulesoft Inventory:\n" + "I" * 2000 + "\n\nMigration Decomposition:\n" + "M" * 2000, id="both"),
            pytest.param(dict(mulesoft_decomposition="M"), "Migration Decomposition:\nM", id="decomposition-only"),
            pytest.param(dict(mulesoft_inventory="I"), "Mulesoft Inventory:\nI", id="inventory-only"),
            pytest.param({}, "", id="neither"),
        ],
    )  # fmt: skip
    # Plan #69 | B55 | kills: wrong labels / limits
    def test_extract_chain_context_joins_parts_when_mulesoft(self, outputs, summary):
        run = _chain_run(
            type="mulesoft_to_springboot", agent_outputs=_agents(**outputs), output=None
        )
        assert _extract_chain_context(run).structured_summary == summary

    @pytest.mark.parametrize(
        ("outputs", "summary"),
        [
            pytest.param(dict(dotnet_inventory="I" * 2500, dotnet_azure_target_mapping="A" * 2500), ".NET Inventory:\n" + "I" * 2000 + "\n\nAzure Target Mapping:\n" + "A" * 2000, id="both"),
            pytest.param(dict(dotnet_azure_target_mapping="A"), "Azure Target Mapping:\nA", id="mapping-only"),
            pytest.param(dict(dotnet_inventory="I"), ".NET Inventory:\nI", id="inventory-only"),
            pytest.param({}, "", id="neither"),
        ],
    )  # fmt: skip
    # Plan #70 | B56 | kills: wrong labels / limits
    def test_extract_chain_context_joins_parts_when_dotnet(self, outputs, summary):
        run = _chain_run(
            type="dotnet_to_azure", agent_outputs=_agents(**outputs), output=None
        )
        assert _extract_chain_context(run).structured_summary == summary

    # Plan #71 | B57 | kills: 3000 limit changed
    def test_extract_chain_context_truncates_output_when_generic_type(self):
        ctx = _extract_chain_context(_chain_run(type="custom", output="o" * 3500))
        assert ctx.structured_summary == "o" * 3000

    @pytest.mark.parametrize(
        ("output", "expected"),
        [
            pytest.param("plain text", "plain text", id="plain-used"),
            pytest.param("<!DOCTYPE html><p>x</p>", "", id="doctype-skipped"),
            pytest.param(
                "<HTML><body>x</body></HTML>", "", id="html-tag-case-insensitive"
            ),
            pytest.param("z" * 3500, "z" * 3000, id="truncated"),
        ],
    )
    # Plan #72 | B58 | kills: do not skip HTML / drop ignorecase
    def test_extract_chain_context_falls_back_to_output_when_no_structured_summary(
        self, output, expected
    ):
        ctx = _extract_chain_context(_chain_run(type="ppt", output=output))
        assert ctx.structured_summary == expected


class TestGetChainContext:
    # Plan #73 | B60 | kills: 403 or body for foreign run
    def test_get_chain_context_returns_404_when_run_not_owned(self, make_client):
        resp = make_client(_db(_Q(first=None))).get("/api/runs/x/chain-context")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}

    # Plan #74 | B61 | kills: walk for non-revision types
    def test_get_chain_context_uses_run_itself_when_not_revision(self, make_client):
        db = _db(_Q(first=_chain_run(id="r0", type="custom", output="hello")))
        resp = make_client(db).get("/api/runs/r0/chain-context")
        body = resp.json()
        assert resp.status_code == 200
        assert (body["workflow_id"], body["structured_summary"]) == ("r0", "hello")
        assert db.query.call_count == 1

    # Plan #75 | B61 | kills: walk without a parent id
    def test_get_chain_context_uses_run_itself_when_revision_has_no_parent(
        self, make_client
    ):
        run = _chain_run(
            id="r0", type="custom_revision", output="rev", parent_run_id=None
        )
        db = _db(_Q(first=run))
        resp = make_client(db).get("/api/runs/r0/chain-context")
        assert resp.json()["workflow_id"] == "r0"
        assert db.query.call_count == 1

    # Plan #76 | B62,B64 | kills: stop walking at first hop / drop owner filter on parent
    def test_get_chain_context_walks_to_root_when_revision_chain_is_multi_hop(
        self, make_client
    ):
        v3 = _chain_run(
            id="v3", type="custom_revision", parent_run_id="v2", output="v3-out"
        )
        v2 = _chain_run(
            id="v2", type="custom_revision", parent_run_id="v1", output="v2-out"
        )
        v1 = _chain_run(id="v1", type="custom", output="root-out")
        q2 = _Q(first=v2)
        resp = make_client(_db(_Q(first=v3), q2, _Q(first=v1))).get(
            "/api/runs/v3/chain-context"
        )
        body = resp.json()
        assert (body["workflow_id"], body["structured_summary"]) == ("v1", "root-out")
        assert q2.sql() == [
            "workflow_runs.id = 'v2'",
            "workflow_runs.user_id = 'user-1'",
        ]

    # Plan #77 | B63 | kills: use None parent / crash when parent missing
    def test_get_chain_context_uses_run_itself_when_parent_not_found(self, make_client):
        child = _chain_run(
            id="c", type="custom_revision", parent_run_id="gone", output="child-out"
        )
        resp = make_client(_db(_Q(first=child), _Q(first=None))).get(
            "/api/runs/c/chain-context"
        )
        assert resp.json()["workflow_id"] == "c"

    # Plan #78 | B62 | kills: continue past a revision without parent
    def test_get_chain_context_stops_at_revision_without_parent(self, make_client):
        r0 = _chain_run(id="r0", type="custom_revision", parent_run_id="r1")
        r1 = _chain_run(
            id="r1", type="custom_revision", parent_run_id=None, output="r1-out"
        )
        resp = make_client(_db(_Q(first=r0), _Q(first=r1))).get(
            "/api/runs/r0/chain-context"
        )
        assert resp.json()["workflow_id"] == "r1"

    # Plan #79 | B62 | kills: hop cap 20 -> 19 or 21
    def test_get_chain_context_caps_walk_at_twenty_hops_when_chain_is_long(
        self, make_client
    ):
        runs = [
            _chain_run(id=f"r{i}", type="custom_revision", parent_run_id=f"r{i + 1}")
            for i in range(22)
        ]
        db = _db(*[_Q(first=r) for r in runs[:21]])
        resp = make_client(db).get("/api/runs/r0/chain-context")
        assert resp.json()["workflow_id"] == "r20"
        assert db.query.call_count == 21


# =========================================================================== lineage tree
def _ref(rid: str, **over) -> SimpleNamespace:
    base = dict(
        id=rid, kind="k", producer_step="s", producer_agent="a", task_id="t",
        content_hash="h", version=1, visibility="private", retention="run",
        location="loc", parents=None, derived_from=None, content="body",
    )  # fmt: skip
    base.update(over)
    return SimpleNamespace(**base)


def _node(rid: str, children=(), **over) -> dict:
    base = {
        "id": rid, "kind": "k", "producer_step": "s", "producer_agent": "a",
        "task_id": "t", "content_hash": "h", "version": 1, "visibility": "private",
        "retention": "run", "location": "loc", "parents": [], "derived_from": None,
        "children": list(children),
    }  # fmt: skip
    base.update(over)
    return base


class TestBuildLineageTree:
    # Plan #80 | B70 | kills: return None for empty
    def test_build_lineage_tree_returns_empty_list_when_no_refs(self):
        assert _build_lineage_tree([], include_content=False) == []

    # Plan #81 | B65 | kills: include content by default
    def test_build_lineage_tree_omits_content_when_include_content_false(self):
        assert _build_lineage_tree([_ref("a")], include_content=False) == [_node("a")]

    # Plan #82 | B65 | kills: never include content
    def test_build_lineage_tree_adds_content_when_include_content_true(self):
        assert _build_lineage_tree([_ref("a")], include_content=True) == [
            _node("a", content="body")
        ]

    # Plan #83 | B66,B70 | kills: ignore derived_from edge
    def test_build_lineage_tree_nests_child_when_derived_from_in_set(self):
        tree = _build_lineage_tree(
            [_ref("a"), _ref("b", derived_from="a")], include_content=False
        )
        assert tree == [_node("a", [_node("b", derived_from="a")])]

    # Plan #84 | B67,B70 | kills: ignore parents[] edge
    def test_build_lineage_tree_nests_child_when_parents_list_in_set(self):
        tree = _build_lineage_tree(
            [_ref("a"), _ref("b", parents=["a"])], include_content=False
        )
        assert tree == [_node("a", [_node("b", parents=["a"])])]

    # Plan #85 | B66,B67 | kills: accept parent ids outside the scoped set
    def test_build_lineage_tree_treats_ref_as_root_when_parent_outside_set(self):
        ref = _ref("b", parents=["ghost"], derived_from="ghost2")
        tree = _build_lineage_tree([ref], include_content=False)
        assert tree == [_node("b", parents=["ghost"], derived_from="ghost2")]

    # Plan #86 | B67 | kills: attach node under every parent (shared dict)
    def test_build_lineage_tree_attaches_under_first_parent_only_when_multiple_parents(
        self,
    ):
        refs = [_ref("a"), _ref("b"), _ref("c", derived_from="a", parents=["a", "b"])]
        tree = _build_lineage_tree(refs, include_content=False)
        assert tree == [
            _node("a", [_node("c", derived_from="a", parents=["a", "b"])]),
            _node("b"),
        ]

    # Plan #87 | B68 | kills: attach a self-edge
    def test_build_lineage_tree_keeps_root_when_ref_is_its_own_parent(self):
        tree = _build_lineage_tree([_ref("a", derived_from="a")], include_content=False)
        assert tree == [_node("a", derived_from="a")]

    # Plan #88 | B69 | kills: drop cycle check (circular structure)
    def test_build_lineage_tree_breaks_cycle_when_refs_are_mutual_parents(self):
        refs = [_ref("a", parents=["b"]), _ref("b", parents=["a"])]
        tree = _build_lineage_tree(refs, include_content=False)
        assert tree == [_node("b", [_node("a", parents=["b"])], parents=["a"])]

    # Plan #89 | B69 | kills: do not try the next parent after a cycle
    def test_build_lineage_tree_uses_next_parent_when_first_would_cycle(self):
        refs = [_ref("q", parents=["c"]), _ref("c", parents=["q", "p"]), _ref("p")]
        tree = _build_lineage_tree(refs, include_content=False)
        assert tree == [
            _node("p", [_node("c", [_node("q", parents=["c"])], parents=["q", "p"])])
        ]


# =========================================================================== artifacts / events
@pytest.fixture
def scoped_store():
    with patch("agents.authz.ScopedStore", autospec=True) as cls:
        yield cls


class TestGetRunArtifacts:
    # Plan #90 | B71 | kills: build store before owner check
    def test_get_run_artifacts_returns_404_when_run_not_owned(
        self, make_client, scoped_store
    ):
        resp = make_client(_db(_Q(first=None))).get("/api/runs/x/artifacts")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}
        scoped_store.assert_not_called()

    # Plan #91 | B72 | kills: skip the second (ScopedStore) gate
    def test_get_run_artifacts_returns_404_when_store_denies_run(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = None
        resp = make_client(_db(_Q(first=_row()))).get("/api/runs/run-1/artifacts")
        assert resp.status_code == 404
        store.lineage.assert_not_called()

    # Plan #92 | B73,B74 | kills: wrong scope args / include content by default
    def test_get_run_artifacts_returns_tree_without_content_when_no_include(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.lineage.return_value = [_ref("a"), _ref("b", derived_from="a")]
        db = _db(_Q(first=_row(workspace_id="ws-9")))
        resp = make_client(db).get("/api/runs/run-1/artifacts")
        assert resp.status_code == 200
        assert resp.json() == {
            "workflow_id": "run-1",
            "artifacts": [_node("a", [_node("b", derived_from="a")])],
        }
        scoped_store.assert_called_once_with(
            owner_id="user-1", workspace_id="ws-9", session=db
        )
        store.get_run.assert_awaited_once_with("run-1")
        store.lineage.assert_awaited_once_with("run-1")

    # Plan #93 | B74 | kills: `include == "content"` compare
    def test_get_run_artifacts_includes_content_when_include_is_content(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.lineage.return_value = [_ref("a")]
        resp = make_client(_db(_Q(first=_row()))).get(
            "/api/runs/run-1/artifacts?include=content"
        )
        assert resp.json()["artifacts"] == [_node("a", content="body")]

    # Plan #94 | B74 | kills: include content for any include value
    def test_get_run_artifacts_omits_content_when_include_is_other_value(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.lineage.return_value = [_ref("a")]
        resp = make_client(_db(_Q(first=_row()))).get(
            "/api/runs/run-1/artifacts?include=all"
        )
        assert resp.json()["artifacts"] == [_node("a")]

    # Plan #95 | B73 | kills: filter after tree build / wrong equality
    def test_get_run_artifacts_filters_by_kind_before_building_tree(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.lineage.return_value = [
            _ref("a", kind="spec"),
            _ref("b", kind="code", derived_from="a"),
        ]
        resp = make_client(_db(_Q(first=_row()))).get(
            "/api/runs/run-1/artifacts?kind=code"
        )
        assert resp.json()["artifacts"] == [_node("b", kind="code", derived_from="a")]

    # Plan #96 | B73 | kills: 422 / all refs for unknown kind
    def test_get_run_artifacts_returns_empty_tree_when_kind_unknown(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.lineage.return_value = [_ref("a")]
        resp = make_client(_db(_Q(first=_row()))).get(
            "/api/runs/run-1/artifacts?kind=nope"
        )
        assert resp.status_code == 200
        assert resp.json() == {"workflow_id": "run-1", "artifacts": []}


class TestGetRunEvents:
    # Plan #97 | B75 | kills: build store before owner check
    def test_get_run_events_returns_404_when_run_not_owned(
        self, make_client, scoped_store
    ):
        resp = make_client(_db(_Q(first=None))).get("/api/runs/x/events")
        assert resp.status_code == 404
        scoped_store.assert_not_called()

    # Plan #98 | B76 | kills: skip ScopedStore default-deny
    def test_get_run_events_returns_404_when_store_denies_run(
        self, make_client, scoped_store
    ):
        scoped_store.return_value.get_run.return_value = None
        resp = make_client(_db(_Q(first=_row()))).get("/api/runs/run-1/events")
        assert resp.status_code == 404
        scoped_store.return_value.read_events.assert_not_called()

    # Plan #99 | B77 | kills: drop created_at / UTC promotion / wrong after passing
    def test_get_run_events_returns_events_with_utc_created_at_when_rows_exist(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.read_events_page.return_value = [
            SimpleNamespace(seq=6, event_id="e6", type="chat_message", payload_json='{"a":1}', created_at=T0),
            SimpleNamespace(seq=7, event_id="e7", type="done", payload_json="{}", created_at=None),
        ]  # fmt: skip
        db = _db(_Q(first=_row(workspace_id="ws-2")))
        resp = make_client(db).get("/api/runs/run-1/events?after=5")
        assert resp.status_code == 200
        assert resp.json() == {
            "workflow_id": "run-1", "after": 5,
            # QA-KB-119 / ISS-1155: one page; default limit 1000, one extra row probes has_more.
            "has_more": False, "next_after": 7,
            "events": [
                {"seq": 6, "event_id": "e6", "type": "chat_message", "payload_json": '{"a":1}', "created_at": T0_ISO},
                {"seq": 7, "event_id": "e7", "type": "done", "payload_json": "{}", "created_at": None},
            ],
        }  # fmt: skip
        store.read_events_page.assert_awaited_once_with(
            "run-1", after_seq=5, limit=1001
        )
        scoped_store.assert_called_once_with(
            owner_id="user-1", workspace_id="ws-2", session=db
        )

    # Plan #100 | B77 | kills: default `after` != 0
    def test_get_run_events_defaults_after_to_zero_and_returns_empty_events(
        self, make_client, scoped_store
    ):
        store = scoped_store.return_value
        store.get_run.return_value = object()
        store.read_events_page.return_value = []
        resp = make_client(_db(_Q(first=_row()))).get("/api/runs/run-1/events")
        assert resp.json() == {
            "workflow_id": "run-1",
            "after": 0,
            "has_more": False,
            "next_after": 0,
            "events": [],
        }
        store.read_events_page.assert_awaited_once_with(
            "run-1", after_seq=0, limit=1001
        )

    # Plan #101 | B77 | kills: accept non-int `after`
    def test_get_run_events_returns_422_when_after_not_integer(
        self, make_client, scoped_store
    ):
        resp = make_client(_db()).get("/api/runs/run-1/events?after=abc")
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == ["query", "after"]
        assert resp.json()["detail"][0]["type"] == "int_parsing"


# =========================================================================== family
def _member(rid: str, **over) -> SimpleNamespace:
    base = dict(
        id=rid, type="prototype", title=f"T-{rid}", status="completed",
        parent_run_id=None, created_at=datetime(2026, 1, 1, 0, 0, 0), completed_at=None,
        git_tag=None, payload_chainable=None, non_chainable_reason=None,
    )  # fmt: skip
    base.update(over)
    return SimpleNamespace(**base)


class TestOwnedFamilyMembers:
    # Plan #102 | B78,B81 | kills: query finalizations for empty family
    def test_owned_family_members_returns_empty_when_root_missing_and_no_children(self):
        db = _db(_Q(first=None), _Q(rows=[]))
        assert _owned_family_members(db, "user-1", "root") == []
        assert db.query.call_count == 2

    # Plan #103 | B78,B80 | kills: log/compare when root row absent
    def test_owned_family_members_admits_orphan_child_silently_when_root_missing(
        self, caplog
    ):
        child = _member("c1", parent_run_id="root")
        db = _db(_Q(first=None), _Q(rows=[child]), _Q(rows=[]), _Q(rows=[]))
        with caplog.at_level(logging.INFO, logger="app.api.runs"):
            members = _owned_family_members(db, "user-1", "root")
        assert [(m.id, m.revision_index, m.parent_run_id) for m in members] == [
            ("c1", 1, None)
        ]
        assert caplog.records == []

    # Plan #104 | B79,B84 | kills: wrong BFS / order key / parent nulling / owner filter
    def test_owned_family_members_orders_chronologically_with_one_based_index(self):
        root = _member("root", parent_run_id="foreign", created_at=datetime(2026, 1, 1))
        b = _member("b", parent_run_id="root", created_at=datetime(2026, 1, 3))
        a = _member("a", parent_run_id="root", created_at=datetime(2026, 1, 3))
        early = _member("z", parent_run_id="root", created_at=datetime(2026, 1, 2))
        fin_q = _Q(rows=[])
        db = _db(_Q(first=root), _Q(rows=[b, a, early]), _Q(rows=[]), fin_q)
        members = _owned_family_members(db, "user-1", "root")
        assert [(m.id, m.revision_index, m.parent_run_id) for m in members] == [
            ("root", 1, None), ("z", 2, "root"), ("a", 3, "root"), ("b", 4, "root"),
        ]  # fmt: skip
        assert "run_finalizations.owner_id = 'user-1'" in fin_q.sql()

    # Plan #105 | B79 | kills: remove visited guard (infinite BFS)
    def test_owned_family_members_skips_already_visited_when_cycle_exists(self):
        root = _member("root", parent_run_id="c1", created_at=datetime(2025, 12, 31))
        c1 = _member("c1", parent_run_id="root")
        db = _db(_Q(first=root), _Q(rows=[c1]), _Q(rows=[root]), _Q(rows=[]))
        members = _owned_family_members(db, "user-1", "root")
        assert [m.id for m in members] == ["root", "c1"]

    @pytest.mark.parametrize(
        ("child_type", "logged"),
        [
            pytest.param("prototype_large_revision", False, id="large-revision"),
            pytest.param("prototype_feature_revision", False, id="feature-revision"),
            pytest.param("prototype_revision", False, id="generic-revision"),
            pytest.param("prototype", False, id="same-type"),
            pytest.param("ppt_revision", True, id="cross-type"),
        ],
    )
    # Plan #106 | B80 | kills: wrong suffix list / drop the log / drop the child
    def test_owned_family_members_logs_only_cross_type_children(
        self, caplog, child_type, logged
    ):
        root = _member("root", type="prototype", created_at=datetime(2025, 12, 31))
        child = _member("c1", type=child_type, parent_run_id="root")
        db = _db(_Q(first=root), _Q(rows=[child]), _Q(rows=[]), _Q(rows=[]))
        with caplog.at_level(logging.INFO, logger="app.api.runs"):
            members = _owned_family_members(db, "user-1", "root")
        assert [m.id for m in members] == ["root", "c1"]
        messages = [r.getMessage() for r in caplog.records]
        if logged:
            assert messages == [
                "run_family: admitting cross-type child c1 (ppt_revision) under root root (prototype)"
            ]
        else:
            assert messages == []

    # Plan #107 | B83 | kills: prefer run columns over finalization row
    def test_owned_family_members_projects_finalization_when_row_exists(self):
        root = _member(
            "root", payload_chainable=True, non_chainable_reason="run-reason"
        )
        child = _member(
            "c1",
            parent_run_id="root",
            payload_chainable=True,
            non_chainable_reason="run-c1",
        )
        fr = SimpleNamespace(
            run_id="c1", chain_context_installed=True, payload_chainable=False,
            non_chainable_reason="fin-reason",
        )  # fmt: skip
        db = _db(_Q(first=root), _Q(rows=[child]), _Q(rows=[]), _Q(rows=[fr]))
        members = {m.id: m for m in _owned_family_members(db, "user-1", "root")}
        c1, rt = members["c1"], members["root"]
        assert (
            c1.chain_context_installed,
            c1.payload_chainable,
            c1.non_chainable_reason,
        ) == (True, False, "fin-reason")
        assert (
            rt.chain_context_installed,
            rt.payload_chainable,
            rt.non_chainable_reason,
        ) == (None, True, "run-reason")

    # Plan #108 | B82 | kills: let the projection failure escape
    def test_owned_family_members_falls_back_to_run_columns_when_finalization_query_fails(
        self,
    ):
        root = _member("root", payload_chainable=True, git_tag="v1")
        db = _db(_Q(first=root), _Q(rows=[]), RuntimeError("db down"))
        members = _owned_family_members(db, "user-1", "root")
        assert [
            (m.id, m.payload_chainable, m.git_tag, m.chain_context_installed)
            for m in members
        ] == [("root", True, "v1", None)]

    # Plan #109 | B83 | kills: AttributeError when ORM row lacks optional columns
    def test_owned_family_members_defaults_optional_columns_when_row_lacks_them(self):
        root = SimpleNamespace(
            id="root", type="prototype", title="T", status="completed",
            parent_run_id=None, created_at=T0, completed_at=None,
        )  # fmt: skip
        db = _db(_Q(first=root), _Q(rows=[]), _Q(rows=[]))
        (member,) = _owned_family_members(db, "user-1", "root")
        assert (
            member.git_tag,
            member.payload_chainable,
            member.non_chainable_reason,
        ) == (None, None, None)


class TestGetRunFamily:
    # Plan #110 | B85 | kills: leak foreign family on 404
    def test_get_run_family_returns_404_when_run_not_owned(self, make_client):
        db = _db(_Q(first=None))
        resp = make_client(db).get("/api/runs/x/family")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}
        assert db.query.call_count == 1

    # Plan #111 | B85 | kills: wrong root id or dropped members in body
    def test_get_run_family_returns_root_and_members_when_run_owned(self, make_client):
        root = _member("root", created_at=T0)
        db = _db(_Q(first=root), _Q(first=root), _Q(rows=[]), _Q(rows=[]))
        resp = make_client(db).get("/api/runs/root/family")
        assert resp.status_code == 200
        assert resp.json() == {
            "root_id": "root",
            "members": [{
                "id": "root", "type": "prototype", "title": "T-root", "status": "completed",
                "revision_index": 1, "parent_run_id": None, "created_at": T0_ISO,
                "completed_at": None, "git_tag": None, "payload_chainable": None,
                "non_chainable_reason": None, "chain_context_installed": None,
            }],
        }  # fmt: skip


# =========================================================================== summary
def _summary_db(run):
    """Queries for get_run_summary: owner gate, family root, children, finalizations."""
    return _db(_Q(first=run), _Q(first=run), _Q(rows=[]), _Q(rows=[]))


class TestGetRunSummary:
    # Plan #112 | B94 | kills: 403/200 for foreign run
    def test_get_run_summary_returns_404_when_run_not_owned(self, make_client):
        resp = make_client(_db(_Q(first=None))).get("/api/runs/x/summary")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}

    # Plan #113 | B86,B87,B88 | kills: echo unsafe agent keys / wrong token_usage parse
    def test_get_run_summary_projects_safe_fields_when_run_has_agents_and_usage(
        self, make_client
    ):
        agents = [
            {"agent_id": "a1", "name": "N", "output": "SECRET", "input_prompt": "P", "duration": 1.5, "error": None, "model_id": "m"},
            {"agent_id": "a2"},
            "not-a-dict",
        ]  # fmt: skip
        run = _row(
            agent_outputs=json.dumps(agents),
            token_usage='{"total": 10}',
            error="boom",
            status="failed",
            duration=3.0,
        )
        resp = make_client(_summary_db(run)).get("/api/runs/run-1/summary")
        body = resp.json()
        assert resp.status_code == 200
        assert body["agents"] == [
            {
                "agent_id": "a1",
                "name": "N",
                "duration": 1.5,
                "error": None,
                "model_id": "m",
            },
            {"agent_id": "a2"},
        ]
        assert body["token_usage"] == {"total": 10}
        assert (body["id"], body["title"], body["type"], body["status"]) == (
            "run-1",
            "T",
            "custom",
            "failed",
        )
        assert (
            body["input"],
            body["duration"],
            body["agent_count"],
            body["error"],
        ) == ("in", 3.0, 2, "boom")
        assert body["root_id"] == "run-1"
        assert [m["id"] for m in body["members"]] == ["run-1"]

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(None, id="none"),
            pytest.param("", id="empty"),
            pytest.param("{broken", id="malformed"),
            pytest.param('{"a": 1}', id="not-a-list"),
        ],
    )
    # Plan #114 | B86 | kills: 500 on malformed blob / accept non-list
    def test_get_run_summary_returns_empty_agents_when_blob_unusable(
        self, make_client, raw
    ):
        resp = make_client(_summary_db(_row(agent_outputs=raw))).get(
            "/api/runs/run-1/summary"
        )
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(None, id="none"),
            pytest.param("", id="empty"),
            pytest.param("{broken", id="malformed"),
            pytest.param("[1, 2]", id="not-a-dict"),
        ],
    )
    # Plan #115 | B87 | kills: 500 on malformed usage / accept non-dict
    def test_get_run_summary_returns_empty_token_usage_when_blob_unusable(
        self, make_client, raw
    ):
        resp = make_client(_summary_db(_row(token_usage=raw))).get(
            "/api/runs/run-1/summary"
        )
        assert resp.status_code == 200
        assert resp.json()["token_usage"] == {}


# =========================================================================== audit reads
class TestOwnerGateOr404:
    # Plan #116 | B94 | kills: use nullable owner_id / drop user filter
    def test_owner_gate_or_404_returns_run_when_owned(self):
        run = _row()
        q = _Q(first=run)
        assert _owner_gate_or_404(_db(q), "run-1", "user-1") is run
        assert q.sql() == [
            "workflow_runs.id = 'run-1'",
            "workflow_runs.user_id = 'user-1'",
        ]

    # Plan #117 | B94 | kills: return None / 403
    def test_owner_gate_or_404_raises_404_when_run_not_found(self):
        with pytest.raises(HTTPException) as exc:
            _owner_gate_or_404(_db(_Q(first=None)), "run-1", "user-1")
        assert exc.value.status_code == 404
        assert exc.value.detail == NOT_FOUND


class TestHookRuns:
    # Plan #118 | B89 | kills: fetch rows for foreign run
    def test_get_hook_runs_returns_404_when_run_not_owned(self, make_client):
        db = _db(_Q(first=None))
        resp = make_client(db).get("/api/runs/x/hook-runs")
        assert resp.status_code == 404
        assert db.query.call_count == 1

    # Plan #119 | B89,B90 | kills: drop owner filter / order / created_at None guard
    def test_get_hook_runs_returns_rows_when_run_owned(self, make_client):
        rows_q = _Q(rows=[
            SimpleNamespace(id="h1", hook="pre", event="e", outcome="ok", detail="d", created_at=T0),
            SimpleNamespace(id="h2", hook="post", event="e2", outcome="skip", detail=None, created_at=None),
        ])  # fmt: skip
        resp = make_client(_db(_Q(first=_row()), rows_q)).get(
            "/api/runs/run-1/hook-runs"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "workflow_id": "run-1",
            "hook_runs": [
                {"id": "h1", "hook": "pre", "event": "e", "outcome": "ok", "detail": "d", "created_at": "2026-01-02T03:04:05"},
                {"id": "h2", "hook": "post", "event": "e2", "outcome": "skip", "detail": None, "created_at": None},
            ],
        }  # fmt: skip
        assert rows_q.sql() == [
            "hook_runs.run_id = 'run-1'",
            "hook_runs.owner_id = 'user-1'",
        ]
        assert [str(o) for o in rows_q.order] == ["hook_runs.created_at ASC"]


class TestGateEvents:
    # Plan #120 | B91 | kills: fetch rows for foreign run
    def test_get_gate_events_returns_404_when_run_not_owned(self, make_client):
        db = _db(_Q(first=None))
        resp = make_client(db).get("/api/runs/x/gate-events")
        assert resp.status_code == 404
        assert db.query.call_count == 1

    # Plan #121 | B91 | kills: wrong field mapping / owner filter
    def test_get_gate_events_returns_rows_when_run_owned(self, make_client):
        rows_q = _Q(rows=[
            SimpleNamespace(id="g1", run_id="run-1", step="s", gate="approve", outcome="ok", detail="d", created_at=T0),
            SimpleNamespace(id="g2", run_id="run-1", step="s2", gate="g", outcome="no", detail=None, created_at=None),
        ])  # fmt: skip
        resp = make_client(_db(_Q(first=_row()), rows_q)).get(
            "/api/runs/run-1/gate-events"
        )
        assert resp.json() == {
            "workflow_id": "run-1",
            "gate_events": [
                {"id": "g1", "run_id": "run-1", "step": "s", "gate": "approve", "outcome": "ok", "detail": "d", "created_at": "2026-01-02T03:04:05"},
                {"id": "g2", "run_id": "run-1", "step": "s2", "gate": "g", "outcome": "no", "detail": None, "created_at": None},
            ],
        }  # fmt: skip
        assert rows_q.sql() == [
            "gate_events.run_id = 'run-1'",
            "gate_events.owner_id = 'user-1'",
        ]


class TestValidationResults:
    # Plan #122 | B92 | kills: fetch rows for foreign run
    def test_get_validation_results_returns_404_when_run_not_owned(self, make_client):
        db = _db(_Q(first=None))
        resp = make_client(db).get("/api/runs/x/validation-results")
        assert resp.status_code == 404
        assert db.query.call_count == 1

    # Plan #123 | B92 | kills: wrong field mapping / owner filter
    def test_get_validation_results_returns_rows_when_run_owned(self, make_client):
        rows_q = _Q(rows=[
            SimpleNamespace(id="v1", run_id="run-1", step="s", validator="html", severity="error", attempt=2, issues='["x"]', created_at=T0),
            SimpleNamespace(id="v2", run_id="run-1", step="s", validator="css", severity="warn", attempt=1, issues=None, created_at=None),
        ])  # fmt: skip
        resp = make_client(_db(_Q(first=_row()), rows_q)).get(
            "/api/runs/run-1/validation-results"
        )
        assert resp.json() == {
            "workflow_id": "run-1",
            "validation_results": [
                {"id": "v1", "run_id": "run-1", "step": "s", "validator": "html", "severity": "error", "attempt": 2, "issues": '["x"]', "created_at": "2026-01-02T03:04:05"},
                {"id": "v2", "run_id": "run-1", "step": "s", "validator": "css", "severity": "warn", "attempt": 1, "issues": None, "created_at": None},
            ],
        }  # fmt: skip
        assert rows_q.sql() == [
            "validation_results.run_id = 'run-1'",
            "validation_results.owner_id = 'user-1'",
        ]


class TestExecRuns:
    # Plan #124 | B93 | kills: fetch rows for foreign run
    def test_get_exec_runs_returns_404_when_run_not_owned(self, make_client):
        db = _db(_Q(first=None))
        resp = make_client(db).get("/api/runs/x/exec-runs")
        assert resp.status_code == 404
        assert db.query.call_count == 1

    # Plan #125 | B93 | kills: wrong field mapping / owner filter
    def test_get_exec_runs_returns_rows_when_run_owned(self, make_client):
        rows_q = _Q(rows=[
            SimpleNamespace(id="x1", run_id="run-1", step="s", argv_json='["ls"]', outcome="ok", exit_code=0, duration_ms=12, policy_snapshot_json="{}", output_digest="abc", created_at=T0),
            SimpleNamespace(id="x2", run_id="run-1", step="s", argv_json="[]", outcome="fail", exit_code=1, duration_ms=3, policy_snapshot_json=None, output_digest=None, created_at=None),
        ])  # fmt: skip
        resp = make_client(_db(_Q(first=_row()), rows_q)).get(
            "/api/runs/run-1/exec-runs"
        )
        assert resp.json() == {
            "workflow_id": "run-1",
            "exec_runs": [
                {"id": "x1", "run_id": "run-1", "step": "s", "argv_json": '["ls"]', "outcome": "ok", "exit_code": 0, "duration_ms": 12, "policy_snapshot_json": "{}", "output_digest": "abc", "created_at": "2026-01-02T03:04:05"},
                {"id": "x2", "run_id": "run-1", "step": "s", "argv_json": "[]", "outcome": "fail", "exit_code": 1, "duration_ms": 3, "policy_snapshot_json": None, "output_digest": None, "created_at": None},
            ],
        }  # fmt: skip
        assert rows_q.sql() == [
            "exec_runs.run_id = 'run-1'",
            "exec_runs.owner_id = 'user-1'",
        ]


# =========================================================================== share
class TestAssertShareOutputClean:
    @pytest.mark.parametrize(
        "output",
        [
            pytest.param("", id="empty"),
            pytest.param("```filename: src/app.py\nprint(1)\n```", id="normal-path"),
            pytest.param("```filename: myskills/x.md\nz", id="prefix-lookalike"),
            pytest.param(
                "```filename: src/.git/config\nz", id="nested-git-dir-not-prefix"
            ),
            pytest.param("```filename: sub/.gitignore2\nz", id="bare-name-lookalike"),
            pytest.param(
                "text ```filename: .chain/x.json\nz", id="fence-not-at-line-start"
            ),
        ],
    )
    # Plan #126 | B95,B96 | kills: over-broad matching
    def test_assert_share_output_clean_passes_when_no_reserved_path(self, output):
        assert _assert_share_output_clean(output, "run-1") is None

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(".chain/x.json", id="dir-prefix"),
            pytest.param("skills/a/b.md", id="skills-prefix"),
            pytest.param(".chain", id="dir-name-exact"),
            pytest.param(".git/config", id="git-dir"),
            pytest.param(".gitignore", id="bare-exact"),
            pytest.param("sub/.gitignore", id="bare-basename"),
        ],
    )
    # Plan #127 | B95,B96 | kills: remove a reserved match arm
    def test_assert_share_output_clean_raises_when_reserved_path_present(self, path):
        output = f"```filename: ok.txt\nx\n```\n```filename: {path}\nleak\n```"
        with pytest.raises(RuntimeError) as exc:
            _assert_share_output_clean(output, "run-9")
        message = str(exc.value)
        assert message.startswith(
            f"share guard: reserved path {path!r} found in deliverable output for run 'run-9'"
        )


def _patch_token(token: str = "TOKEN"):
    return patch(
        "app.api.runs.secrets.token_urlsafe", autospec=True, return_value=token
    )


class TestCreateOrRefreshShare:
    # Plan #128 | B94 | kills: mint for foreign run
    def test_create_share_returns_404_when_run_not_owned(self, make_client):
        resp = make_client(_db(_Q(first=None))).post("/api/runs/x/share")
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}

    @pytest.mark.parametrize("status", ["running", "failed", "cancelled"])
    # Plan #129 | B97 | kills: allow non-completed statuses
    def test_create_share_returns_400_when_run_not_completed(self, make_client, status):
        db = _db(_Q(first=_row(status=status)))
        resp = make_client(db).post("/api/runs/run-1/share")
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": {
                "code": "run_not_shareable",
                "message": "Only completed runs with a deliverable can be shared.",
            }
        }
        db.commit.assert_not_called()

    @pytest.mark.parametrize("output", ["", None])
    # Plan #130 | B98 | kills: share without deliverable
    def test_create_share_returns_400_when_no_deliverable(self, make_client, output):
        db = _db(_Q(first=_row(output=output)))
        resp = make_client(db).post("/api/runs/run-1/share")
        assert resp.status_code == 400
        assert resp.json() == {
            "detail": {
                "code": "no_deliverable",
                "message": "This run has no deliverable output to share.",
            }
        }
        db.commit.assert_not_called()

    # Plan #131 | B99 | kills: mint token despite reserved path / leak details
    def test_create_share_returns_generic_500_when_guard_detects_reserved_path(
        self, make_client, caplog
    ):
        run = _row(output="```filename: .chain/secret.json\nleak\n```")
        db = _db(_Q(first=run))
        with caplog.at_level(logging.ERROR, logger="app.api.runs"):
            resp = make_client(db).post("/api/runs/run-1/share")
        assert resp.status_code == 500
        assert resp.json() == {
            "detail": {
                "code": "share_guard_violation",
                "message": "Unable to create share link for this run.",
            }
        }
        assert run.share_token is None
        db.commit.assert_not_called()
        assert "refusing share token mint for run_id=run-1" in caplog.text

    @pytest.mark.parametrize("status", ["completed", "degraded"])
    # Plan #132 | B100 | kills: wrong ttl / url / not persisting / not committing
    def test_create_share_mints_token_and_persists_when_run_shareable(
        self, make_client, status
    ):
        run = _row(status=status, output="```filename: src/a.py\nx\n```")
        db = _db(_Q(first=run))
        with (
            _patch_token() as tok,
            patch("app.api.runs.datetime", _fixed_datetime(NOW)),
        ):
            resp = make_client(db).post("/api/runs/run-1/share")
        assert resp.status_code == 200
        assert resp.json() == {
            "share_token": "TOKEN",
            "share_url": "/s/TOKEN",
            "expires_at": "2026-01-31T12:00:00+00:00",
        }
        tok.assert_called_once_with(32)
        assert run.share_token == "TOKEN"
        assert run.share_expires_at == NOW + timedelta(days=30)
        db.commit.assert_called_once_with()


class TestRevokeShare:
    # Plan #133 | B94 | kills: revoke foreign run
    def test_revoke_share_returns_404_when_run_not_owned(self, make_client):
        resp = make_client(_db(_Q(first=None))).delete("/api/runs/x/share")
        assert resp.status_code == 404

    # Plan #134 | B101 | kills: forget to clear expiry / commit
    def test_revoke_share_clears_token_and_expiry_when_run_owned(self, make_client):
        run = _row(share_token="T", share_expires_at=NOW)
        db = _db(_Q(first=run))
        resp = make_client(db).delete("/api/runs/run-1/share")
        assert resp.status_code == 204
        assert resp.content == b""
        assert (run.share_token, run.share_expires_at) == (None, None)
        db.commit.assert_called_once_with()

    # Plan #135 | B101 | kills: 404/raise when nothing to revoke
    def test_revoke_share_is_noop_204_when_run_has_no_share(self, make_client):
        run = _row()
        resp = make_client(_db(_Q(first=run))).delete("/api/runs/run-1/share")
        assert resp.status_code == 204
        assert (run.share_token, run.share_expires_at) == (None, None)


class TestGetSharedRunByToken:
    def _call(self, run, token="tok"):
        q = _Q(first=run)
        with patch("app.api.runs.datetime", _fixed_datetime(NOW)):
            result = get_shared_run_by_token(token, _db(q))
        return result, q

    # Plan #136 | B102 | kills: raise / return something for unknown token
    def test_get_shared_run_by_token_returns_none_when_token_unknown(self):
        result, q = self._call(None, token="nope")
        assert result is None
        assert q.sql() == ["workflow_runs.share_token = 'nope'"]

    # Plan #137 | B103 | kills: require expiry
    def test_get_shared_run_by_token_returns_run_when_no_expiry(self):
        run = _row(share_expires_at=None, output="plain")
        assert self._call(run)[0] is run

    @pytest.mark.parametrize(
        ("expires", "served"),
        [
            pytest.param(NOW + timedelta(days=1), True, id="future"),
            pytest.param(NOW - timedelta(seconds=30), True, id="within-grace"),
            pytest.param(
                NOW - timedelta(seconds=60), True, id="exactly-grace-boundary"
            ),
            pytest.param(NOW - timedelta(seconds=61), False, id="just-expired"),
            pytest.param(
                datetime(2026, 1, 1, 11, 59, 30), True, id="naive-within-grace"
            ),
            pytest.param(datetime(2026, 1, 1, 11, 58, 0), False, id="naive-expired"),
        ],
    )
    # Plan #138 | B103 | kills: change grace window / `<` to `<=` / skip naive promotion
    def test_get_shared_run_by_token_applies_expiry_with_grace_window(
        self, expires, served
    ):
        run = _row(share_expires_at=expires, output="plain")
        result, _ = self._call(run)
        assert result is (run if served else None)

    # Plan #139 | B104 | kills: serve run with reserved path
    def test_get_shared_run_by_token_returns_none_when_output_has_reserved_path(
        self, caplog
    ):
        run = _row(share_expires_at=None, output="```filename: .git/config\nx\n```")
        with caplog.at_level(logging.ERROR, logger="app.api.runs"):
            result, _ = self._call(run)
        assert result is None
        assert "refusing share serve for run_id=run-1" in caplog.text

    @pytest.mark.parametrize("output", ["", None])
    # Plan #140 | B104 | kills: run the guard on empty output
    def test_get_shared_run_by_token_returns_run_when_output_empty(self, output):
        run = _row(share_expires_at=None, output=output)
        assert self._call(run)[0] is run


# =========================================================================== restore helpers
class TestValidateTagForRestore:
    # Plan #141 | B106 | kills: return a different tag
    def test_validate_tag_for_restore_returns_tag_when_in_visible_list(self):
        sandbox = MagicMock(spec=RunSandbox)
        sandbox.list_tags.return_value = ["v1", "v2"]
        assert _validate_tag_for_restore("v2", sandbox) == "v2"

    @pytest.mark.parametrize("tag", ["v3", "", "V1", "v1 "])
    # Plan #142 | B106 | kills: substring / case-insensitive matching
    def test_validate_tag_for_restore_raises_400_when_tag_not_exact_match(self, tag):
        sandbox = MagicMock(spec=RunSandbox)
        sandbox.list_tags.return_value = ["v1", "v2"]
        with pytest.raises(HTTPException) as exc:
            _validate_tag_for_restore(tag, sandbox)
        assert exc.value.status_code == 400
        assert exc.value.detail == {
            "code": "invalid_ref",
            "message": "Requested tag not found.",
        }

    # Plan #143 | B105 | kills: propagate list_tags error (fail-open)
    def test_validate_tag_for_restore_fails_closed_when_list_tags_raises(self):
        sandbox = MagicMock(spec=RunSandbox)
        sandbox.list_tags.side_effect = RuntimeError("git broke")
        with pytest.raises(HTTPException) as exc:
            _validate_tag_for_restore("v1", sandbox)
        assert exc.value.status_code == 400

    # Plan #144 | B105 | kills: require list_tags attribute
    def test_validate_tag_for_restore_raises_400_when_sandbox_has_no_list_tags(self):
        with pytest.raises(HTTPException) as exc:
            _validate_tag_for_restore("v1", SimpleNamespace())
        assert exc.value.status_code == 400


class TestHasActiveFamilyMember:
    @pytest.mark.parametrize("active", [True, False])
    # Plan #145 | B107 | kills: swap argument order / invert result
    def test_has_active_family_member_delegates_to_run_commands(self, active):
        db = MagicMock(spec=Session)
        with patch(
            "app.api.run_commands._has_active_chain_revision",
            autospec=True,
            return_value=active,
        ) as m:
            assert _has_active_family_member(db, "root-1", "user-1") is active
        m.assert_called_once_with(db, "root-1", "user-1")


# =========================================================================== restore endpoint
BODY = {"tag": "v1", "idempotency_key": "k1"}


@pytest.fixture
def restore_env():
    """Patch every collaborator of ``restore_version`` where it is looked up."""
    with contextlib.ExitStack() as stack:
        env = SimpleNamespace()
        # Our restore refuses an expired run dir via run_dir_expired (404 "Sandbox not
        # found", ISS-1072). Here it follows the mocked root's is_dir(), so a test can
        # still flip the directory to missing.
        stack.enter_context(
            patch(
                "app.api.runs.run_dir_expired",
                autospec=True,
                side_effect=lambda root: not root.is_dir(),
            )
        )
        env.lookup = stack.enter_context(
            patch(
                "app.api.runs.lookup_idempotent_restore",
                autospec=True,
                return_value=None,
            )
        )
        env.resolve = stack.enter_context(
            patch(
                "app.api.runs.resolve_revision_root",
                autospec=True,
                return_value=RevisionRootResolved(root_id="root-1"),
            )
        )
        env.sandbox_cls = stack.enter_context(
            patch("app.api.runs.RunSandbox", autospec=True)
        )
        env.lock = stack.enter_context(
            patch(
                "app.api.runs.family_lock",
                autospec=True,
                side_effect=lambda *a, **k: contextlib.nullcontext(),
            )
        )
        env.active = stack.enter_context(
            patch(
                "app.api.runs._has_active_family_member",
                autospec=True,
                return_value=False,
            )
        )
        env.commit = stack.enter_context(
            patch(
                "agents.execution_engine.engine.commit_in_sandbox",
                autospec=True,
                return_value=CommitInSandboxResult(sha="abc123"),
            )
        )
        stack.enter_context(
            patch("app.api.runs.settings", SimpleNamespace(RUNS_ROOT="/runs-root"))
        )
        sb = env.sandbox_cls.return_value
        sb.root = MagicMock(spec=Path)
        sb.root.is_dir.return_value = True
        sb.list_tags.return_value = ["v1", "v2"]
        sb.detect_persistent_git_state.return_value = {"state": "clean"}
        sb.materialize_tree_at_ref.return_value = SimpleNamespace(status="materialized")
        env.sandbox = sb
        yield env


def _restore(make_client, run=None, body=BODY, db=None):
    db = db or _db(_Q(first=run if run is not None else _row()))
    return make_client(db).post("/api/runs/run-1/restore", json=body), db


def _detail(resp) -> dict:
    return resp.json()["detail"]


class TestRestoreVersion:
    # Plan #146 | B108 | kills: wrong sandbox args / commit args / audit row / lock key
    def test_restore_version_commits_and_records_audit_when_materialized(
        self, make_client, restore_env
    ):
        resp, db = _restore(make_client)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": "abc123",
            "outcome": "committed",
        }
        restore_env.lookup.assert_called_once_with(db, "user-1", "k1")
        restore_env.sandbox_cls.assert_called_once_with(
            "user-1", "root-1", current_run_id="run-1", runs_root="/runs-root"
        )
        restore_env.lock.assert_called_once_with("user-1", "root-1")
        restore_env.active.assert_called_once_with(db, "root-1", "user-1")
        restore_env.sandbox.materialize_tree_at_ref.assert_called_once_with("v1")
        restore_env.commit.assert_awaited_once_with(
            restore_env.sandbox,
            "restore: run-1 to v1",
            SimpleNamespace(
                run_id="run-1", owner_id="user-1", user_id="user-1", workspace_id="ws-1",
                runner=None, final_status=None, deliverable=None, last_commit_blocked=False,
            ),
            SimpleNamespace(agent_id="restore", hooks=[], tools=None),
            audit_operation="restore",
            audit_detail={"tag_name": "v1", "idempotency_key": "k1"},
            registry=None,
        )  # fmt: skip
        audit = db.add.call_args.args[0]
        assert (audit.owner_id, audit.workspace_id, audit.run_id, audit.operation) == (
            "user-1",
            "ws-1",
            "run-1",
            "restore",
        )
        assert (audit.source_ref, audit.idempotency_key, audit.commit_sha) == (
            "v1",
            "k1",
            "abc123",
        )
        assert (audit.tag_name, audit.outcome) == ("v1", "committed")
        db.commit.assert_called_once_with()

    # Plan #147 | B108 | kills: 404 vs 200 for cross-owner run; lookup before owner gate
    def test_restore_version_returns_404_when_run_not_owned(
        self, make_client, restore_env
    ):
        resp, _ = _restore(make_client, db=_db(_Q(first=None)))
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}
        restore_env.lookup.assert_not_called()

    @pytest.mark.parametrize(
        ("prior", "tag", "outcome"),
        [
            pytest.param(
                {"tag_name": "v9", "commit_id": "c9", "outcome": "no_change"},
                "v9",
                "no_change",
                id="stored-values",
            ),
            pytest.param(
                {"tag_name": None, "commit_id": None, "outcome": None},
                "v1",
                "committed",
                id="defaults-when-none",
            ),
        ],
    )
    # Plan #148 | B109 | kills: skip idempotent short-circuit / wrong defaults
    def test_restore_version_returns_cached_result_when_idempotency_key_seen(
        self, make_client, restore_env, prior, tag, outcome
    ):
        restore_env.lookup.return_value = prior
        resp, _ = _restore(make_client)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": tag,
            "commit_id": prior["commit_id"],
            "outcome": outcome,
        }
        restore_env.resolve.assert_not_called()
        restore_env.sandbox_cls.assert_not_called()

    # Plan #149 | B110 | kills: proceed when root unresolved / leak reason
    def test_restore_version_returns_404_and_logs_when_revision_root_unresolved(
        self, make_client, restore_env, caplog
    ):
        restore_env.resolve.return_value = RevisionRootUnresolved(
            reason="cycle", run_id="run-1", visited_count=2, repeated_node="n1"
        )
        with caplog.at_level(logging.WARNING, logger="app.api.runs"):
            resp, _ = _restore(make_client)
        assert resp.status_code == 404
        assert resp.json() == {"detail": NOT_FOUND}
        restore_env.sandbox_cls.assert_not_called()
        assert (
            "restore: revision root unresolved run=run-1 reason=cycle visited=2 repeated=n1"
            in caplog.text
        )

    # Plan #150 | B111 | kills: skip sandbox dir check
    def test_restore_version_returns_404_when_sandbox_directory_missing(
        self, make_client, restore_env
    ):
        restore_env.sandbox.root.is_dir.return_value = False
        resp, _ = _restore(make_client)
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Sandbox not found"}
        restore_env.sandbox.list_tags.assert_not_called()

    # Plan #151 | B112 | kills: pass unvalidated tag through to git
    def test_restore_version_returns_400_when_tag_not_visible(
        self, make_client, restore_env
    ):
        resp, _ = _restore(make_client, body={"tag": "v9", "idempotency_key": "k1"})
        assert resp.status_code == 400
        assert _detail(resp) == {
            "code": "invalid_ref",
            "message": "Requested tag not found.",
        }
        restore_env.lock.assert_not_called()
        restore_env.sandbox.materialize_tree_at_ref.assert_not_called()

    # Plan #152 | B113 | kills: use None instead of "" for missing workspace
    def test_restore_version_uses_empty_workspace_when_run_has_none(
        self, make_client, restore_env
    ):
        resp, db = _restore(make_client, run=_row(workspace_id=None))
        assert resp.status_code == 200
        assert restore_env.commit.await_args.args[2].workspace_id == ""
        assert db.add.call_args.args[0].workspace_id == ""

    # Plan #153 | B114 | kills: ignore the active-family guard
    def test_restore_version_returns_409_when_family_has_active_run(
        self, make_client, restore_env
    ):
        restore_env.active.return_value = True
        resp, db = _restore(make_client)
        assert resp.status_code == 409
        assert _detail(resp) == {
            "code": "family_run_active",
            "message": "Cannot restore while a run in this family is active. Try again once all runs have completed.",
        }
        restore_env.sandbox.materialize_tree_at_ref.assert_not_called()
        restore_env.commit.assert_not_awaited()
        db.add.assert_not_called()

    # Plan #154 | B115 | kills: skip reconcile when state not clean
    def test_restore_version_reconciles_when_git_state_not_clean(
        self, make_client, restore_env, caplog
    ):
        state = {"state": "merge_head"}
        restore_env.sandbox.detect_persistent_git_state.return_value = state
        restore_env.sandbox.reconcile_persistent_git_state.return_value = "reconciled"
        with caplog.at_level(logging.INFO, logger="app.api.runs"):
            resp, _ = _restore(make_client)
        assert resp.status_code == 200
        restore_env.sandbox.reconcile_persistent_git_state.assert_called_once_with(
            state
        )
        assert (
            "restore: git state reconciled run=run-1 outcome=reconciled" in caplog.text
        )

    # Plan #155 | B115 | kills: reconcile for clean state
    def test_restore_version_skips_reconcile_when_git_state_clean(
        self, make_client, restore_env
    ):
        _restore(make_client)
        restore_env.sandbox.reconcile_persistent_git_state.assert_not_called()

    # Plan #156 | B115 | kills: default missing "state" to non-clean
    def test_restore_version_treats_missing_state_key_as_clean(
        self, make_client, restore_env
    ):
        restore_env.sandbox.detect_persistent_git_state.return_value = {}
        resp, _ = _restore(make_client)
        assert resp.status_code == 200
        restore_env.sandbox.reconcile_persistent_git_state.assert_not_called()

    # Plan #157 | B116 | kills: continue after reconcile_failed
    def test_restore_version_returns_409_when_reconcile_failed(
        self, make_client, restore_env
    ):
        restore_env.sandbox.detect_persistent_git_state.return_value = {
            "state": "stale_lock"
        }
        restore_env.sandbox.reconcile_persistent_git_state.return_value = (
            "reconcile_failed"
        )
        resp, _ = _restore(make_client)
        assert resp.status_code == 409
        assert _detail(resp) == {
            "code": "git_state_reconcile_failed",
            "message": "The sandbox has unrecoverable git state from a prior crash. Operator intervention required.",
        }
        restore_env.sandbox.materialize_tree_at_ref.assert_not_called()

    # Plan #158 | B117 | kills: swallow AttributeError / wrong status
    def test_restore_version_returns_501_when_materialize_not_available(
        self, make_client, restore_env
    ):
        restore_env.sandbox.materialize_tree_at_ref.side_effect = AttributeError(
            "missing"
        )
        resp, _ = _restore(make_client)
        assert resp.status_code == 501
        assert _detail(resp) == {
            "code": "not_implemented",
            "message": "materialize_tree_at_ref is not available (task 8.3).",
        }

    # Plan #159 | B118 | kills: leak git error text / treat as no-op
    def test_restore_version_returns_generic_500_when_materialize_git_fails(
        self, make_client, restore_env
    ):
        restore_env.sandbox.materialize_tree_at_ref.side_effect = GitCommandError(
            ["git", "checkout"], 128, "fatal: /secret/path"
        )
        resp, db = _restore(make_client)
        assert resp.status_code == 500
        assert _detail(resp) == {
            "code": "restore_materialize_failed",
            "message": "Failed to materialize the requested version.",
        }
        assert "/secret/path" not in resp.text
        db.add.assert_not_called()

    # Plan #160 | B119 | kills: commit on no_change / drop audit row
    def test_restore_version_reports_no_change_without_commit_when_tree_already_at_tag(
        self, make_client, restore_env
    ):
        restore_env.sandbox.materialize_tree_at_ref.return_value = SimpleNamespace(
            status="no_change"
        )
        resp, db = _restore(make_client)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": None,
            "outcome": "no_change",
        }
        restore_env.commit.assert_not_awaited()
        audit = db.add.call_args.args[0]
        assert (audit.commit_sha, audit.outcome) == (None, "no_change")

    @pytest.mark.parametrize(
        "result",
        [
            pytest.param(SimpleNamespace(status="error"), id="error-status"),
            pytest.param(SimpleNamespace(status="weird"), id="unknown-status"),
            pytest.param(object(), id="no-status-attribute"),
        ],
    )
    # Plan #161 | B120 | kills: commit on unexpected materialize status
    def test_restore_version_returns_500_when_materialize_status_unexpected(
        self, make_client, restore_env, result
    ):
        restore_env.sandbox.materialize_tree_at_ref.return_value = result
        resp, db = _restore(make_client)
        assert resp.status_code == 500
        assert _detail(resp)["code"] == "restore_materialize_failed"
        restore_env.commit.assert_not_awaited()
        db.add.assert_not_called()

    # Plan #162 | B121 | kills: write idempotency key for blocked restore
    def test_restore_version_returns_blocked_without_audit_when_commit_blocked(
        self, make_client, restore_env, caplog
    ):
        restore_env.commit.return_value = CommitInSandboxResult(
            blocked=True, block_reason="secret_detected"
        )
        with caplog.at_level(logging.WARNING, logger="app.api.runs"):
            resp, db = _restore(make_client)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": None,
            "outcome": "blocked",
        }
        db.add.assert_not_called()
        db.commit.assert_not_called()
        assert (
            "restore: commit BLOCKED by scan run=run-1 tag=v1 reason=secret_detected"
            in caplog.text
        )

    # Plan #163 | B122 | kills: report committed when nothing staged
    def test_restore_version_reports_no_change_when_commit_has_nothing_staged(
        self, make_client, restore_env
    ):
        restore_env.commit.return_value = CommitInSandboxResult(no_change=True)
        resp, db = _restore(make_client)
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": None,
            "outcome": "no_change",
        }
        assert db.add.call_args.args[0].outcome == "no_change"

    # Plan #164 | B123 | kills: return "" instead of None for empty sha
    def test_restore_version_returns_null_commit_id_when_sha_empty(
        self, make_client, restore_env
    ):
        restore_env.commit.return_value = CommitInSandboxResult(sha="")
        resp, _ = _restore(make_client)
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": None,
            "outcome": "committed",
        }

    # Plan #165 | B124 | kills: not rolling back / ignoring stored winner
    def test_restore_version_returns_stored_result_when_idempotency_collision(
        self, make_client, restore_env, caplog
    ):
        restore_env.lookup.side_effect = [
            None,
            {"tag_name": "v2", "commit_id": "winner", "outcome": "committed"},
        ]
        db = _db(_Q(first=_row()))
        db.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        with caplog.at_level(logging.INFO, logger="app.api.runs"):
            resp, _ = _restore(make_client, db=db)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v2",
            "commit_id": "winner",
            "outcome": "committed",
        }
        db.rollback.assert_called_once_with()
        assert restore_env.lookup.call_count == 2
        assert "restore: idempotency collision on key=k1 run=run-1" in caplog.text

    # Plan #166 | B124 | kills: wrong fallbacks for None stored fields
    def test_restore_version_falls_back_to_local_values_when_stored_fields_none(
        self, make_client, restore_env
    ):
        restore_env.lookup.side_effect = [
            None,
            {"tag_name": None, "commit_id": "winner", "outcome": None},
        ]
        db = _db(_Q(first=_row()))
        db.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        resp, _ = _restore(make_client, db=db)
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": "winner",
            "outcome": "committed",
        }

    # Plan #167 | B125 | kills: 500 when the follow-up read finds nothing
    def test_restore_version_returns_in_memory_result_when_collision_lookup_empty(
        self, make_client, restore_env
    ):
        restore_env.lookup.side_effect = [None, None]
        db = _db(_Q(first=_row()))
        db.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        resp, _ = _restore(make_client, db=db)
        assert resp.status_code == 200
        assert resp.json() == {
            "run_id": "run-1",
            "tag": "v1",
            "commit_id": "abc123",
            "outcome": "committed",
        }
        db.rollback.assert_called_once_with()

    # Plan #168 | B126 | kills: wrong status/code or leaking lock key
    def test_restore_version_returns_503_when_family_lock_times_out(
        self, make_client, restore_env, caplog
    ):
        restore_env.lock.side_effect = FamilyLockTimeout("user-1", "root-1", 5.0)
        with caplog.at_level(logging.WARNING, logger="app.api.runs"):
            resp, _ = _restore(make_client)
        assert resp.status_code == 503
        assert _detail(resp) == {
            "code": "family_lock_timeout",
            "message": "Could not acquire the family lock. Another operation is in progress — try again shortly.",
        }
        assert "root-1" not in resp.text
        assert (
            "restore: family lock timeout run=run-1 revision_root=root-1" in caplog.text
        )

    # Plan #169 | B127 | kills: leak exception text / let it escape
    def test_restore_version_returns_generic_500_when_unexpected_error(
        self, make_client, restore_env
    ):
        restore_env.active.side_effect = RuntimeError("db password=hunter2")
        resp, _ = _restore(make_client)
        assert resp.status_code == 500
        assert _detail(resp) == {
            "code": "restore_failed",
            "message": "Restore failed unexpectedly.",
        }
        assert "hunter2" not in resp.text

    @pytest.mark.parametrize(
        ("body", "loc", "err_type"),
        [
            pytest.param(
                {"idempotency_key": "k"}, ["body", "tag"], "missing", id="tag-missing"
            ),
            pytest.param(
                {"tag": "v1"}, ["body", "idempotency_key"], "missing", id="key-missing"
            ),
            pytest.param(
                {"tag": "t" * 129, "idempotency_key": "k"},
                ["body", "tag"],
                "string_too_long",
                id="tag-too-long",
            ),
            pytest.param(
                {"tag": "v1", "idempotency_key": "k" * 257},
                ["body", "idempotency_key"],
                "string_too_long",
                id="key-too-long",
            ),
        ],
    )
    # Plan #170 | B108 | kills: loosen RestoreRequest validation
    def test_restore_version_returns_422_when_body_invalid(
        self, make_client, restore_env, body, loc, err_type
    ):
        resp, _ = _restore(make_client, body=body, db=_db())
        assert resp.status_code == 422
        assert resp.json()["detail"][0]["loc"] == loc
        assert resp.json()["detail"][0]["type"] == err_type
        restore_env.lookup.assert_not_called()
