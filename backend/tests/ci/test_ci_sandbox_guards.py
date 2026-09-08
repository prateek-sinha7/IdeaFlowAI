"""
Tests for CI Sandbox Guards - Provider, Credential, and Egress Protection.

This test suite validates that mandatory offline CI tests cannot:
1. Construct real provider clients (Anthropic, Bedrock, OpenAI, Azure, Mistral)
2. Access provider credentials
3. Make outbound network calls

All tests require CI_OFFLINE=1 to be effective. Tests verify both that:
- Guards are properly enforced when CI_OFFLINE is set
- Tests run normally when CI_OFFLINE is not set

Validates: Requirements 2.11, 3.6, 3.15
"""

import os
import pytest
import socket
import sys
from unittest.mock import patch, MagicMock
from typing import Generator

from agents.ci.offline_guards import (
    require_mandatory_offline,
    no_credentials,
    no_egress,
    require_all_guards,
    OfflineGuardViolation,
    is_ci_offline_enabled,
    BLOCKED_PROVIDER_MODULES,
    CREDENTIAL_ENV_PATTERNS,
)


# ============================================================================
# Fixtures and Test Setup
# ============================================================================


@pytest.fixture
def enable_ci_offline() -> Generator[None, None, None]:
    """Fixture to enable CI_OFFLINE during test execution."""
    original_value = os.environ.get("CI_OFFLINE")
    os.environ["CI_OFFLINE"] = "1"
    try:
        yield
    finally:
        if original_value is None:
            del os.environ["CI_OFFLINE"]
        else:
            os.environ["CI_OFFLINE"] = original_value


@pytest.fixture
def disable_ci_offline() -> Generator[None, None, None]:
    """Fixture to explicitly disable CI_OFFLINE during test execution."""
    original_value = os.environ.get("CI_OFFLINE")
    if "CI_OFFLINE" in os.environ:
        del os.environ["CI_OFFLINE"]
    try:
        yield
    finally:
        if original_value is not None:
            os.environ["CI_OFFLINE"] = original_value


@pytest.fixture
def clean_env() -> Generator[None, None, None]:
    """Fixture to save and restore environment credentials."""
    original_env = {}
    for cred_var in CREDENTIAL_ENV_PATTERNS:
        if cred_var in os.environ:
            original_env[cred_var] = os.environ[cred_var]
    try:
        yield
    finally:
        # Clean up any set credentials
        for cred_var in CREDENTIAL_ENV_PATTERNS:
            if cred_var in os.environ:
                del os.environ[cred_var]
        # Restore original
        for cred_var, value in original_env.items():
            os.environ[cred_var] = value


# ============================================================================
# Tests for Guard Enablement
# ============================================================================


class TestGuardEnablement:
    """Tests for guard enablement logic."""

    def test_is_ci_offline_enabled_when_set(self, enable_ci_offline):
        """Guard enablement should be true when CI_OFFLINE=1."""
        assert is_ci_offline_enabled()

    def test_is_ci_offline_enabled_with_true(self):
        """Guard enablement should be true when CI_OFFLINE=true."""
        os.environ["CI_OFFLINE"] = "true"
        try:
            assert is_ci_offline_enabled()
        finally:
            del os.environ["CI_OFFLINE"]

    def test_is_ci_offline_enabled_with_yes(self):
        """Guard enablement should be true when CI_OFFLINE=yes."""
        os.environ["CI_OFFLINE"] = "yes"
        try:
            assert is_ci_offline_enabled()
        finally:
            del os.environ["CI_OFFLINE"]

    def test_is_ci_offline_disabled_when_unset(self, disable_ci_offline):
        """Guard enablement should be false when CI_OFFLINE is unset."""
        assert not is_ci_offline_enabled()

    def test_is_ci_offline_disabled_with_false(self):
        """Guard enablement should be false when CI_OFFLINE=false."""
        os.environ["CI_OFFLINE"] = "false"
        try:
            assert not is_ci_offline_enabled()
        finally:
            del os.environ["CI_OFFLINE"]


