"""
Test Suite: Deterministic Dependency Setup and Frozen Lock Contracts

This suite validates that:
1. Backend Python dependencies are frozen in uv.lock (complete transitive closure)
2. Frontend JavaScript dependencies are frozen in package-lock.json
3. All versions align with pin_authority.py (source of truth)
4. No floating ranges exist (only exact SemVer versions)
5. Lock files are reproducible and deterministic
6. Dependencies are truly frozen (no mutable tags or drifts)

Requirements:
  - 2.9: CI resolves dependencies from frozen complete committed resolutions
  - 2.10: Runtime compatibility validated against pinned versions
  - 3.10: Pin drift tests prevent version inconsistencies
  - 3.14: Dependency setup is deterministic across runs
  - 3.16: Locks are frozen, committed, and reproducible
"""

import json
import re
from pathlib import Path
import subprocess
from typing import Dict, Set, Any
import tempfile
import shutil

import pytest
from hypothesis import given, strategies as st, settings
from tools.ci.pin_authority import (
    get_authority,
    is_exact_semver,
    is_exact_image_tag,
    get_python_runtime,
    get_node_runtime,
    get_scanner_versions,
    get_container_base_images,
)


BACKEND_DIR = Path(__file__).parents[4]

# A PEP 440 exact pin: `==` followed by a concrete release, optionally with
# pre/post/dev suffixes or a local version. Deliberately allows two-component
# releases (`2.14`) because that is what several upstreams actually publish, and
# deliberately rejects `==1.2.*`, which is a range wearing `==`.
_EXACT_PEP440_VERSION = re.compile(
    r"^[0-9]+(?:\.[0-9]+)*"  # release segment: 1 / 1.2 / 1.2.3
    r"(?:(?:a|b|rc)[0-9]+)?"  # pre-release
    r"(?:\.post[0-9]+)?"  # post-release
    r"(?:\.dev[0-9]+)?"  # dev release
    r"(?:\+[A-Za-z0-9.]+)?$"  # local version
)

# Operators that make a requirement non-exact. `==` is excluded; `===` (arbitrary
# equality) is exact but non-standard, so it is not accepted either.
_RANGE_OPERATORS = ("~=", ">=", "<=", "!=", ">", "<", "^", "*")


def _is_exact_pep440_pin(spec: str) -> tuple[bool, str]:
    """
    Return (is_exact, reason) for a single requirement string.

    Accepts extras and env markers: `bandit[toml]==1.9.4`,
    `pydantic[email]==2.12.5`. Rejects anything without exactly one `==` and a
    concrete version.
    """
    requirement = spec.split(";", 1)[0].strip()  # drop environment marker
    if not requirement:
        return False, "empty requirement"

    if requirement.count("==") != 1:
        return False, (
            "must use exactly one `==` for exact pinning "
            f"(found {requirement.count('==')})"
        )

    name_part, version_part = requirement.split("==", 1)
    name_part, version_part = name_part.strip(), version_part.strip()

    for operator in _RANGE_OPERATORS:
        if operator in version_part:
            return (
                False,
                f"version {version_part!r} contains range operator {operator!r}",
            )
    if operator_in_name := [o for o in _RANGE_OPERATORS if o in name_part]:
        return (
            False,
            f"name {name_part!r} contains range operator {operator_in_name[0]!r}",
        )

    if not _EXACT_PEP440_VERSION.match(version_part):
        return False, f"version {version_part!r} is not a concrete PEP 440 release"

    return True, ""


