"""Contract: the built-in Skills catalog ships in the image and resolves at runtime.

``app/agents/skills_catalog.py`` used to read ``<backend>/skills/global`` only. In
the image ``<backend>`` is ``WORKDIR /app``, and ``/app/skills`` is the per-user
EBS bind-mount (docker-compose.yml), which shadows anything baked under it. So the
catalog was always empty in deployed environments, and every manifest ``skills:``
id (prototype-specify's ``velocity-design``) failed with "unresolvable step skill
id". The image now bakes the catalog outside that mount and points
``GLOBAL_SKILLS_ROOT`` at it.

Everything here reads repo files (Dockerfile, .dockerignore, docker-compose.yml,
manifests, the catalog); nothing needs Docker. The regression tests rebuild the
image's file layout in ``tmp_path`` FROM those files and run the real
``skills_catalog.py`` from inside it, so reverting the module, the Dockerfile
``ENV`` or the ``COPY`` brings back the original failure.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest
import yaml

import app.agents
import app.agents.skills_catalog as skills_catalog
from agents.factory import AgentContext, create_runner
from app.agents import hooks_catalog, skills
from app.agents.sandbox import RunSandbox
from app.core import config
from app.services.od_context_sandbox import write_od_context_to_sandbox
from app.services.od_loader import od_root
from tests.fakes.chat_model import FakeStaticChatModel

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = _BACKEND_DIR.parent
_CHECKOUT_CATALOG = _BACKEND_DIR / "skills" / "global"
_CATALOG_SOURCE = Path(skills_catalog.__file__).resolve()
_TEMPLATE_BODY = "# Web Prototype Template\n\nHero + feature triplet."


# ---------------------------------------------------------------------------
# Repo-file readers
# ---------------------------------------------------------------------------


def _runtime_stage() -> str:
    """The Dockerfile's runtime stage with comment lines dropped."""
    text = (
        (_BACKEND_DIR / "Dockerfile")
        .read_text(encoding="utf-8")
        .split(" AS runtime", 1)[1]
    )
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _dockerfile_env(name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}=(\S+)", _runtime_stage())
    return match.group(1) if match else None


def _runtime_copy(src: str) -> tuple[list[str], PurePosixPath] | None:
    """``(flags, absolute image dest)`` of the runtime-stage ``COPY <src> <dest>``."""
    runtime = _runtime_stage()
    copy = re.search(
        rf"^COPY\s+((?:--\S+\s+)*){re.escape(src)}\s+(\S+)\s*$", runtime, re.MULTILINE
    )
    if copy is None:
        return None
    workdir = re.findall(r"^WORKDIR\s+(\S+)", runtime[: copy.start()], re.MULTILINE)[-1]
    return copy.group(1).split(), PurePosixPath(workdir) / copy.group(2)


