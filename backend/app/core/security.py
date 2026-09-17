"""Per-token (jti) revocation lookup.

Password hashing and local JWT issuance/verification were removed in the
Cognito-only auth migration (``.kiro/specs/login/prompt.md`` Phase 1):
Cognito is now the sole authentication authority, so there is no local
credential to hash or verify, and no local JWT to sign or decode. This
module keeps only ``is_token_revoked``, which is provider-agnostic (it looks
up a ``jti`` in the ``revoked_tokens`` table regardless of whether that jti
came from a Cognito access token or, historically, a local one).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type-only import
    from sqlalchemy.orm import Session


def is_token_revoked(jti: str, db: "Session") -> bool:
    """Return True if the given JWT ``jti`` has been explicitly revoked.

    A single source of truth for "is this individual token revoked" — used by
    both the HTTP dependency (`get_current_user`) and the WebSocket handler so
    that revocations are honoured everywhere.

    Args:
        jti: The JWT ID claim to check.
        db: An active SQLAlchemy session.

    Returns:
        True if a row exists in ``revoked_tokens`` for ``jti``, else False.
    """
    # Local import to avoid a circular dependency: revoked_token -> models ->
    # security at module load time.
    from app.models.revoked_token import RevokedToken

    if not jti:
        return False
    return db.query(RevokedToken.id).filter(RevokedToken.jti == jti).first() is not None
