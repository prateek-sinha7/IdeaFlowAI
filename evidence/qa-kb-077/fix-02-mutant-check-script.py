"""Mutant check for backend/tests/unit/app/test_main.py (ISS-1017). No repo file is edited.

Runs the committed test function twice against the real app.main.app:
  1. as shipped (custom _validation_error_handler from main.py:539)  -> must PASS
  2. mutant: FastAPI's stock request_validation_exception_handler   -> must FAIL (value echoed)
"""
import sys
from types import SimpleNamespace

from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user
from app.main import app
from app.models.database import get_db
from tests.unit.app.test_main import (
    test_validation_error_handler_omits_rejected_value_when_credential_too_short as t,
)

app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1", email="u@example.com")
app.dependency_overrides[get_db] = lambda: None


def run(label):
    try:
        t(TestClient(app))
        print(f"{label}: PASSED")
        return True
    except AssertionError as e:
        print(f"{label}: FAILED -> {str(e).splitlines()[0][:220]}")
        return False


shipped = run("1 shipped handler (main.py:539)")
app.exception_handlers[RequestValidationError] = request_validation_exception_handler
app.middleware_stack = None  # rebuild the stack so the swapped handler table is used
mutant = run("2 mutant: FastAPI stock handler")
print("RESULT:", "test is sensitive to main.py:539" if shipped and not mutant else "NOT SENSITIVE")
sys.exit(0 if shipped and not mutant else 1)
