"""Test prompt_policy validation at load time.

Covers Requirement 29 AC1: prompt_policy must be validated against registered
prompt-policy names from CapabilityRegistry at LOAD time, not at dispatch time.
Unknown → AgentSpecError naming the file and the allowed names.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest

from agents.loader import AgentSpecError, load_agent_spec


class TestPromptPolicyValidation:
    """Requirement 29: prompt_policy validation at load time."""

    def test_unknown_prompt_policy_raises_error(self) -> None:
        """Unknown prompt_policy name raises AgentSpecError with allowed names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create a temporary agent directory with an unknown prompt_policy
            agent_dir = tmppath / "test-agent"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-agent
                name: Test Agent
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                prompt_policy: unknown_policy
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            # Monkeypatch PROMPTS_DIR to the temp directory
            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                with pytest.raises(AgentSpecError) as exc_info:
                    load_agent_spec("test-agent")

                error_msg = str(exc_info.value)
                assert "unknown_policy" in error_msg
                assert "not a registered prompt policy" in error_msg
                assert "Allowed values:" in error_msg
                # Should list the registered policies
                assert "default" in error_msg
                assert "body_only" in error_msg
                assert "governance" in error_msg
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_default_prompt_policy_loads_successfully(self) -> None:
        """Registered prompt_policy 'default' loads without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            agent_dir = tmppath / "test-default-policy"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-default-policy
                name: Test Default Policy
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                prompt_policy: default
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                spec = load_agent_spec("test-default-policy")
                assert spec.prompt_policy == "default"
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_body_only_prompt_policy_loads_successfully(self) -> None:
        """Registered prompt_policy 'body_only' loads without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            agent_dir = tmppath / "test-body-only-policy"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-body-only-policy
                name: Test Body Only Policy
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                prompt_policy: body_only
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                spec = load_agent_spec("test-body-only-policy")
                assert spec.prompt_policy == "body_only"
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_governance_prompt_policy_loads_successfully(self) -> None:
        """Registered prompt_policy 'governance' loads without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            agent_dir = tmppath / "test-governance-policy"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-governance-policy
                name: Test Governance Policy
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                prompt_policy: governance
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                spec = load_agent_spec("test-governance-policy")
                assert spec.prompt_policy == "governance"
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_absent_prompt_policy_loads_as_none(self) -> None:
        """Absent prompt_policy field loads as None (no validation required)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            agent_dir = tmppath / "test-no-policy"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-no-policy
                name: Test No Policy
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                spec = load_agent_spec("test-no-policy")
                assert spec.prompt_policy is None
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_error_message_lists_all_allowed_names(self) -> None:
        """Error message for unknown policy lists all registered names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            agent_dir = tmppath / "test-error-msg"
            agent_dir.mkdir()
            agent_file = agent_dir / "AGENT.md"

            agent_md = dedent(
                """
                ---
                id: test-error-msg
                name: Test Error Message
                role: A test agent
                pipeline_type: test_pipeline
                order: 1
                max_tokens: 1000
                prompt_policy: invalid_policy_name
                ---

                You are a test agent.
                """
            ).lstrip()

            agent_file.write_text(agent_md)

            import agents.loader as loader_module

            original_prompts_dir = loader_module._PROMPTS_DIR
            try:
                loader_module._PROMPTS_DIR = tmppath
                loader_module._SPEC_CACHE.clear()

                with pytest.raises(AgentSpecError) as exc_info:
                    load_agent_spec("test-error-msg")

                error_msg = str(exc_info.value)
                # Should mention the file path
                assert "test-error-msg" in error_msg or "AGENT.md" in error_msg
                # Should list the invalid name
                assert "invalid_policy_name" in error_msg
                # Should mention allowed values
                assert "Allowed values:" in error_msg
            finally:
                loader_module._PROMPTS_DIR = original_prompts_dir
                loader_module._SPEC_CACHE.clear()

    def test_bogus_policy_on_real_agent_fails_the_process_first_import(self) -> None:
        """Reproduces the REAL first `import agents.loader` in a fresh process.

        The prior fix only ever validated a synthetic temp-dir agent loaded
        AFTER `agents.loader` had already finished importing — the circular-
        import window (agents.capabilities.registry -> agents.registry ->
        `from agents.loader import SUPPORTED_PIPELINE_TYPES`) that swallows
        validation for every REAL AGENT.md scanned during this module's own
        bootstrap discovery was never exercised. Plant a bogus-policy AGENT.md
        directly under the real agents/prompts/ dir and import agents.loader
        fresh in a subprocess: that must fail, not silently cache the spec.
        """
        backend_root = Path(__file__).resolve().parents[2]
        bogus_dir = backend_root / "agents" / "prompts" / "__test_bogus_prompt_policy_agent__"
        assert not bogus_dir.exists(), f"stale fixture dir from a prior run: {bogus_dir}"
        bogus_dir.mkdir()
        try:
            (bogus_dir / "AGENT.md").write_text(
                dedent(
                    """
                    ---
                    id: __test_bogus_prompt_policy_agent__
                    name: Bogus Policy Agent
                    role: A test agent
                    pipeline_type: test_pipeline
                    order: 1
                    max_tokens: 1000
                    prompt_policy: totally_bogus_policy_xyz
                    ---

                    You are a test agent.
                    """
                ).lstrip()
            )

            result = subprocess.run(
                [sys.executable, "-c", "import agents.loader"],
                cwd=str(backend_root),
                capture_output=True,
                text=True,
                timeout=60,
            )

            assert result.returncode != 0, (
                "expected `import agents.loader` to fail on a real bogus "
                f"prompt_policy; stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            assert "AgentSpecError" in result.stderr
            assert "totally_bogus_policy_xyz" in result.stderr
            assert "__test_bogus_prompt_policy_agent__" in result.stderr
        finally:
            shutil.rmtree(bogus_dir)