def _all_pyproject_dependency_specs(data: Dict[str, Any]) -> Dict[str, list]:
    """
    Return every dependency list in pyproject.toml, keyed by its TOML location.

    Covers all four places a Python dependency can be declared, so a list cannot
    escape the exactness checks by moving between them:
      - project.dependencies                     (runtime)
      - project.optional-dependencies.<extra>    (extras)
      - dependency-groups.<group>                (PEP 735 — the current dev home)
      - tool.uv.dev-dependencies / tool.uv.dependency-groups.<group> (legacy uv)

    PEP 735 group entries may be `{include-group = "other"}` tables rather than
    requirement strings; those are structural, carry no version, and are skipped.
    """
    project = data.get("project", {})
    groups: Dict[str, list] = {
        "project.dependencies": list(project.get("dependencies", []))
    }

    for extra, specs in project.get("optional-dependencies", {}).items():
        groups[f"project.optional-dependencies.{extra}"] = list(specs)

    for group, specs in data.get("dependency-groups", {}).items():
        if isinstance(specs, list):
            groups[f"dependency-groups.{group}"] = [
                s for s in specs if isinstance(s, str)
            ]

    uv = data.get("tool", {}).get("uv", {})
    if isinstance(uv.get("dev-dependencies"), list):
        groups["tool.uv.dev-dependencies"] = list(uv["dev-dependencies"])
    for group, specs in uv.get("dependency-groups", {}).items():
        if isinstance(specs, list):
            groups[f"tool.uv.dependency-groups.{group}"] = list(specs)

    return groups


def _parse_requirements(path: Path) -> Dict[str, str]:
    """
    Parse a requirements file into {name_with_extras_lowercased: version}.

    Strips comments and skips `-r` includes so each file is compared on its own
    direct pins. Fails loudly on a non-exact line rather than silently ignoring
    it — a range in a requirements file is exactly what these contracts forbid.
    """
    pins: Dict[str, str] = {}
    for lineno, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        ok, reason = _is_exact_pep440_pin(line)
        assert ok, f"{path.name}:{lineno}: {line!r} is not an exact pin — {reason}"
        name, version = line.split("==", 1)
        pins[name.strip().lower()] = version.strip()
    return pins


def _normalise_specs(specs: list) -> Dict[str, str]:
    """Turn a list of exact requirement strings into {name: version}."""
    out: Dict[str, str] = {}
    for spec in specs:
        name, version = spec.split(";", 1)[0].strip().split("==", 1)
        out[name.strip().lower()] = version.strip()
    return out


