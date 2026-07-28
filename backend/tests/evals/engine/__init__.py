"""Pipeline-agnostic engine/capability tests.

Tests here exercise mechanisms used by MULTIPLE pipelines — verified
against production source (grep against agents/workflows/*/workflow.yaml)
before anything lands here, not assumed. Contrast with
tests/evals/workflow/<domain>/<variant>/, which holds tests whose value is
specific to one pipeline's manifest/capabilities.

See tests/evals/PLAN.md's "Amendment 1" for the concrete evidence behind
the two files currently here (test_api_entry_seam.py, formerly "L1";
test_previous_run_context_seed.py, formerly "L3").
"""
