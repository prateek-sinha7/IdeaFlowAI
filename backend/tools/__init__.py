"""Development- and CI-time tooling for the backend.

Nothing in here is part of the running service. `app/` and `agents/` must never
import from this package: it is invoked by GitHub Actions (`python -m
tools.ci.ci_gate ...`), by `backend/tests/`, and from the command line. The
production container image does not copy it (see `backend/Dockerfile`), which is
why its dependencies — `defusedxml`, for one — live in the dev dependency group
only.

Subpackages:
- `ci`: CI signal registry, evidence manifests, coverage/scanner verdict gates,
  test-inventory accounting, and the toolchain pin authority.
"""
