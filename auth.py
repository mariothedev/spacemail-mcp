"""Validate locally issued HS256 bearer tokens."""

import logging

import jwt
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)
SCOPES = ("spacemail:read", "spacemail:send", "spacemail:delete")


class JWTTokenVerifier:
    def __init__(self, secret: str, issuer: str, audience: str):
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes; use a random secret")
        if not issuer or not audience:
            raise ValueError("JWT issuer and audience must not be empty")
        self.secret = secret
        self.issuer = issuer
        self.audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub", "iat"]},
            )
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                return None
            return AccessToken(
                token=token,
                client_id=claims["sub"],
                subject=claims["sub"],
                scopes=scope.split(),
                expires_at=claims["exp"],
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            # Never log tokens or decoded claims.
            logger.warning("Rejected invalid access token")
            return None
