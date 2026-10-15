"""Run one pytest file with agents.execution_engine.engine loaded from HEAD's source
(the working-tree file is untouched). Usage, from backend/: python <this> <test file>"""
import importlib.util
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.getcwd())

import agents.execution_engine  # noqa: F401  parent package first

path = "agents/execution_engine/engine.py"
src = subprocess.check_output(["git", "show", "HEAD:backend/" + path])
spec = importlib.util.spec_from_file_location("agents.execution_engine.engine", path)
mod = importlib.util.module_from_spec(spec)
sys.modules["agents.execution_engine.engine"] = mod
exec(compile(src, path, "exec"), mod.__dict__)
assert "_output_basename and not _materialized" not in src.decode()
sys.exit(pytest.main([*sys.argv[1:], "-q", "-p", "no:cacheprovider"]))
