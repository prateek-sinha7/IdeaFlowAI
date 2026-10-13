"""AWS's documentation example credentials pass the secret scan; real-shaped keys still block."""

from agents.capabilities.hooks.secret_scan import scan_for_secret


def test_aws_documentation_examples_pass():
    # Run 3976f8ce: an API spec's "example" field carried these and degraded the run.
    payload = (
        '{"example": "AKIAIOSFODNN7EXAMPLE"}\n'
        'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"\n'
        'access_key: "AKIAIOSFODNN7EXAMPLE"\n'
    )
    assert scan_for_secret(payload) is None


def test_a_real_shaped_access_key_still_blocks():
    assert scan_for_secret('{"key": "AKIAQ3EGRL7ZXBV2WK4P"}') == "AKIAQ3EGRL7ZXBV2"


def test_a_real_key_next_to_the_example_still_blocks():
    assert (
        scan_for_secret("AKIAIOSFODNN7EXAMPLE AKIAQ3EGRL7ZXBV2WK4P")
        == "AKIAQ3EGRL7ZXBV2"
    )


def test_a_real_secret_assignment_still_blocks():
    assert (
        scan_for_secret('secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYREALKEY1"') is not None
    )