def _backend_mount_targets() -> list[PurePosixPath]:
    """Container paths docker-compose.yml bind-mounts into the backend service."""
    compose = yaml.safe_load(
        (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    targets: list[PurePosixPath] = []
    for volume in compose["services"]["backend"].get("volumes", []):
        target = volume.split(":")[1] if isinstance(volume, str) else volume["target"]
        targets.append(PurePosixPath(target))
    return targets


def _dockerignore_rules() -> list[str]:
    lines = (_BACKEND_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _declared_skill_ids(node: object) -> set[str]:
    """Every string under any ``skills:`` list, at any nesting depth."""
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            if key == "skills" and isinstance(value, list):
                found.update(v for v in value if isinstance(v, str) and v)
            else:
                found |= _declared_skill_ids(value)
        return found
    if isinstance(node, list):
        found = set()
        for item in node:
            found |= _declared_skill_ids(item)
        return found
    return set()


def _manifest_step_skills(workflow: str, agent_id: str) -> list[str]:
    manifest_path = _BACKEND_DIR / "agents" / "workflows" / workflow / "workflow.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for step in manifest["steps"]:
        if isinstance(step, dict) and step.get("agent") == agent_id:
            return list(step.get("skills") or [])
    raise AssertionError(f"{workflow} has no {agent_id} step")


def _on_host(image_root: Path, image_path: PurePosixPath) -> Path:
    """Where an absolute image path lives inside the tmp image tree."""
    return image_root.joinpath(*image_path.parts[1:])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checkout_catalog_ids(monkeypatch) -> Iterator[set[str]]:
    """Ids of every skill folder under the checkout's backend/skills/global."""
    monkeypatch.setattr(skills_catalog, "_GLOBAL_SKILL_DIR", _CHECKOUT_CATALOG)
    skills_catalog.clear_cache()
    yield {entry.id for entry in skills_catalog.list_global_skills()}
    skills_catalog.clear_cache()


@pytest.fixture
def image_catalog(tmp_path, monkeypatch) -> ModuleType:
    """The real skills_catalog.py, loaded from an image-shaped tree in tmp_path.

    The layout comes from the repo, not from this test: the module sits where
    ``COPY app/`` puts it, the catalog sits where ``COPY skills/global/`` puts it
    (if anywhere), and every docker-compose bind-mount target is an EMPTY dir,
    because a fresh EBS volume shadows whatever the image baked there.
    ``GLOBAL_SKILLS_ROOT`` is exported the way the Dockerfile ``ENV`` sets it and
    read by a freshly built ``Settings``, as at container boot. The module is
    installed as ``app.agents.skills_catalog``, so the factory and the stager
    (which both import it lazily) resolve against it.
    """
    image_root = tmp_path / "image"
    app_copy = _runtime_copy("app/")
    assert app_copy is not None, "runtime stage must COPY app/"
    module_path = _on_host(image_root, app_copy[1]) / "agents" / "skills_catalog.py"
    module_path.parent.mkdir(parents=True)
    shutil.copyfile(_CATALOG_SOURCE, module_path)

    catalog_copy = _runtime_copy("skills/global/")
    if catalog_copy is not None:
        shutil.copytree(_CHECKOUT_CATALOG, _on_host(image_root, catalog_copy[1]))

    for target in _backend_mount_targets():
        mounted = _on_host(image_root, target)
        shutil.rmtree(mounted, ignore_errors=True)
        mounted.mkdir(parents=True)

    env_root = _dockerfile_env("GLOBAL_SKILLS_ROOT")
    if env_root:
        monkeypatch.setenv(
            "GLOBAL_SKILLS_ROOT", str(_on_host(image_root, PurePosixPath(env_root)))
        )
    else:
        monkeypatch.delenv("GLOBAL_SKILLS_ROOT", raising=False)
    monkeypatch.setattr(config, "settings", config.Settings())

    spec = importlib.util.spec_from_file_location(skills_catalog.__name__, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, skills_catalog.__name__, module)
    monkeypatch.setattr(app.agents, "skills_catalog", module)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Regression: the image layout serves the catalog (the dev failure)
# ---------------------------------------------------------------------------


def test_create_runner_stages_velocity_design_with_template_body_when_running_from_image_layout(
    image_catalog, tmp_path
):
    # Arrange — the exact step from the dev failure, with a template selected so the
    # skill's {{INJECT_FROM:...}} marker has real content to resolve.
    step_skills = _manifest_step_skills("prototype", "prototype-specify")
    assert (
        "velocity-design" in step_skills
    ), "fixture assumption: the step from the dev log"
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    sandbox = RunSandbox(
        "test-user", "image-layout-run", runs_root=str(runs_root), has_git=False
    )
    sandbox.ensure()
    write_od_context_to_sandbox(
        sandbox,
        {
            "template_id": "web-prototype",
            "template_name": "Web Prototype",
            "template_body": _TEMPLATE_BODY,
            "ds_id": "apple",
            "ds_name": "Apple",
            "ds_body": "# Apple Design System",
            "craft_block": "",
            "no_template": False,
            "is_design_system_required": None,
        },
        explicit_selection=True,
    )
    ctx = AgentContext(
        user_request="build it",
        model=FakeStaticChatModel(),
        user_id="test-user",
        run_id=sandbox.run_id,
        step_skills=step_skills,
    )

    # Act — reverting the fix raises "unresolvable step skill id: velocity-design" here.
    create_runner("prototype-specify", ctx, run_sandbox=sandbox)

    # Assert — staged from the baked catalog, with the template body, not the fallback.
    assert ctx.skills_delivery is not None
    assert ctx.skills_delivery.staged == step_skills
    staged = sandbox.read("skills/velocity-design/SKILL.md")
    assert "Hero + feature triplet." in staged
    assert "<!-- -->" not in staged
    assert "{{INJECT_FROM:" not in staged


def test_list_global_skills_serves_every_checkout_skill_when_running_from_image_layout(
    image_catalog, checkout_catalog_ids
):
    # Act
    served = {entry.id for entry in image_catalog.list_global_skills()}

    # Assert — generic: every repo-shipped skill, not just the one in the dev log.
    assert checkout_catalog_ids, "the checkout catalog must not be empty"
    assert served == checkout_catalog_ids


def test_manifest_skill_ids_resolve_in_checkout_catalog_when_scanning_every_workflow(
    checkout_catalog_ids,
):
    # Arrange
    manifests = sorted((_BACKEND_DIR / "agents" / "workflows").glob("*/workflow.yaml"))

    # Act
    missing: dict[str, list[str]] = {}
    for manifest in manifests:
        declared = _declared_skill_ids(
            yaml.safe_load(manifest.read_text(encoding="utf-8"))
        )
        if declared - checkout_catalog_ids:
            missing[manifest.parent.name] = sorted(declared - checkout_catalog_ids)

    # Assert
    assert (
        not missing
    ), f"manifest skills: ids absent from backend/skills/global: {missing}"


# ---------------------------------------------------------------------------
# Guards: Dockerfile + .dockerignore packaging
# ---------------------------------------------------------------------------


def test_dockerfile_copies_catalog_to_global_skills_root_when_runtime_stage_builds():
    # Arrange
    env_root = _dockerfile_env("GLOBAL_SKILLS_ROOT")
    catalog_copy = _runtime_copy("skills/global/")

    # Assert
    assert env_root, "runtime stage must ENV GLOBAL_SKILLS_ROOT"
    assert catalog_copy is not None, "runtime stage must COPY skills/global/"
    flags, dest = catalog_copy
    assert dest == PurePosixPath(env_root)
    # Outside every bind-mount (a mount would shadow it) and root-owned (no --chown),
    # so the runtime user can read the catalog but never rewrite it.
    for target in _backend_mount_targets():
        assert (
            dest != target and target not in dest.parents
        ), f"{dest} is shadowed by {target}"
    assert not any(flag.startswith("--chown") for flag in flags)


def test_dockerignore_readmits_only_skills_global_when_skills_dir_is_excluded():
    # Arrange
    rules = _dockerignore_rules()

    # Act
    last_exclude = max(i for i, rule in enumerate(rules) if rule == "skills/")
    readmits = [i for i, rule in enumerate(rules) if rule.startswith("!skills")]
    last_readmit = max(i for i, rule in enumerate(rules) if rule.startswith("!"))

    # Assert
    assert {rules[i] for i in readmits} == {"!skills/global", "!skills/global/**"}
    assert (
        min(readmits) > last_exclude
    ), "re-include must come after `skills/` (last match wins)"
    assert rules.index("**/.env") > last_readmit, "secret excludes must stay last"


@pytest.mark.parametrize(
    "read_path",
    [hooks_catalog._GLOBAL_HOOKS_DIR, skills.PPTX_SKILLS_DIR],
    ids=["hooks-catalog", "pptx-reference-docs"],
)
def test_dockerfile_bakes_backend_data_dir_at_path_code_reads_when_dir_is_backend_relative(
    read_path,
):
    # Arrange — the loaders resolve <backend>/<rel>; the image flattens <backend> to
    # WORKDIR /app, so the tree must be COPYed from <rel>/ to /app/<rel>.
    # resolve(): skills.PPTX_SKILLS_DIR is built without .resolve().
    rel = PurePosixPath(Path(read_path).resolve().relative_to(_BACKEND_DIR).as_posix())
    app_copy = _runtime_copy("app/")
    data_copy = _runtime_copy(f"{rel}/")

    # Assert
    assert (
        app_copy is not None and data_copy is not None
    ), f"runtime stage must COPY {rel}/"
    assert data_copy[1] == app_copy[1].parent / rel


def test_dockerignore_keeps_baked_data_dirs_in_context_when_image_copies_them():
    # Act
    rules = {rule.strip("/") for rule in _dockerignore_rules()}

    # Assert
    assert not rules & {"pptx", "hooks", "hooks/global"}


def test_pptx_reference_files_exist_with_exact_case_when_skills_module_names_them():
    # Arrange — os.listdir returns real names, so a case mismatch fails even on a
    # case-insensitive filesystem.
    source = Path(skills.__file__).read_text(encoding="utf-8")
    named = set(re.findall(r'PPTX_SKILLS_DIR / "([^"]+)"', source))

    # Assert
    assert named
    assert named <= set(os.listdir(skills.PPTX_SKILLS_DIR))


def test_pptx_tool_assets_exist_under_od_root_when_resolved_from_checkout():
    # Act
    root = od_root()

    # Assert
    assert (
        root / "skills" / "pptx-html-fidelity-audit" / "scripts" / "verify_layout.py"
    ).is_file()
    assert (root / "fonts").is_dir()