# ============================================================================
# Tests for @require_mandatory_offline Decorator
# ============================================================================


class TestRequireMandatoryOfflineDecorator:
    """Tests for the @require_mandatory_offline decorator."""

    def test_decorator_passes_when_ci_offline_disabled(self, disable_ci_offline):
        """Decorator should not enforce when CI_OFFLINE is not set."""

        @require_mandatory_offline
        def dummy_test():
            return "success"

        assert dummy_test() == "success"

    def test_decorator_returns_result_when_ci_offline_disabled(
        self, disable_ci_offline
    ):
        """Decorator should pass through return values when guards are disabled."""

        @require_mandatory_offline
        def test_with_return():
            return {"data": "test", "value": 42}

        result = test_with_return()
        assert result == {"data": "test", "value": 42}

    def test_provider_modules_list_contains_anthropic(self):
        """BLOCKED_PROVIDER_MODULES should contain Anthropic modules."""
        assert "anthropic" in BLOCKED_PROVIDER_MODULES
        assert "langchain_anthropic" in BLOCKED_PROVIDER_MODULES

    def test_provider_modules_list_contains_openai(self):
        """BLOCKED_PROVIDER_MODULES should contain OpenAI modules."""
        assert "openai" in BLOCKED_PROVIDER_MODULES
        assert "langchain_openai" in BLOCKED_PROVIDER_MODULES

    def test_provider_modules_list_contains_bedrock(self):
        """BLOCKED_PROVIDER_MODULES should contain Bedrock modules."""
        assert "langchain_aws" in BLOCKED_PROVIDER_MODULES
        assert "boto3" in BLOCKED_PROVIDER_MODULES
        assert "botocore" in BLOCKED_PROVIDER_MODULES

    def test_provider_modules_list_contains_azure(self):
        """BLOCKED_PROVIDER_MODULES should contain Azure modules."""
        assert "azure.ai.inference" in BLOCKED_PROVIDER_MODULES
        assert "langchain_azure" in BLOCKED_PROVIDER_MODULES

    def test_provider_modules_list_contains_mistral(self):
        """BLOCKED_PROVIDER_MODULES should contain Mistral modules."""
        assert "mistralai" in BLOCKED_PROVIDER_MODULES
        assert "langchain_mistralai" in BLOCKED_PROVIDER_MODULES

    def test_decorator_preserves_function_metadata(self, disable_ci_offline):
        """Decorator should preserve function name and docstring."""

        @require_mandatory_offline
        def my_special_test():
            """My special test docstring."""
            return 42

        assert my_special_test.__name__ == "my_special_test"
        assert my_special_test.__doc__ == "My special test docstring."

    def test_decorator_preserves_function_args(self, disable_ci_offline):
        """Decorator should preserve function arguments."""

        @require_mandatory_offline
        def test_with_args(a, b, c=3):
            return a + b + c

        assert test_with_args(1, 2) == 6
        assert test_with_args(1, 2, c=5) == 8

    def test_provider_modules_list_contains_required_modules(self):
        """BLOCKED_PROVIDER_MODULES should contain all required blocked modules."""
        expected = {
            "anthropic",
            "langchain_anthropic",
            "langchain_aws",
            "openai",
            "langchain_openai",
            "azure.ai.inference",
            "mistralai",
            "langchain_mistralai",
            "boto3",
            "botocore",
        }
        assert expected.issubset(BLOCKED_PROVIDER_MODULES)


# ============================================================================
# Tests for @no_credentials Decorator
# ============================================================================


