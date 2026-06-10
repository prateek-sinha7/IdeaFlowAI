"""A tiny passing test for the fixture module — the code_test target.

Kept deliberately small (RESEARCH Pitfall 2: pytest-inside-pytest). It imports the
sibling module by relative path so ``pytest .`` from the fixture root collects it
with no package install.
"""

from calc import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(4, 5) == 20