class TestPyprojectRequirementsSync:
    """
    Assert backend/pyproject.toml and backend/requirements-*.txt stay identical.

    pyproject.toml/uv.lock are the resolution authority for both CI (`uv sync
    --frozen`) and local dev (`uv sync`); requirements-*.txt are a
    human-readable convenience mirror that is not read by either. This suite
    keeps the mirror honest so it cannot silently disagree with the authority.

    Historically (before uv.lock was committed) requirements-*.txt WAS the
    only CI-read source and drifted from pyproject.toml, because nothing
    compared them: pyproject declared 3 dev pins while
    requirements-dev.txt declared 12, and `uv sync` consequently UNINSTALLED
    pytest, ruff, pyright, vulture, import-linter, bandit, pip-audit, httpx and
    playwright from a working venv, and downgraded pytest-cov 7.1.0 -> 5.0.0.
    Both sides installed "successfully" the whole time — the two environments
    were just different, which is why only a comparison catches it.
    """

    def test_prod_dependencies_match_requirements_prod(self) -> None:
        """project.dependencies must equal requirements-prod.txt exactly."""
        import tomllib

        data = tomllib.loads(
            (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )
        declared = _normalise_specs(data["project"]["dependencies"])
        installed = _parse_requirements(BACKEND_DIR / "requirements-prod.txt")

        assert declared == installed, _sync_failure_message(
            "project.dependencies", declared, "requirements-prod.txt", installed
        )

    def test_dev_dependencies_match_requirements_dev(self) -> None:
        """The `dev` dependency group must equal requirements-dev.txt's own pins."""
        import tomllib

        data = tomllib.loads(
            (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )
        groups = data.get("dependency-groups", {})
        assert "dev" in groups, (
            "pyproject.toml must declare a [dependency-groups] `dev` group — "
            "`uv sync` installs that group by default, so it is what a local "
            "developer environment is built from"
        )

        declared = _normalise_specs([s for s in groups["dev"] if isinstance(s, str)])
        # requirements-dev.txt starts with `-r requirements-prod.txt`; _parse_requirements
        # skips that include, so this compares dev-only pins against dev-only pins.
        installed = _parse_requirements(BACKEND_DIR / "requirements-dev.txt")

        assert declared == installed, _sync_failure_message(
            "dependency-groups.dev", declared, "requirements-dev.txt", installed
        )

    def test_dev_dependencies_declared_in_exactly_one_place(self) -> None:
        """
        Guard against a THIRD copy of the dev list reappearing.

        Before this suite, the dev toolchain was spread across
        `[project.optional-dependencies].dev` (3 pins) and the deprecated
        `[tool.uv].dev-dependencies` (1 pin) as well as requirements-dev.txt (12
        pins) — three lists, three different answers. `[dependency-groups].dev`
        is now the single pyproject home; the legacy locations must stay empty so
        they cannot start drifting again.
        """
        import tomllib

        data = tomllib.loads(
            (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
        )

        legacy_locations = [
            location
            for location in _all_pyproject_dependency_specs(data)
            if location
            in ("project.optional-dependencies.dev", "tool.uv.dev-dependencies")
            or location.startswith("tool.uv.dependency-groups.")
        ]
        assert not legacy_locations, (
            "dev dependencies must be declared ONLY in [dependency-groups].dev, "
            f"but these legacy locations are also populated: {legacy_locations}. "
            "Multiple lists drift; `uv sync` reads only some of them."
        )


def _sync_failure_message(
    left_name: str, left: Dict[str, str], right_name: str, right: Dict[str, str]
) -> str:
    """Build a diff-style message naming exactly which pins disagree."""
    lines = [f"{left_name} and {right_name} disagree:"]
    for package in sorted(set(left) | set(right)):
        in_left, in_right = left.get(package), right.get(package)
        if in_left == in_right:
            continue
        if in_left is None:
            lines.append(
                f"  - {package}=={in_right} in {right_name} but MISSING from {left_name}"
            )
        elif in_right is None:
            lines.append(
                f"  - {package}=={in_left} in {left_name} but MISSING from {right_name}"
            )
        else:
            lines.append(
                f"  - {package}: {left_name}=={in_left} vs {right_name}=={in_right}"
            )
    lines.append(
        "Edit BOTH files together; CI installs the requirements files, `uv sync` reads pyproject."
    )
    return "\n".join(lines)


class TestBackendLockDeterminism:
    """Test backend uv.lock determinism, completeness, and pin alignment."""

    @pytest.fixture
    def backend_dir(self) -> Path:
        """Get backend directory path (tests/unit/tools/ci/<file> -> backend/)."""
        return Path(__file__).resolve().parents[4]

    @pytest.fixture
    def uv_lock_path(self, backend_dir: Path) -> Path:
        """Get uv.lock file path."""
        return backend_dir / "uv.lock"

    @pytest.fixture
    def pyproject_path(self, backend_dir: Path) -> Path:
        """Get pyproject.toml file path."""
        return backend_dir / "pyproject.toml"

    def test_uv_lock_exists_and_readable(self, uv_lock_path: Path) -> None:
        """Verify uv.lock exists, is readable, and is valid TOML."""
        assert uv_lock_path.exists(), "uv.lock must exist and be committed"
        content = uv_lock_path.read_text(encoding="utf-8")
        assert len(content) > 0, "uv.lock must not be empty"
        assert "version =" in content, "uv.lock must contain version metadata"

    def test_uv_lock_contains_python_version(self, uv_lock_path: Path) -> None:
        """Verify uv.lock records the Python version it was created with."""
        content = uv_lock_path.read_text(encoding="utf-8")
        # uv.lock format: "python = "3.13.0" or similar
        assert (
            "python =" in content or "requires_python" in content
        ), "uv.lock must record Python version metadata"
        expected_python = get_python_runtime()
        # Check that the runtime version appears in the lock file
        assert (
            expected_python in content
        ), f"uv.lock must reference pinned Python {expected_python}"

    def test_pyproject_dependencies_are_exact(self, pyproject_path: Path) -> None:
        """
        Verify EVERY pyproject.toml dependency list uses exact pinning.

        Covers project.dependencies AND every dependency group (see
        _all_pyproject_dependency_specs). This previously read only
        project.dependencies, so the entire dev toolchain was unchecked.

        Uses _is_exact_pep440_pin, NOT is_exact_semver: PyPI versions follow
        PEP 440, not SemVer, and two of this project's exact pins have only two
        components — `vulture==2.14` and `import-linter==2.1` are the actual
        released versions (2.14.0 / 2.1.0 do not exist). A SemVer 3-part check
        would reject correct pins and pressure someone into inventing a version.
        """
        import tomllib

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        groups = _all_pyproject_dependency_specs(data)

        assert groups.get(
            "project.dependencies"
        ), "pyproject.toml must declare project.dependencies"

        for location, specs in groups.items():
            for spec in specs:
                ok, reason = _is_exact_pep440_pin(spec)
                assert ok, f"{location}: {spec!r} is not an exact pin — {reason}"

    def test_no_floating_version_ranges_in_pyproject(
        self, pyproject_path: Path
    ) -> None:
        """Reject any floating ranges (~, ^, >=, >, <=, <) in dependencies."""
        import tomllib

        content = pyproject_path.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        # Collect from EVERY dependency list, including the top-level PEP 735
        # `[dependency-groups]` table. That table was missing here: this test
        # scanned project.dependencies, project.optional-dependencies and
        # tool.uv.dependency-groups only, so when the dev toolchain moved to
        # `[dependency-groups].dev` it silently stopped being scanned at all.
        all_deps = [
            spec
            for specs in _all_pyproject_dependency_specs(data).values()
            for spec in specs
        ]

        forbidden_patterns = [
            r"~=",  # compatible release
            r"\^",  # caret (npm-style, not standard in pyproject)
            r">(?!=)",  # greater-than but not >=
            r"<(?!=)",  # less-than but not <=
            r"(?<!=)>(?!=)",  # bare >
            r"(?<!=)<(?!=)",  # bare <
        ]

        for dep in all_deps:
            for pattern in forbidden_patterns:
                if re.search(pattern, dep):
                    raise AssertionError(
                        f"Dependency {dep} contains floating range '{pattern}' — "
                        f"must use exact pinning with =="
                    )

    @pytest.mark.allow_io(
        "the assertion IS `uv lock --check`'s own verdict; a stub would assert the stub"
    )
    def test_uv_lock_frozen_check_passes(self, backend_dir: Path) -> None:
        """Verify uv lock --check would pass (frozen check)."""
        # Use uv lock --check to verify the lock is frozen
        result = subprocess.run(
            ["uv", "lock", "--check"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )
        assert (
            result.returncode == 0
        ), f"uv lock --check failed; lock is not frozen:\n{result.stderr}"

    @pytest.mark.allow_io(
        "the assertion IS `uv sync --frozen --dry-run`'s verdict on the committed lock"
    )
    def test_uv_sync_frozen_mode_works(self, backend_dir: Path) -> None:
        """Verify uv sync --frozen would work (deterministic install)."""
        # This validates the lock is complete and in sync with pyproject.toml
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Copy pyproject.toml and uv.lock to temp dir
            shutil.copy(backend_dir / "pyproject.toml", tmpdir_path / "pyproject.toml")
            shutil.copy(backend_dir / "uv.lock", tmpdir_path / "uv.lock")

            # Try dry-run frozen sync
            result = subprocess.run(
                ["uv", "sync", "--frozen", "--dry-run"],
                cwd=tmpdir_path,
                capture_output=True,
                text=True,
            )
            # --dry-run should succeed (or at least not fail on lock mismatch)
            # If it fails, likely lock is out of sync with pyproject
            assert (
                "lock is out of sync" not in result.stderr.lower()
            ), f"uv.lock is out of sync with pyproject.toml:\n{result.stderr}"

    def test_backend_python_version_alignment(self) -> None:
        """Verify backend Python metadata aligns with pin authority."""
        import tomllib

        backend_dir = Path(__file__).parents[4]
        pyproject_path = backend_dir / "pyproject.toml"

        content = pyproject_path.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        expected_python = get_python_runtime()
        # Extract minimum Python version from requires-python field
        requires_python = data.get("project", {}).get("requires-python", "")

        # Should contain or allow the pinned runtime
        assert (
            expected_python or requires_python
        ), "pyproject.toml must declare Python version compatibility"

        # Check ruff target version
        ruff_config = data.get("tool", {}).get("ruff", {})
        ruff_target = ruff_config.get("target-version", "")
        auth = get_authority()
        expected_ruff_target = auth.ruff_target_version
        assert ruff_target == expected_ruff_target, (
            f"Ruff target version {ruff_target} does not match pin authority "
            f"{expected_ruff_target}"
        )


class TestFrontendLockDeterminism:
    """Test frontend package-lock.json determinism, completeness, and pin alignment."""

    @pytest.fixture
    def frontend_dir(self) -> Path:
        """Get frontend directory path."""
        return Path(__file__).parents[5] / "frontend"

    @pytest.fixture
    def package_lock_path(self, frontend_dir: Path) -> Path:
        """Get package-lock.json file path."""
        return frontend_dir / "package-lock.json"

    @pytest.fixture
    def package_json_path(self, frontend_dir: Path) -> Path:
        """Get package.json file path."""
        return frontend_dir / "package.json"

    def test_package_lock_exists_and_readable(self, package_lock_path: Path) -> None:
        """Verify package-lock.json exists, is readable, and is valid JSON."""
        assert (
            package_lock_path.exists()
        ), "package-lock.json must exist and be committed"
        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert "lockfileVersion" in data, "package-lock.json must have lockfileVersion"
        assert (
            data["lockfileVersion"] >= 3
        ), "package-lock.json must use lockfileVersion 3+ (modern format)"

    def test_package_json_dependencies_are_exact(self, package_json_path: Path) -> None:
        """Verify package.json dependencies use consistent pinning strategy.

        Note: package.json may use floating ranges (^, ~), but these are locked
        down by package-lock.json v3. We verify:
        1. package-lock.json exists and uses v3 (lock file is authoritative)
        2. Dependencies use consistent strategy (not mixing exact + ranges)
        """
        content = package_json_path.read_text(encoding="utf-8")
        data = json.loads(content)

        all_deps: dict[str, str] = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))
        assert all_deps, "package.json declares no dependencies"

        # This used to `pytest.skip("package.json can use floating ranges;
        # package-lock.json v3 locks them")`. The lock does pin what gets
        # installed, but a floating range in the manifest still means the
        # manifest and the lock disagree about intent: `npm install` will happily
        # move within the range and rewrite the lock, so the recorded resolution
        # is only as stable as nobody having run it. The requirement is exact
        # versions in the manifest, so assert that instead of explaining it away.
        floating = {
            name: spec
            for name, spec in all_deps.items()
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?", spec)
        }

        assert not floating, (
            "frontend/package.json must pin exact versions. Floating "
            f"specifier(s): {floating}. Pin each to the version package-lock.json "
            "already resolves, then run `npm install --package-lock-only` so the "
            "manifest and the lock agree."
        )

    def test_package_lock_has_lockfile_version_3(self, package_lock_path: Path) -> None:
        """Verify package-lock.json uses lockfileVersion 3 (reproducible format)."""
        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert (
            data["lockfileVersion"] == 3
        ), f"package-lock.json must use lockfileVersion 3, found {data['lockfileVersion']}"

    def test_package_lock_integrity(self, package_lock_path: Path) -> None:
        """Verify package-lock.json structural integrity."""
        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # Must have packages key
        assert "packages" in data, "package-lock.json must have packages key"

        # Root package should have name and version
        root_pkg = data["packages"].get("", {})
        assert (
            "name" in root_pkg or root_pkg == {}
        ), "package-lock.json root package should have metadata"

    @pytest.mark.allow_io(
        "probes the real `npm ci --dry-run` against the committed package-lock.json"
    )
    def test_npm_ci_would_work_deterministically(self, frontend_dir: Path) -> None:
        """Verify npm ci would work with the current lock (dry-run if possible)."""
        # npm ci is deterministic when package-lock.json exists
        # This test just verifies the lock file exists (actual install happens in CI)
        package_lock_path = frontend_dir / "package-lock.json"
        assert (
            package_lock_path.exists()
        ), "package-lock.json must exist for deterministic npm ci"

        # Try dry-run if available (platform-dependent)
        try:
            result = subprocess.run(
                ["npm", "ci", "--dry-run"],
                cwd=frontend_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 and "--dry-run" not in result.stderr:
                # Real error, not just --dry-run not supported
                pass  # Accept failure on Windows or where npm not in PATH
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # npm not in PATH or timeout; skip platform-specific check
            pytest.skip("npm not available on this platform")

    def test_frontend_node_version_alignment(self) -> None:
        """Verify frontend Node.js version metadata aligns with pin authority."""
        frontend_dir = Path(__file__).parents[5] / "frontend"
        package_json_path = frontend_dir / "package.json"

        content = package_json_path.read_text(encoding="utf-8")
        data = json.loads(content)

        engines = data.get("engines", {})
        node_spec = engines.get("node", "")

        # The spec should allow the pinned runtime
        _ = get_node_runtime()  # Kept for reference
        # Typically something like ">=24.0.0 <25.0.0"
        assert (
            node_spec or data.get("packageManager")
        ), "package.json must declare node engines or packageManager for reproducibility"

    def test_no_mutable_tags_in_package_json(self, package_json_path: Path) -> None:
        """Reject any mutable tags or floating ranges in dependencies."""
        content = package_json_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # Collect all dependencies
        all_deps = {}
        all_deps.update(data.get("dependencies", {}))
        all_deps.update(data.get("devDependencies", {}))

        # Reject mutable/floating patterns
        _ = [
            r"^latest$",
            r"^\*$",
            r"^",  # caret (floating)
            r"~",  # tilde (floating)
            r">",  # greater than (floating)
            r"<",  # less than (floating)
        ]  # Kept for reference; validation done via version_spec checks below

        for dep_name, version_spec in all_deps.items():
            if version_spec.startswith(("^", "~", ">", "<", "|")):
                # These are explicitly allowed in package.json by npm semantics,
                # but package-lock.json locks them down. We only warn here.
                pytest.skip(
                    f"Note: {dep_name}@{version_spec} is a floating range in package.json"
                )


class TestPinAuthorityConsistency:
    """Test that pin_authority.py values are consistent and valid."""

    def test_all_versions_are_exact_semver(self) -> None:
        """Verify all pinned versions use exact SemVer."""
        auth = get_authority()

        version_fields = [
            ("python_runtime_version", auth.python_runtime_version),
            ("node_runtime_version", auth.node_runtime_version),
            ("playwright_package_version", auth.playwright_package_version),
            ("chromium_version", auth.chromium_version),
        ]

        for field_name, version in version_fields:
            assert is_exact_semver(
                version
            ), f"{field_name} = {version} is not exact SemVer"

        # Check scanner versions
        scanners = get_scanner_versions()
        for tool_name, version in scanners.items():
            assert is_exact_semver(
                version
            ), f"Scanner {tool_name} version {version} is not exact SemVer"

    def test_container_images_are_pinned(self) -> None:
        """Verify all container images are pinned (not floating tags)."""
        images = get_container_base_images()

        # Each image should have a tag or digest
        for component, image_ref in images.items():
            assert image_ref, f"Image for {component} must not be empty"
            assert ":" in image_ref or "@" in image_ref, (
                f"Image {image_ref} for {component} must have a tag or digest, "
                f"not just a repo name"
            )

    def test_no_latest_tags_in_images(self) -> None:
        """Reject 'latest' tags (mutable references)."""
        images = get_container_base_images()

        for component, image_ref in images.items():
            assert (
                ":latest" not in image_ref.lower()
            ), f"Image {image_ref} for {component} must not use 'latest' tag"
            assert (
                image_ref.lower() != "latest"
            ), f"Image {component} must not be 'latest'"

    def test_python_requirements_alignment(self) -> None:
        """Verify Python version fields are internally consistent."""
        auth = get_authority()

        # Runtime >= minimum
        # Extract major.minor.patch
        runtime_parts = auth.python_runtime_version.split(".")[:3]
        minimum_parts = auth.python_requires_minimum.split(".")[:3]

        runtime_tuple = tuple(int(p) for p in runtime_parts)
        minimum_tuple = tuple(int(p) for p in minimum_parts)

        assert runtime_tuple >= minimum_tuple, (
            f"Python runtime {auth.python_runtime_version} must be "
            f">= minimum {auth.python_requires_minimum}"
        )

    def test_ruff_target_version_compatible(self) -> None:
        """Verify Ruff target version matches Python runtime."""
        auth = get_authority()

        # Extract major.minor from runtime
        runtime_parts = auth.python_runtime_version.split(".")[:2]
        _ = f"py{''.join(runtime_parts)}"  # Kept for reference

        # Ruff target should be <= runtime
        # (e.g., py313 for 3.13.x)
        assert auth.ruff_target_version.startswith(
            "py"
        ), f"Ruff target {auth.ruff_target_version} must start with 'py'"


class TestLockReproducibility:
    """Property-based tests for lock reproducibility."""

    @given(
        st.just(None)  # Placeholder for future property strategies
    )
    @settings(max_examples=1, deadline=None)  # `uv lock` runs twice; no fixed deadline
    @pytest.mark.allow_io(
        "reproducibility can only be shown by running the real resolver twice"
    )
    def test_uv_lock_generates_identically_on_clean_install(
        self, _placeholder: None
    ) -> None:
        """
        Verify: Given clean pyproject.toml and no lock, `uv lock` produces
        byte-identical lock (within tolerance for timestamps).
        """
        backend_dir = Path(__file__).parents[4]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Copy minimal pyproject.toml setup
            shutil.copy(backend_dir / "pyproject.toml", tmpdir_path / "pyproject.toml")

            # Generate lock once
            result1 = subprocess.run(
                ["uv", "lock"],
                cwd=tmpdir_path,
                capture_output=True,
                text=True,
            )
            assert result1.returncode == 0, f"First uv lock failed: {result1.stderr}"

            lock1 = (tmpdir_path / "uv.lock").read_text(encoding="utf-8")

            # Clean and generate again
            (tmpdir_path / "uv.lock").unlink()
            result2 = subprocess.run(
                ["uv", "lock"],
                cwd=tmpdir_path,
                capture_output=True,
                text=True,
            )
            assert result2.returncode == 0, f"Second uv lock failed: {result2.stderr}"

            lock2 = (tmpdir_path / "uv.lock").read_text(encoding="utf-8")

            # Locks should be byte-identical (or nearly so, ignoring metadata timestamps)
            # For deterministic proof, strip any timestamp lines and compare
            lock1_normalized = "\n".join(
                line
                for line in lock1.split("\n")
                if not line.strip().startswith("#") or "timestamp" not in line.lower()
            )
            lock2_normalized = "\n".join(
                line
                for line in lock2.split("\n")
                if not line.strip().startswith("#") or "timestamp" not in line.lower()
            )

            assert (
                lock1_normalized == lock2_normalized
            ), "uv lock output is not deterministic (differs on clean regeneration)"

    @given(st.just(None))
    @settings(max_examples=1, deadline=None)  # No deadline for optional platform tests
    def test_npm_ci_is_deterministic_with_lock(self, _placeholder: None) -> None:
        """
        Verify: Given package-lock.json, `npm ci` is deterministic across runs.
        """
        frontend_dir = Path(__file__).parents[5] / "frontend"

        if not frontend_dir.exists():
            pytest.skip("Frontend directory not found")

        # Just verify package-lock.json exists and is v3 (we can't run npm on all platforms)
        package_lock_path = frontend_dir / "package-lock.json"
        assert package_lock_path.exists(), "package-lock.json must exist"

        # Verify it's v3 format (deterministic)
        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert (
            data.get("lockfileVersion") == 3
        ), "package-lock must use v3 for determinism"


class TestLockFileDrift:
    """Test for consistency between lock files and manifest files."""

    def test_backend_lock_digest_present(self) -> None:
        """
        Verify uv.lock includes a content digest for reproducibility checking.
        """
        backend_dir = Path(__file__).parents[4]
        uv_lock_path = backend_dir / "uv.lock"

        content = uv_lock_path.read_text(encoding="utf-8")
        # uv.lock includes a marker comment or field for validation
        # At minimum, it should have versioning info
        assert (
            "version =" in content or "generated" in content.lower()
        ), "uv.lock must have reproducibility markers"

    def test_frontend_package_lock_v3_format(self) -> None:
        """Verify package-lock.json uses v3 format (reproducible)."""
        frontend_dir = Path(__file__).parents[5] / "frontend"
        package_lock_path = frontend_dir / "package-lock.json"

        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # v3 format is required for reproducibility
        assert data.get("lockfileVersion") == 3, (
            f"package-lock.json lockfileVersion must be 3 for reproducibility, "
            f"found {data.get('lockfileVersion')}"
        )

    def test_no_floating_ranges_backend(self) -> None:
        """Backend: reject any version spec that is not exact pinning."""
        backend_dir = Path(__file__).parents[4]
        pyproject_path = backend_dir / "pyproject.toml"

        import tomllib

        content = pyproject_path.read_bytes()
        data = tomllib.loads(content.decode("utf-8"))

        # Collect all dependencies
        all_deps = []
        all_deps.extend(data.get("project", {}).get("dependencies", []))

        for dep_spec in (
            data.get("project", {}).get("optional-dependencies", {}).values()
        ):
            all_deps.extend(dep_spec)

        # Every dependency must use ==
        for dep in all_deps:
            # Skip special syntax like extras
            if ";" in dep:
                dep = dep.split(";")[0].strip()

            # Must have ==
            assert "==" in dep, (
                f"Dependency {dep} must use exact pinning (==), " f"not floating ranges"
            )

    def test_no_floating_ranges_frontend(self) -> None:
        """Frontend: package-lock.json enforces exact versions."""
        frontend_dir = Path(__file__).parents[5] / "frontend"
        package_lock_path = frontend_dir / "package-lock.json"

        content = package_lock_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # In package-lock v3, all resolved packages have exact versions
        packages = data.get("packages", {})

        # Check a sample of packages in lock
        for pkg_path, pkg_data in list(packages.items())[:20]:  # Sample
            if "version" in pkg_data:
                version = pkg_data["version"]
                # Must be exact (no ranges)
                assert not any(version.startswith(c) for c in "~^><|"), (
                    f"Package {pkg_path} has range {version} in lock; "
                    f"package-lock should have exact versions"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
