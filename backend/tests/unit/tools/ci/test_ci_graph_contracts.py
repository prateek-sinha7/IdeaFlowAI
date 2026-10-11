"""
Graph contracts for ci.yml's FEAT-004 wiring (F-12, F-15, F-16, F-19).

These parse the committed workflow, config and compose files and assert the
structural properties the aggregate gate depends on:

* the `changes` job (F-15): dorny/paths-filter pinned to a commit, PR-only, the
  filter keys agree with tools/ci/change_scope.py, and the heavy jobs read the
  area outputs while repo-static stays ungated;
* ci-evidence hears from every registry owner job and from `changes`, and passes
  the path filter only when `changes` succeeded;
* deploy.yml's `gate` grants every permission any ci.yml job requests (a
  reusable workflow cannot ask for more, and the shortfall is a startup failure
  that kills every deploy);
* frontend-build -> frontend-e2e hand the standalone bundle over by artifact and
  E2E serves it with PLAYWRIGHT_WEB_SERVER=standalone (F-12);
* compose validation (F-19) is a registered check with a placeholder-only env;
* the misleading container-scan sentence (F-16) is gone.

Running dorny, the dynamic matrices, docker compose, actionlint and the
standalone server is CI-only; these tests pin the configuration that drives them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.ci.change_scope import FILTER_NAMES
from tools.ci.signal_registry import SIGNAL_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
CI_YML = WORKFLOWS_DIR / "ci.yml"
DEPLOY_YML = WORKFLOWS_DIR / "deploy.yml"
CI_DIR = REPO_ROOT / "ci"
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "docker-compose.prod.yml",
)
COMPOSE_ENV = CI_DIR / "compose-ci.env"
PLAYWRIGHT_CONFIG = REPO_ROOT / "frontend" / "playwright.config.ts"

DORNY_PIN = "dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d"

#: area output -> the jobs ci.yml gates on it with a plain `if:`.
AREA_GATED_JOBS = {
    "backend": (
        "backend-inventory",
        "backend-static",
        "backend-offline",
        "backend-postgres",
    ),
    "frontend": (
        "frontend-build",
        "frontend-static",
        "frontend-vitest",
        "frontend-e2e",
    ),
}
#: Evidence jobs keep `always()` so a failed producer still gets a verdict.
EVIDENCE_JOBS = {"backend": "backend-evidence", "frontend": "frontend-evidence"}

_PERMISSION_LEVELS = {"none": 0, "read": 1, "write": 2}


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ci() -> dict[str, Any]:
    return _load(CI_YML)


@pytest.fixture(scope="module")
def jobs(ci: dict[str, Any]) -> dict[str, Any]:
    return ci["jobs"]


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _step(job: dict[str, Any], *, step_id: str | None = None, name: str = "") -> dict:
    matches = [
        s
        for s in job.get("steps") or []
        if (step_id is not None and s.get("id") == step_id)
        or (name and str(s.get("name", "")).startswith(name))
    ]
    assert len(matches) == 1, f"expected one step id={step_id!r} name={name!r}"
    return matches[0]


def _owner_jobs() -> set[str]:
    aggregate = SIGNAL_REGISTRY["ci-required"].aggregate_members or []
    return {SIGNAL_REGISTRY[name].owner_job for name in aggregate}


# ----------------------------------------------------------------------
# The `changes` job (F-15)
# ----------------------------------------------------------------------


class TestChangesJob:
    def test_changes_pins_dorny_to_a_commit_when_workflow_loads(self, jobs):
        filter_step = _step(jobs["changes"], step_id="filter")
        assert filter_step["uses"] == DORNY_PIN
        assert re.search(
            re.escape(DORNY_PIN) + r"\s*#\s*v4\.0\.3\b",
            CI_YML.read_text(encoding="utf-8"),
        ), "the dorny pin must carry its `# v4.0.3` version comment"

    def test_changes_filter_step_runs_only_when_event_is_pull_request(self, jobs):
        filter_step = _step(jobs["changes"], step_id="filter")
        assert filter_step["if"].replace('"', "'") == (
            "github.event_name == 'pull_request'"
        )
        assert filter_step["with"]["predicate-quantifier"] == "some-with-excludes"

    def test_changes_filters_match_change_scope_names_when_parsed(self, jobs):
        changes = jobs["changes"]
        filters = yaml.safe_load(_step(changes, step_id="filter")["with"]["filters"])
        assert tuple(filters) == FILTER_NAMES
        assert {".github/**", "ci/**"} <= set(filters["workflows"])

        scope = _step(changes, step_id="scope")
        assert scope["run"].strip() == "python3 backend/tools/ci/change_scope.py"
        env = scope["env"]
        assert env["EVENT_NAME"] == "${{ github.event_name }}"
        for name in FILTER_NAMES:
            assert env[f"F_{name.upper()}"] == (
                f"${{{{ steps.filter.outputs.{name} }}}}"
            )

    def test_changes_workflows_filter_covers_shared_ci_tooling_when_parsed(self, jobs):
        # frontend-static, frontend-evidence, security[iac] and
        # container-scan[frontend] execute backend/tools/ci code and install the
        # ci-tools group from backend/uv.lock. Those paths are outside the
        # frontend/infra areas, so they must force a full run or a PR changing
        # only them would FILTER the jobs that run the changed code.
        filters = yaml.safe_load(
            _step(jobs["changes"], step_id="filter")["with"]["filters"]
        )
        assert {
            "backend/tools/__init__.py",
            "backend/tools/ci/**",
            "backend/uv.lock",
            "backend/pyproject.toml",
        } <= set(filters["workflows"])

    def test_changes_backend_filter_excludes_only_inert_paths_when_parsed(self, jobs):
        filters = yaml.safe_load(
            _step(jobs["changes"], step_id="filter")["with"]["filters"]
        )
        assert filters["backend"][0] == "**"
        assert sorted(filters["backend"][1:]) == sorted(
            ["!docs/**", "!.knowledge/**", "!unit-test-prompt/**", "!*.md"]
        )

    def test_changes_checkout_is_sparse_and_credential_free_when_configured(self, jobs):
        checkout = jobs["changes"]["steps"][0]
        assert str(checkout["uses"]).startswith("actions/checkout@")
        options = checkout["with"]
        assert options["persist-credentials"] is False
        assert options["sparse-checkout"].split() == [
            "backend/tools/ci/change_scope.py"
        ]
        assert options["sparse-checkout-cone-mode"] is False

    def test_changes_requests_only_read_scopes_when_listing_pr_files(self, jobs):
        assert jobs["changes"]["permissions"] == {
            "contents": "read",
            "pull-requests": "read",
        }

    def test_changes_exposes_every_scope_output_when_declared(self, jobs):
        outputs = jobs["changes"]["outputs"]
        expected = {
            "backend",
            "frontend",
            "infra",
            "docker",
            "workflows",
            "backend_image",
            "frontend_image",
            "security_legs",
            "container_components",
            "filtered_areas",
        }
        assert set(outputs) == expected
        for key, value in outputs.items():
            assert value == f"${{{{ steps.scope.outputs.{key} }}}}"


class TestGating:
    @pytest.mark.parametrize(
        ("area", "job_name"),
        [(a, j) for a, names in AREA_GATED_JOBS.items() for j in names],
    )
    def test_heavy_job_reads_its_area_output_when_gated(self, jobs, area, job_name):
        job = jobs[job_name]
        assert "changes" in _needs(job)
        assert job["if"] == f"needs.changes.outputs.{area} == 'true'"

    @pytest.mark.parametrize(("area", "job_name"), sorted(EVIDENCE_JOBS.items()))
    def test_evidence_job_keeps_always_when_gated(self, jobs, area, job_name):
        job = jobs[job_name]
        assert "changes" in _needs(job)
        assert job["if"] == f"always() && needs.changes.outputs.{area} == 'true'"

    def test_repo_static_is_ungated_when_workflow_loads(self, jobs):
        job = jobs["repo-static"]
        assert "if" not in job
        assert "changes" not in _needs(job)

    def test_security_matrix_comes_from_security_legs_when_gated(self, jobs):
        job = jobs["security"]
        assert "changes" in _needs(job)
        assert "if" not in job, "secrets must always run, so security is never skipped"
        assert job["strategy"]["matrix"]["leg"] == (
            "${{ fromJSON(needs.changes.outputs.security_legs) }}"
        )

    def test_container_scan_matrix_comes_from_components_when_gated(self, jobs):
        job = jobs["container-scan"]
        assert "changes" in _needs(job)
        assert job["if"] == "needs.changes.outputs.container_components != '[]'"
        assert job["strategy"]["matrix"]["component"] == (
            "${{ fromJSON(needs.changes.outputs.container_components) }}"
        )


# ----------------------------------------------------------------------
# ci-evidence
# ----------------------------------------------------------------------


class TestCiEvidence:
    def test_ci_evidence_needs_every_owner_job_when_aggregating(self, jobs):
        needs = set(_needs(jobs["ci-evidence"]))
        owners = _owner_jobs() - {"ci-evidence"}
        assert owners | {"changes"} <= needs

    def test_ci_evidence_passes_job_arg_for_every_owner_when_aggregating(self, jobs):
        run = _step(jobs["ci-evidence"], step_id="aggregate")["run"]
        passed = set(re.findall(r'--job "([a-z0-9-]+)=', run))
        assert passed == _owner_jobs() - {"ci-evidence"}

    def test_ci_evidence_filters_only_when_changes_succeeded(self, jobs):
        step = _step(jobs["ci-evidence"], step_id="aggregate")
        env = step["env"]
        assert env["EVENT_NAME"] == "${{ github.event_name }}"
        assert env["CHANGES_RESULT"] == "${{ needs.changes.result }}"
        assert env["FILTERED_AREAS"] == "${{ needs.changes.outputs.filtered_areas }}"
        assert env["R_FRONTEND_BUILD"] == "${{ needs.frontend-build.result }}"

        run = step["run"]
        assert '--event "$EVENT_NAME"' in run
        assert 'if [[ "$CHANGES_RESULT" == "success" ]]; then' in run
        assert "read -ra" in run
        guard = run.index('if [[ "$CHANGES_RESULT" == "success" ]]')
        assert run.count("args+=(--filtered-area") == 1
        assert run.index("args+=(--filtered-area") > guard
        assert "|| true" not in run


# ----------------------------------------------------------------------
# deploy.yml gate permissions (generalised startup-failure guard)
# ----------------------------------------------------------------------


def test_deploy_gate_grants_every_ci_permission_when_calling_ci(ci, jobs):
    gate = _load(DEPLOY_YML)["jobs"]["gate"]
    assert gate["uses"] == "./.github/workflows/ci.yml"
    granted = gate["permissions"]

    requested: dict[str, str] = dict(ci.get("permissions") or {})
    for job in jobs.values():
        for scope, level in (job.get("permissions") or {}).items():
            if (
                _PERMISSION_LEVELS[level]
                > _PERMISSION_LEVELS[requested.get(scope, "none")]
            ):
                requested[scope] = level

    shortfalls = {
        scope: level
        for scope, level in requested.items()
        if _PERMISSION_LEVELS[granted.get(scope, "none")] < _PERMISSION_LEVELS[level]
    }
    assert not shortfalls, (
        f"deploy.yml `gate` must grant {shortfalls}; a reusable workflow cannot "
        f"request more than its caller grants, so every deploy would die as "
        f"startup_failure"
    )


# ----------------------------------------------------------------------
# F-12: build once, E2E against the production server
# ----------------------------------------------------------------------


class TestFrontendBuildHandoff:
    def test_frontend_e2e_downloads_build_artifact_when_running_e2e(self, jobs):
        build, e2e = jobs["frontend-build"], jobs["frontend-e2e"]
        assert "frontend-build" in _needs(e2e)

        upload = _step(build, name="Upload the standalone bundle")
        download = _step(e2e, name="Download the standalone bundle")
        assert upload["with"]["name"] == download["with"]["name"]
        assert upload["with"]["name"].endswith("-frontend-build")
        assert upload["with"]["path"] == "ci-results/frontend-standalone.tgz"
        assert download["with"]["path"] == "${{ runner.temp }}/frontend-build"

    def test_frontend_e2e_serves_standalone_when_playwright_runs(self, jobs):
        run_step = _step(jobs["frontend-e2e"], name="Run the complete mocked project")
        assert run_step["env"]["PLAYWRIGHT_WEB_SERVER"] == "standalone"

    def test_frontend_static_no_longer_builds_when_checks_load(self, jobs):
        checks = json.loads(
            (CI_DIR / "frontend-static-checks.json").read_text(encoding="utf-8")
        )
        assert [c["check_id"] for c in checks["checks"]] == ["typecheck", "lint"]
        step_names = [s.get("name", "") for s in jobs["frontend-static"]["steps"]]
        assert "Restore Next.js build cache" not in step_names
        assert "Restore Next.js build cache" in [
            s.get("name", "") for s in jobs["frontend-build"]["steps"]
        ]

    def test_playwright_config_defaults_to_dev_server_when_variable_unset(self):
        text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
        assert 'process.env.PLAYWRIGHT_WEB_SERVER ?? "dev"' in text
        assert 'command: "npm run dev"' in text
        assert 'command: "node .next/standalone/server.js"' in text


# ----------------------------------------------------------------------
# F-19: compose validation
# ----------------------------------------------------------------------

_INTERPOLATION = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)([^}]*)\}")
_SECRET_KEY = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE|_KEY$", re.I)


def _strings(node: Any) -> list[str]:
    """Every string key and value in a parsed YAML tree (what compose interpolates)."""
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in _strings(k) + _strings(v)]
    if isinstance(node, list):
        return [s for item in node for s in _strings(item)]
    return [node] if isinstance(node, str) else []


def _undefaulted_variables() -> set[str]:
    names: set[str] = set()
    for path in COMPOSE_FILES:
        for text in _strings(_load(path)):
            for name, modifier in _INTERPOLATION.findall(text):
                # `:-x` / `-x` supply a default; `:?` / `?` and bare `${X}` do not.
                if not modifier.startswith((":-", "-")):
                    names.add(name)
    return names


def _compose_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in COMPOSE_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        assert sep, f"malformed line in {COMPOSE_ENV.name}: {line!r}"
        values[key.strip()] = value.strip()
    return values


class TestComposeConfig:
    def test_repo_static_checks_run_compose_config_script_when_loaded(self):
        checks = json.loads(
            (CI_DIR / "repo-static-checks.json").read_text(encoding="utf-8")
        )
        by_id = {c["check_id"]: c for c in checks["checks"]}
        assert by_id["compose-config"]["command"] == [
            "bash",
            "../.github/scripts/ci-compose-config.sh",
        ]
        assert by_id["compose-config"]["mandatory"] is True
        assert (REPO_ROOT / ".github" / "scripts" / "ci-compose-config.sh").is_file()

    def test_compose_env_defines_every_undefaulted_variable_when_compared(self):
        missing = _undefaulted_variables() - set(_compose_env())
        assert not missing, f"ci/compose-ci.env must define {sorted(missing)}"

    def test_compose_env_holds_only_placeholders_when_loaded(self):
        env = _compose_env()
        assert env, "ci/compose-ci.env defines nothing"
        for key, value in env.items():
            assert "ci-placeholder" in value, f"{key} is not a ci-placeholder value"
            assert not _SECRET_KEY.search(key), f"{key} looks like a secret"

    def test_repo_static_records_docker_compose_version_when_recording_tools(
        self, jobs
    ):
        step = _step(jobs["repo-static"], name="Record tool versions")
        assert "docker compose version" in step["run"]


# ----------------------------------------------------------------------
# F-16: container-scan comment
# ----------------------------------------------------------------------


def test_container_scan_comment_drops_misleading_sentence_when_read():
    text = CI_YML.read_text(encoding="utf-8")
    assert "must build the image the same way the release build does" not in text


def test_container_scan_keeps_local_unpushed_build_when_read(jobs):
    build = _step(
        jobs["container-scan"], name="Build the ${{ matrix.component }} image"
    )
    options = build["with"]
    assert options["push"] is False
    assert options["load"] is True
    assert "platforms" not in options
    assert "provenance" not in options
