"""Canonicalization policy for case-insensitive email identity aliases."""

from __future__ import annotations


def canonicalize_email(value: str) -> str:
    """Return the canonical email alias used for application identity matching.

    The application treats email sign-in aliases as case-insensitive. This helper
    normalizes only the alias value; the immutable Cognito ``sub`` remains the
    authoritative account identity.
    """
    return value.strip().lower()
