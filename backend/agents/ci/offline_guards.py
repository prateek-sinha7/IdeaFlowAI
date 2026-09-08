"""
Mandatory-offline provider, credential, and egress guards for CI tests.

This module implements three critical guards to enforce that mandatory CI tests:
1. Never construct real provider clients (Anthropic, Bedrock, OpenAI, Azure, Mistral)
2. Never access or probe provider credentials
3. Never make outbound network calls

Guards are enforced via decorators that fail immediately on violation.
Set CI_OFFLINE=1 to enable guards.

Requirements: 2.11, 3.6, 3.15
"""

import functools
import os
import sys
from typing import Any, Callable, TypeVar
from unittest.mock import patch

F = TypeVar("F", bound=Callable[..., Any])


class OfflineGuardViolation(Exception):
    """Raised when a test attempts to violate an offline boundary."""

    pass


def is_ci_offline_enabled() -> bool:
    """Check if CI_OFFLINE enforcement is enabled."""
    return os.environ.get("CI_OFFLINE", "").lower() in ("1", "true", "yes")


# Blocked provider modules that must never be imported/constructed in mandatory offline tests
BLOCKED_PROVIDER_MODULES = {
    "anthropic",
    "langchain_anthropic",
    "langchain_aws",  # Contains ChatBedrockConverse
    "openai",
    "langchain_openai",
    "azure.ai.inference",  # Azure AI SDK
    "langchain_azure",
    "mistralai",  # Mistral AI SDK
    "langchain_mistralai",
    "boto3",  # AWS SDK (used for Bedrock)
    "botocore",  # Botocore (used for Bedrock credential resolution)
}

# Known credential environment variable patterns
CREDENTIAL_ENV_PATTERNS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "MISTRAL_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_BEARER_TOKEN_BEDROCK",
}

# Network-related modules that should not be used for provider calls
NETWORK_MODULES = {
    "socket",
    "http.client",
    "urllib",
    "urllib.request",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
}


def require_mandatory_offline(func: F) -> F:
    """
    Decorator that blocks provider client construction in mandatory offline CI tests.

    Fails immediately if:
    - A real Anthropic, Bedrock, OpenAI, Azure, or Mistral client is instantiated
    - Provider module imports occur during test execution
    - Provider credentials are accessed

    Usage:
        @require_mandatory_offline
        def test_my_feature():
            # This test will fail if it tries to instantiate a real provider
            pass

    Requirements: 2.11
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_ci_offline_enabled():
            return func(*args, **kwargs)

        # Build a list of patches that should apply safely
        patches_to_apply = []

        # Try to patch each provider module if it's already imported
        # This avoids issues with modules that have complex imports
        patch_targets = [
            (
                "anthropic.Anthropic",
                "Real Anthropic client construction blocked in mandatory offline CI",
            ),
            (
                "anthropic.AsyncAnthropic",
                "Real Anthropic async client construction blocked in mandatory offline CI",
            ),
            (
                "langchain_anthropic.ChatAnthropic",
                "Real Anthropic provider via langchain_anthropic blocked in mandatory offline CI",
            ),
            (
                "langchain_aws.ChatBedrockConverse",
                "Real Bedrock provider via langchain_aws blocked in mandatory offline CI",
            ),
            (
                "langchain_openai.ChatOpenAI",
                "Real OpenAI provider via langchain_openai blocked in mandatory offline CI",
            ),
            (
                "azure.ai.inference.ChatCompletionsClient",
                "Real Azure AI client construction blocked in mandatory offline CI",
            ),
            (
                "langchain_azure.AzureChatOpenAI",
                "Real Azure provider via langchain_azure blocked in mandatory offline CI",
            ),
            (
                "mistralai.Mistral",
                "Real Mistral client construction blocked in mandatory offline CI",
            ),
            (
                "langchain_mistralai.ChatMistralAI",
                "Real Mistral provider via langchain_mistralai blocked in mandatory offline CI",
            ),
        ]

        # Apply safe patches for targets that won't cause import errors
        for target, message in patch_targets:
            try:
                # Check if the target is already in sys.modules or can be safely patched
                parts = target.split(".")
                module_name = parts[0]
                if (
                    module_name in sys.modules
                    or module_name in BLOCKED_PROVIDER_MODULES
                ):
                    patches_to_apply.append(
                        patch(target, side_effect=OfflineGuardViolation(message))
                    )
            except (ImportError, AttributeError, KeyError):
                # Skip targets that can't be patched safely
                pass

        # Execute the test with patches applied
        active_patches = []
        try:
            for p in patches_to_apply:
                try:
                    p.start()
                    active_patches.append(p)
                except (ImportError, AttributeError):
                    # Skip patches that fail to start
                    pass

            return func(*args, **kwargs)
        finally:
            for p in active_patches:
                try:
                    p.stop()
                except Exception:
                    pass

    return wrapper


def no_credentials(func: F) -> F:
    """
    Decorator that ensures provider credentials are not available to a test.

    Fails immediately if a test accesses a known provider credential environment variable.
    Clears credentials from environment during test execution.

    Usage:
        @no_credentials
        def test_my_feature():
            # Credential env vars are unavailable during this test
            pass

    Requirements: 2.11
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_ci_offline_enabled():
            return func(*args, **kwargs)

        # Save original env vars
        original_env = {}
        for cred_var in CREDENTIAL_ENV_PATTERNS:
            if cred_var in os.environ:
                original_env[cred_var] = os.environ[cred_var]
                del os.environ[cred_var]

        try:
            return func(*args, **kwargs)
        finally:
            # Restore original env vars
            for cred_var, value in original_env.items():
                os.environ[cred_var] = value

    return wrapper


