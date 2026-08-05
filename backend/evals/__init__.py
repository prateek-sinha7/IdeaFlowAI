"""Evaluation tooling that is not a test suite.

`grading/` runs real agents and grades their output — it spends money, produces
artifacts, and is invoked deliberately by a developer. It lives here rather than
under `tests/` so `pytest testpaths=["tests"]` never walks it; its own unit
tests live in `tests/unit/test_grading_*.py`.
"""
