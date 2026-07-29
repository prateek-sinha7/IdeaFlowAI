"""Eval suite — issue-scoped, offline-by-default evals (see
specs/006-hybrid-eval-suite/quickstart.md + data-model.md).

Every test in this package carries the ``eval`` marker and runs against the
scripted offline harness (``tests/agents/_scripted_model.py``) — zero LLM
tokens by default. Live tests are gated behind ``requires_api_key``.
"""
