"""Validate Authentik-issued RS256 bearer tokens."""

import logging

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)
SCOPES = ("spacemail:read", "spacemail:send", "spacemail:delete")


class AuthentikTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str):
        if not issuer or not audience or not jwks_url:
            raise ValueError("Authentik issuer, audience and JWKS URL must not be empty")
        self.issuer = issuer
        self.audience = audience
        self.jwks = PyJWKClient(jwks_url)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                return None
            return AccessToken(
                token=token,
                client_id=claims.get("azp", claims["sub"]),
                subject=claims["sub"],
                scopes=scope.split(),
                expires_at=claims["exp"],
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            # Never log tokens or decoded claims.
            logger.warning("Rejected invalid access token")
            return None
