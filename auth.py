"""Validate Authentik-signed access tokens for this resource server."""

import asyncio
import logging
from urllib.parse import urlparse

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


class AuthentikTokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str):
        for url in (issuer, jwks_url):
            if urlparse(url).scheme != "https" or not urlparse(url).netloc:
                raise ValueError("Authentik issuer and JWKS URL must use HTTPS")
        if not audience:
            raise ValueError("AUTHENTIK_AUDIENCE must not be empty")
        self.issuer = issuer
        self.audience = audience
        self.jwks = PyJWKClient(jwks_url, timeout=10)

    async def verify_token(self, token: str) -> AccessToken | None:
        # JWKS retrieval is blocking; do not block the server's event loop.
        return await asyncio.to_thread(self._verify, token)

    def _verify(self, token: str) -> AccessToken | None:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub", "iat"]},
            )
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                return None
            return AccessToken(
                token=token,
                client_id=claims.get("azp") or claims["sub"],
                subject=claims["sub"],
                scopes=scope.split(),
                expires_at=claims["exp"],
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            # Never log tokens or decoded claims.
            logger.warning("Rejected invalid access token")
            return None
