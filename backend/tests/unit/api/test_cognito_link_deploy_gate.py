"""The pre-migration Cognito-link deploy gate, and the wiring that enforces it.

WHY THIS EXISTS
---------------
Migrations are not a deploy step. ``backend/docker-entrypoint.sh`` runs
``alembic upgrade head`` under ``set -eu`` before ``exec uvicorn``, so a
migration that refuses to apply never surfaces as a failed step — the
container exits, ``restart: unless-stopped`` loops it, ``:8000`` is never
bound, and ``remote-deploy.sh``'s health gate burns five minutes before
rolling the images back. Migration 0038 has exactly that shape: it aborts
when a ``users`` row is not cleanly Cognito-linked.

``--report --fail-on-unlinked`` converts that into a fast, legible deploy
failure. Its EXIT CODE is the whole contract, so it is pinned here in both
directions, along with the three things that make it reachable in production:
the script being baked into the image, the entrypoint being bypassed, and the
gate running before ``up -d``.

Zero real I/O: the database handle, the inspector and the row query are all
substituted, so no ``users`` table (and no Cognito pool) is required.
"""

from __future__ import annotations

import contextlib
import importlib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[4]
_DEPLOY_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "remote-deploy.sh"
_BACKEND_DOCKERFILE = _REPO_ROOT / "backend" / "Dockerfile"

_MODULE = "scripts.migrate_local_users_to_cognito"

_UNLINKED_ROW = {
    "id": "11111111-2222-3333-4444-555555555555",
    "email": "stale@example.com",
    "tier": "basic",
    "is_admin": False,
    "cognito_sub": None,
    "auth_provider": "local",
}


@pytest.fixture
def script():
    return importlib.import_module(_MODULE)


def _stub_db(monkeypatch, script, *, tables: list[str], rows: list[dict]) -> None:
    """Point the script at an in-memory stand-in for the database.

    ``cmd_report`` only reflects table names and reads rows, so replacing the
    engine, ``sa.inspect`` and ``_unlinked_rows`` covers every access it makes.
    """
    engine = type(
        "Engine", (), {"connect": lambda self: contextlib.nullcontext(object())}
    )()
    inspector = type("Inspector", (), {"get_table_names": lambda self: tables})()

    monkeypatch.setattr(script, "engine", engine)
    monkeypatch.setattr(script.sa, "inspect", lambda _conn: inspector)
    monkeypatch.setattr(script, "_legacy_columns", lambda _conn: {"auth_provider"})
    monkeypatch.setattr(script, "_unlinked_rows", lambda _conn, _cols: rows)


class TestGateExitCode:
    def test_cmd_report_exits_ok_when_users_table_absent(self, script, monkeypatch):
        """A first-ever deploy has no schema yet.

        The gate runs BEFORE migrations create ``users``, so an absent table is
        a fresh install, not a failure. Getting this wrong makes the gate block
        every new environment from ever bootstrapping.
        """
        _stub_db(monkeypatch, script, tables=[], rows=[_UNLINKED_ROW])

        assert script.cmd_report(fail_on_unlinked=True) == script.EXIT_OK

    def test_cmd_report_exits_ok_when_all_rows_linked_and_gate_enabled(
        self, script, monkeypatch
    ):
        """The pass case: nothing needs attention, so the deploy proceeds."""
        _stub_db(monkeypatch, script, tables=["users"], rows=[])

        assert script.cmd_report(fail_on_unlinked=True) == script.EXIT_OK

    def test_cmd_report_exits_failed_when_rows_unlinked_and_gate_enabled(
        self, script, monkeypatch
    ):
        """The gate's reason for existing."""
        _stub_db(monkeypatch, script, tables=["users"], rows=[_UNLINKED_ROW])

        assert script.cmd_report(fail_on_unlinked=True) == script.EXIT_FAILED

    def test_cmd_report_exits_ok_when_rows_unlinked_and_gate_disabled(
        self, script, monkeypatch
    ):
        """Bare ``--report`` stays advisory.

        Operators run it interactively to decide what to do next; it must not
        start failing just because a gating mode was added alongside it.
        """
        _stub_db(monkeypatch, script, tables=["users"], rows=[_UNLINKED_ROW])

        assert script.cmd_report(fail_on_unlinked=False) == script.EXIT_OK

    def test_cmd_report_names_the_offending_row_when_gate_fails(
        self, script, monkeypatch, capsys
    ):
        """A gate that fails without naming the row sends the operator hunting."""
        _stub_db(monkeypatch, script, tables=["users"], rows=[_UNLINKED_ROW])

        script.cmd_report(fail_on_unlinked=True)

        captured = capsys.readouterr()
        assert _UNLINKED_ROW["email"] in captured.out
        assert "0038" in captured.err