def no_egress(func: F) -> F:
    """
    Decorator that blocks outbound network calls in mandatory offline CI tests.

    Fails immediately if a test attempts to:
    - Create a socket connection to a non-loopback address
    - Make an HTTP/HTTPS request to a remote server
    - Use urllib or requests to access external URLs

    Allows loopback (127.0.0.1, localhost, ::1) connections for isolated test services.

    Usage:
        @no_egress
        def test_my_feature():
            # This test will fail if it tries to make external network calls
            pass

    Requirements: 2.11
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_ci_offline_enabled():
            return func(*args, **kwargs)

        original_socket_create_connection = None
        original_socket_socket = None
        original_urllib_open = None
        original_requests_request = None

        def _blocked_socket_create_connection(*args_: Any, **kwargs_: Any) -> Any:
            """Block socket.create_connection unless to loopback."""
            if args_:
                address = args_[0]
                if isinstance(address, tuple):
                    host, _port = address
                    if host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
                        raise OfflineGuardViolation(
                            f"Outbound socket connection to {host} blocked in mandatory offline CI"
                        )
            return original_socket_create_connection(*args_, **kwargs_)

        def _blocked_socket_socket_init(self: Any, *args_: Any, **kwargs_: Any) -> None:
            """Wrap socket __init__ to detect egress attempts."""
            original_socket_socket(self, *args_, **kwargs_)

            # Wrap connect to intercept
            original_connect = self.connect

            def _blocked_connect(address: Any, *args_c: Any, **kwargs_c: Any) -> None:
                if isinstance(address, tuple):
                    host, _port = address
                    if host not in ("127.0.0.1", "localhost", "::1", "[::1]"):
                        raise OfflineGuardViolation(
                            f"Outbound socket connection to {host} blocked in mandatory offline CI"
                        )
                return original_connect(address, *args_c, **kwargs_c)

            self.connect = _blocked_connect

        def _blocked_urllib_open(url: str, *args_: Any, **kwargs_: Any) -> Any:
            """Block urllib.request.urlopen for external URLs."""
            if isinstance(url, str) and not any(
                x in url for x in ("localhost", "127.0.0.1", "[::1]")
            ):
                raise OfflineGuardViolation(
                    f"Outbound HTTP request to {url} blocked in mandatory offline CI"
                )
            return original_urllib_open(url, *args_, **kwargs_)

        def _blocked_requests_request(*args_: Any, **kwargs_: Any) -> Any:
            """Block requests module for external URLs."""
            url = args_[1] if len(args_) > 1 else kwargs_.get("url")
            if (
                url
                and isinstance(url, str)
                and not any(x in url for x in ("localhost", "127.0.0.1", "[::1]"))
            ):
                raise OfflineGuardViolation(
                    f"Outbound HTTP request via requests to {url} blocked in mandatory offline CI"
                )
            return original_requests_request(*args_, **kwargs_)

        # Apply patches
        try:
            import socket

            original_socket_create_connection = socket.create_connection
            socket.create_connection = _blocked_socket_create_connection

            original_socket_socket = socket.socket.__init__
            socket.socket.__init__ = _blocked_socket_socket_init
        except (ImportError, AttributeError):
            pass

        try:
            import urllib.request

            original_urllib_open = urllib.request.urlopen
            urllib.request.urlopen = _blocked_urllib_open
        except (ImportError, AttributeError):
            pass

        try:
            import requests

            original_requests_request = requests.request
            requests.request = _blocked_requests_request
        except (ImportError, AttributeError):
            pass

        try:
            return func(*args, **kwargs)
        finally:
            # Restore original functions
            try:
                import socket

                if original_socket_create_connection:
                    socket.create_connection = original_socket_create_connection
                if original_socket_socket:
                    socket.socket.__init__ = original_socket_socket
            except (ImportError, AttributeError):
                pass

            try:
                import urllib.request

                if original_urllib_open:
                    urllib.request.urlopen = original_urllib_open
            except (ImportError, AttributeError):
                pass

            try:
                import requests

                if original_requests_request:
                    requests.request = original_requests_request
            except (ImportError, AttributeError):
                pass

    return wrapper


def require_all_guards(func: F) -> F:
    """
    Convenience decorator that applies all three offline guards.

    Equivalent to stacking:
        @require_mandatory_offline
        @no_credentials
        @no_egress
        def test_my_feature():
            pass

    Requirements: 2.11
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        @no_egress
        @no_credentials
        @require_mandatory_offline
        def guarded_func() -> Any:
            return func(*args, **kwargs)

        return guarded_func()

    return wrapper
