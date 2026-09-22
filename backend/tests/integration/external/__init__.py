"""Integration tests that drive a real external binary or stubbed third-party service.

Anything in here shells out to, or speaks a wire protocol with, a process outside the
pytest interpreter (a stdio MCP server, a CLI tool). LLM providers stay faked — live
provider calls belong in ``tests/e2e/``.
"""