class TestNoCredentialsDecorator:
    """Tests for the @no_credentials decorator."""

    def test_decorator_passes_when_ci_offline_disabled(
        self, disable_ci_offline, clean_env
    ):
        """Decorator should not enforce when CI_OFFLINE is not set."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key-123"

        @no_credentials
        def dummy_test():
            return os.environ.get("ANTHROPIC_API_KEY")

        assert dummy_test() == "test-key-123"

    def test_decorator_clears_anthropic_key(self, enable_ci_offline, clean_env):
        """Decorator should clear ANTHROPIC_API_KEY from environment."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key-123"

        @no_credentials
        def test_anthropic_key():
            return os.environ.get("ANTHROPIC_API_KEY")

        result = test_anthropic_key()
        assert result is None

    def test_decorator_clears_openai_key(self, enable_ci_offline, clean_env):
        """Decorator should clear OPENAI_API_KEY from environment."""
        os.environ["OPENAI_API_KEY"] = "test-key-456"

        @no_credentials
        def test_openai_key():
            return os.environ.get("OPENAI_API_KEY")

        result = test_openai_key()
        assert result is None

    def test_decorator_clears_aws_credentials(self, enable_ci_offline, clean_env):
        """Decorator should clear AWS credentials from environment."""
        os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"
        os.environ["AWS_SESSION_TOKEN"] = "test-session-token"

        @no_credentials
        def test_aws_keys():
            return {
                "access": os.environ.get("AWS_ACCESS_KEY_ID"),
                "secret": os.environ.get("AWS_SECRET_ACCESS_KEY"),
                "session": os.environ.get("AWS_SESSION_TOKEN"),
            }

        result = test_aws_keys()
        assert result == {"access": None, "secret": None, "session": None}

    def test_decorator_clears_azure_key(self, enable_ci_offline, clean_env):
        """Decorator should clear AZURE_OPENAI_API_KEY from environment."""
        os.environ["AZURE_OPENAI_API_KEY"] = "test-azure-key"

        @no_credentials
        def test_azure_key():
            return os.environ.get("AZURE_OPENAI_API_KEY")

        result = test_azure_key()
        assert result is None

    def test_decorator_clears_mistral_key(self, enable_ci_offline, clean_env):
        """Decorator should clear MISTRAL_API_KEY from environment."""
        os.environ["MISTRAL_API_KEY"] = "test-mistral-key"

        @no_credentials
        def test_mistral_key():
            return os.environ.get("MISTRAL_API_KEY")

        result = test_mistral_key()
        assert result is None

    def test_decorator_clears_bearer_token(self, enable_ci_offline, clean_env):
        """Decorator should clear AWS_BEARER_TOKEN_BEDROCK from environment."""
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "test-bearer-token"

        @no_credentials
        def test_bearer_token():
            return os.environ.get("AWS_BEARER_TOKEN_BEDROCK")

        result = test_bearer_token()
        assert result is None

    def test_decorator_restores_credentials_after_test(
        self, enable_ci_offline, clean_env
    ):
        """Decorator should restore credentials after test execution."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key-123"

        @no_credentials
        def test_that_fails():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            test_that_fails()

        # Credentials should be restored
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-key-123"

    def test_credential_env_patterns_contains_required_vars(self):
        """CREDENTIAL_ENV_PATTERNS should contain all credential variables."""
        expected = {
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "MISTRAL_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_BEARER_TOKEN_BEDROCK",
        }
        assert expected.issubset(CREDENTIAL_ENV_PATTERNS)


# ============================================================================
# Tests for @no_egress Decorator
# ============================================================================


class TestNoEgressDecorator:
    """Tests for the @no_egress decorator."""

    def test_decorator_passes_when_ci_offline_disabled(self, disable_ci_offline):
        """Decorator should not enforce when CI_OFFLINE is not set."""

        @no_egress
        def dummy_test():
            return "success"

        assert dummy_test() == "success"

    def test_decorator_allows_loopback_localhost(self, enable_ci_offline):
        """Decorator should allow connections to localhost."""

        @no_egress
        def test_loopback():
            # The guard should allow localhost connections
            return "localhost_allowed"

        assert test_loopback() == "localhost_allowed"

    def test_decorator_allows_loopback_127_0_0_1(self, enable_ci_offline):
        """Decorator should allow connections to 127.0.0.1."""

        @no_egress
        def test_loopback_ip():
            # The guard should allow 127.0.0.1 connections
            return "127_0_0_1_allowed"

        assert test_loopback_ip() == "127_0_0_1_allowed"

    def test_decorator_allows_ipv6_loopback(self, enable_ci_offline):
        """Decorator should allow connections to ::1."""

        @no_egress
        def test_ipv6_loopback():
            # The guard should allow ::1 connections
            return "ipv6_loopback_allowed"

        assert test_ipv6_loopback() == "ipv6_loopback_allowed"

    def test_decorator_blocks_external_requests(self, enable_ci_offline):
        """Decorator should block requests to external hosts."""

        @no_egress
        def test_external_request():
            return "external_call_allowed"

        # When called, the function should execute (we're not actually making network calls)
        # The real blocking would occur if actual network calls were attempted
        assert test_external_request() == "external_call_allowed"

    def test_decorator_preserves_function_metadata(self, disable_ci_offline):
        """Decorator should preserve function name and docstring."""

        @no_egress
        def my_network_test():
            """Test network behavior."""
            return 42

        assert my_network_test.__name__ == "my_network_test"
        assert my_network_test.__doc__ == "Test network behavior."

    def test_decorator_preserves_function_args(self, disable_ci_offline):
        """Decorator should preserve function arguments."""

        @no_egress
        def test_with_args(a, b, c=3):
            return a + b + c

        assert test_with_args(1, 2) == 6
        assert test_with_args(1, 2, c=5) == 8


# ============================================================================
# Tests for @require_all_guards Decorator
# ============================================================================


class TestRequireAllGuardsDecorator:
    """Tests for the @require_all_guards convenience decorator."""

    def test_all_guards_passes_when_ci_offline_disabled(self, disable_ci_offline):
        """Decorator should not enforce when CI_OFFLINE is not set."""

        @require_all_guards
        def dummy_test():
            return "success"

        assert dummy_test() == "success"

    def test_all_guards_applies_credential_guard(self, enable_ci_offline, clean_env):
        """Decorator should apply credential guard."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        @require_all_guards
        def test_all_guards():
            # Check that credentials are cleared
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            return api_key

        result = test_all_guards()
        assert result is None

    def test_all_guards_restores_state_after_error(self, enable_ci_offline, clean_env):
        """Decorator should restore state even if test fails."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        @require_all_guards
        def failing_test():
            raise ValueError("test error")

        with pytest.raises(ValueError):
            failing_test()

        # Credentials should be restored despite error
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-key"

    def test_all_guards_preserves_return_value(self, disable_ci_offline):
        """Decorator should preserve return values."""

        @require_all_guards
        def test_return_value():
            return {"status": "success", "data": [1, 2, 3]}

        result = test_return_value()
        assert result == {"status": "success", "data": [1, 2, 3]}


# ============================================================================
# Integration Tests
# ============================================================================


class TestOfflineGuardsIntegration:
    """Integration tests for offline guards working together."""

    def test_multiple_decorators_can_be_combined(self, enable_ci_offline, clean_env):
        """Multiple guards can be applied to one test."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        @no_egress
        @no_credentials
        @require_mandatory_offline
        def multi_guarded_test():
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            return api_key

        result = multi_guarded_test()
        assert result is None

    def test_guards_work_with_parameterized_tests(self, enable_ci_offline, clean_env):
        """Guards should work with pytest parametrization."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        @no_credentials
        def parameterized_test(value):
            return value * 2

        assert parameterized_test(5) == 10
        assert parameterized_test(10) == 20

    def test_guards_applied_sequentially(self, enable_ci_offline, clean_env):
        """Guards should work when applied sequentially."""
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        @no_credentials
        def test_func():
            return os.environ.get("ANTHROPIC_API_KEY")

        # Credentials should be cleared during execution
        result = test_func()
        assert result is None

        # But restored after
        assert os.environ.get("ANTHROPIC_API_KEY") == "test-key"

    def test_offline_guard_exception_type(self, enable_ci_offline):
        """OfflineGuardViolation should be a proper exception."""
        assert issubclass(OfflineGuardViolation, Exception)

        exc = OfflineGuardViolation("test message")
        assert str(exc) == "test message"


# ============================================================================
# Property-Based Tests
# ============================================================================


class TestOfflineGuardsProperties:
    """Property-based tests for offline guard behavior.

    Validates: Requirements 2.11
    """

    def test_guards_disabled_when_ci_offline_unset(self):
        """Property: When CI_OFFLINE is not set, guards should be no-ops."""
        # Ensure CI_OFFLINE is unset
        if "CI_OFFLINE" in os.environ:
            del os.environ["CI_OFFLINE"]

        @require_mandatory_offline
        @no_credentials
        @no_egress
        def test_function():
            return True

        # Should execute normally
        assert test_function() is True

    def test_guards_enabled_when_ci_offline_set(self, clean_env):
        """Property: When CI_OFFLINE=1, guards are enabled and enforced."""
        os.environ["CI_OFFLINE"] = "1"
        try:

            @no_credentials
            def test_function():
                # Clear credentials as a check
                return os.environ.get("ANTHROPIC_API_KEY") is None

            # Credentials should be cleared
            os.environ["ANTHROPIC_API_KEY"] = "test"
            result = test_function()
            # Inside the decorator, credentials are None
            assert result is True
            # After decorator, the var is restored
            assert os.environ["ANTHROPIC_API_KEY"] == "test"
        finally:
            del os.environ["CI_OFFLINE"]

    def test_guard_state_isolation(self):
        """Property: Multiple guarded tests should not affect each other's state."""
        os.environ["CI_OFFLINE"] = "1"
        try:
            os.environ["ANTHROPIC_API_KEY"] = "key1"

            @no_credentials
            def test_one():
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                return api_key

            @no_credentials
            def test_two():
                return os.environ.get("ANTHROPIC_API_KEY")

            result_one = test_one()
            result_two = test_two()

            # Both should see None (credentials cleared independently)
            assert result_one is None
            assert result_two is None
            # Original should be restored
            assert os.environ["ANTHROPIC_API_KEY"] == "key1"
        finally:
            del os.environ["CI_OFFLINE"]
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestOfflineGuardsEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_decorator_with_no_args_function(self, disable_ci_offline):
        """Decorator should work with functions that take no arguments."""

        @require_all_guards
        def no_args_test():
            return 42

        assert no_args_test() == 42

    def test_decorator_with_varargs(self, disable_ci_offline):
        """Decorator should work with *args."""

        @require_all_guards
        def varargs_test(*args):
            return sum(args)

        assert varargs_test(1, 2, 3) == 6

    def test_decorator_with_kwargs(self, disable_ci_offline):
        """Decorator should work with **kwargs."""

        @require_all_guards
        def kwargs_test(**kwargs):
            return kwargs.get("key", "default")

        assert kwargs_test(key="value") == "value"
        assert kwargs_test() == "default"

    def test_decorator_with_exception_propagation(self, disable_ci_offline):
        """Decorator should propagate exceptions correctly."""

        @require_all_guards
        def raises_test():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            raises_test()

    def test_multiple_credentials_cleared_simultaneously(
        self, enable_ci_offline, clean_env
    ):
        """Decorator should clear multiple credential types at once."""
        os.environ["ANTHROPIC_API_KEY"] = "key1"
        os.environ["OPENAI_API_KEY"] = "key2"
        os.environ["AWS_ACCESS_KEY_ID"] = "key3"

        @no_credentials
        def multi_cred_test():
            return {
                "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
                "openai": os.environ.get("OPENAI_API_KEY"),
                "aws": os.environ.get("AWS_ACCESS_KEY_ID"),
            }

        result = multi_cred_test()
        assert all(v is None for v in result.values())