class TestLinkWritesBothColumns:
    """0038's pre-flight rejects a non-'cognito' ``auth_provider`` just as
    firmly as a NULL ``cognito_sub``. Writing only the sub produced a row that
    ``--report`` still flagged and 0038 still refused, with no verb able to
    resolve it — so both columns are pinned here."""

    def test_write_link_sets_auth_provider_when_column_present(
        self, script, monkeypatch
    ):
        statements: list[str] = []
        monkeypatch.setattr(
            script, "engine", _capturing_engine(statements)
        )

        script._write_link("row-id", "sub-value", {"cognito_sub", "auth_provider"})

        assert len(statements) == 1
        assert "cognito_sub = :sub" in statements[0]
        assert "auth_provider = 'cognito'" in statements[0]

    def test_write_link_omits_auth_provider_when_column_already_dropped(
        self, script, monkeypatch
    ):
        """Post-0038 the column is gone; naming it would raise."""
        statements: list[str] = []
        monkeypatch.setattr(
            script, "engine", _capturing_engine(statements)
        )

        script._write_link("row-id", "sub-value", {"cognito_sub"})

        assert len(statements) == 1
        assert "cognito_sub = :sub" in statements[0]
        assert "auth_provider" not in statements[0]


def _capturing_engine(statements: list[str]):
    """An engine whose ``begin()`` records the SQL text instead of running it."""

    class _Conn:
        def execute(self, clause, _params=None):
            statements.append(str(clause))

    class _Engine:
        def begin(self):
            return contextlib.nullcontext(_Conn())

    return _Engine()


class TestDeployWiring:
    """The gate only protects production if the deploy actually runs it, in the
    right place, without the entrypoint that would defeat it. Each assertion
    below corresponds to a way this has to be wired to work at all."""

    @pytest.fixture
    def deploy_script(self) -> str:
        assert _DEPLOY_SCRIPT.exists(), f"missing {_DEPLOY_SCRIPT}"
        return _DEPLOY_SCRIPT.read_text(encoding="utf-8")

    def test_deploy_runs_the_gate_with_fail_on_unlinked(self, deploy_script):
        """Without the flag the report exits 0 and gates nothing."""
        assert "migrate_local_users_to_cognito.py --report --fail-on-unlinked" in (
            deploy_script
        )

    def test_deploy_gate_overrides_the_container_entrypoint(self, deploy_script):
        """``docker-entrypoint.sh`` runs ``alembic upgrade head``.

        Without ``--entrypoint python`` the gate command would itself perform
        the migration it exists to prevent.
        """
        gate_line = _gate_invocation(deploy_script)
        assert "--entrypoint python" in gate_line
        assert "--rm" in gate_line
        assert "--no-deps" in gate_line

    def test_deploy_gate_runs_before_the_stack_is_recreated(self, deploy_script):
        """Ordering IS the feature: after ``pull`` (the image must be local) and
        before ``up -d`` (a failure must leave the healthy stack serving)."""
        pull = deploy_script.index("docker-compose.prod.yml pull")
        gate = deploy_script.index("--report --fail-on-unlinked")
        up = deploy_script.index("up -d --remove-orphans")

        assert pull < gate < up

    def test_deploy_gate_failure_aborts_the_deploy(self, deploy_script):
        """A gate whose failure is not fatal is decoration."""
        _, _, after_gate = deploy_script.partition("--report --fail-on-unlinked")
        before_up, _, _ = after_gate.partition("up -d --remove-orphans")

        assert "exit 1" in before_up

    def test_gate_script_is_baked_into_the_backend_image(self):
        """The gate runs inside the new image, so the script has to be in it.

        The Dockerfile copies individual scripts rather than the whole tree, so
        this file is easy to leave behind — and the omission would only show up
        as a failing deploy.

        Matches a real ``COPY`` INSTRUCTION, not merely the path appearing
        somewhere in the file: the surrounding comment names the script too, so
        a substring check passes even with the COPY deleted (confirmed by
        deleting it).
        """
        dockerfile = _BACKEND_DOCKERFILE.read_text(encoding="utf-8")

        copy_lines = [
            line
            for line in dockerfile.splitlines()
            if line.startswith("COPY")
            and "scripts/migrate_local_users_to_cognito.py" in line
        ]

        assert copy_lines, (
            "backend/Dockerfile must COPY scripts/migrate_local_users_to_cognito.py "
            "— remote-deploy.sh runs it inside this image as a pre-migration gate."
        )


def _gate_invocation(deploy_script: str) -> str:
    """The full (line-continued) shell command that runs the gate."""
    start = deploy_script.index("run --rm --no-deps --entrypoint python backend")
    end = deploy_script.index("--report --fail-on-unlinked", start)
    return deploy_script[start - 200 : end]
