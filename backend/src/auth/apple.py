"""Apple Sign-In verification."""

from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient
from pydantic import BaseModel


APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


class AppleTokenClaims(BaseModel):
    """Claims extracted from a verified Apple identity token."""

    sub: str  # Apple's unique user identifier (stable across devices)
    email: Optional[str] = None  # May be hidden by user
    email_verified: Optional[bool] = None


async def verify_apple_identity_token(
    identity_token: str,
    bundle_ids: list[str],
) -> Optional[AppleTokenClaims]:
    """Verify an Apple Sign-In identity token.

    This validates the JWT token from Apple Sign-In by:
    1. Fetching Apple's public keys
    2. Verifying the JWT signature
    3. Checking the audience (bundle ID) and issuer

    Args:
        identity_token: The JWT identity token from Apple Sign-In.
        bundle_ids: List of allowed app bundle IDs (token's audience must match one).

    Returns:
        AppleTokenClaims if the token is valid, None otherwise.
    """
    try:
        # Fetch Apple's public keys
        jwks_client = PyJWKClient(APPLE_KEYS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(identity_token)

        # Verify and decode the token
        payload = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=bundle_ids,
            issuer=APPLE_ISSUER,
        )

        return AppleTokenClaims(
            sub=payload["sub"],
            email=payload.get("email"),
            email_verified=payload.get("email_verified"),
        )
    except Exception as e:
        print(f"[Auth] Apple token verification failed: {e}")
        return None
