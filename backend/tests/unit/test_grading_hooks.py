"""Unit tests for evals.grading.hooks — path-addressed hook loading.

Covers resolution relative to the declaring config file (sibling, subdirectory,
absolute), the failure modes that must raise ValueError naming the file and the
function, and the real rubric/validate pair shipped under `grading/model/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.grading.hooks import load_callable

HOOK_SOURCE = """
def check(response):
    return True, f"saw {response}"
"""

REAL_WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2]
    / "evals"
    / "grading"
    / "model"
    / "workflows"
    / "prototype"
)


def write_hook(path: Path, source: str = HOOK_SOURCE) -> Path:
    """Write a throwaway hook file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


def test_resolves_sibling_file(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "validate.py")

    function = load_callable("./validate.py:check", relative_to=config)

    assert function("spec") == (True, "saw spec")


def test_resolves_from_subdirectory(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "sub" / "x.py")

    function = load_callable("./sub/x.py:check", relative_to=config)

    assert function("spec") == (True, "saw spec")


def test_resolves_absolute_path(tmp_path):
    config = tmp_path / "configs" / "rubric.yaml"
    config.parent.mkdir()
    config.write_text("agent_id: x")
    hook = write_hook(tmp_path / "elsewhere" / "validate.py")

    function = load_callable(f"{hook}:check", relative_to=config)

    assert function("spec") == (True, "saw spec")


def test_returned_object_is_the_source_definition(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "validate.py", "def adapt(text):\n    return text.upper()\n")

    function = load_callable("./validate.py:adapt", relative_to=config)

    assert callable(function)
    assert function.__name__ == "adapt"
    assert function("abc") == "ABC"


def test_missing_file_raises_naming_the_file(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")

    with pytest.raises(ValueError) as error:
        load_callable("./absent.py:check", relative_to=config)

    assert "absent.py" in str(error.value)
    assert "check" in str(error.value)


def test_missing_function_raises_naming_the_function(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "validate.py")

    with pytest.raises(ValueError) as error:
        load_callable("./validate.py:absent_function", relative_to=config)

    assert "absent_function" in str(error.value)
    assert "validate.py" in str(error.value)


def test_invalid_python_raises_naming_the_file(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "broken.py", "def check(:\n")

    with pytest.raises(ValueError) as error:
        load_callable("./broken.py:check", relative_to=config)

    assert "broken.py" in str(error.value)
    assert "check" in str(error.value)


def test_non_callable_attribute_raises(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "validate.py", "check = 42\n")

    with pytest.raises(ValueError) as error:
        load_callable("./validate.py:check", relative_to=config)

    assert "not callable" in str(error.value)


@pytest.mark.parametrize("reference", ["./validate.py", "check", "", ":check", "./x.py:"])
def test_malformed_reference_raises(tmp_path, reference):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")

    with pytest.raises(ValueError) as error:
        load_callable(reference, relative_to=config)

    assert "malformed" in str(error.value)


def test_loading_the_same_file_twice_returns_working_callables(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "validate.py")

    first = load_callable("./validate.py:check", relative_to=config)
    second = load_callable("./validate.py:check", relative_to=config)

    assert first("a") == (True, "saw a")
    assert second("b") == (True, "saw b")


def test_two_hooks_with_the_same_basename_do_not_collide(tmp_path):
    config = tmp_path / "rubric.yaml"
    config.write_text("agent_id: x")
    write_hook(tmp_path / "one" / "validate.py", "def check(text):\n    return 'one'\n")
    write_hook(tmp_path / "two" / "validate.py", "def check(text):\n    return 'two'\n")

    first = load_callable("./one/validate.py:check", relative_to=config)
    second = load_callable("./two/validate.py:check", relative_to=config)

    assert first("x") == "one"
    assert second("x") == "two"


def test_resolves_the_real_prototype_specify_validate_hook():
    """The shipped rubric declares `./prototype_specify_validate.py:check`."""
    rubric = REAL_WORKFLOW_DIR / "prototype_specify_rubric.yaml"

    check = load_callable(
        "./prototype_specify_validate.py:check", relative_to=rubric
    )
    passed, reason = check("no nav table here")

    assert isinstance(passed, bool)
    assert isinstance(reason, str)
    assert passed is False
