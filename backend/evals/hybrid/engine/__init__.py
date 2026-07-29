"""Pipeline-agnostic engine/capability tests.

Tests here exercise mechanisms used by MULTIPLE pipelines — verified
against production source (grep against agents/workflows/*/workflow.yaml)
before anything lands here, not assumed. Contrast with
evals/hybrid/workflow/<domain>/<variant>/, which holds tests whose value is
specific to one pipeline's manifest/capabilities.

The membership rule is specified in specs/006-hybrid-eval-suite/quickstart.md
("Rules that keep this suite trustworthy"). The two files currently here are
test_api_entry_seam.py and test_previous_run_context_seed.py.
"""
