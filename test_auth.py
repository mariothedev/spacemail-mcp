import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from auth import AuthentikTokenVerifier


class TokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.verifier = AuthentikTokenVerifier(
            "https://auth.example/application/o/spacemail/",
            "spacemail-client",
            "https://auth.example/application/o/spacemail/jwks/",
        )
        self.claims = {
            "iss": self.verifier.issuer,
            "aud": self.verifier.audience,
            "sub": "user-123",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "scope": "spacemail:read spacemail:send",
        }

    def verify(self, claims=None, key=None, algorithm="RS256"):
        token = jwt.encode(
            self.claims if claims is None else claims,
            key or self.key,
            algorithm=algorithm,
            headers={"kid": "test-key"},
        )
        with patch.object(
            self.verifier.jwks, "get_signing_key_from_jwt",
            return_value=SimpleNamespace(key=self.key.public_key()),
        ):
            return asyncio.run(self.verifier.verify_token(token))

    def test_valid_token(self):
        token = self.verify()
        self.assertEqual(token.scopes, ["spacemail:read", "spacemail:send"])
        self.assertEqual(token.subject, "user-123")

    def test_invalid_claims(self):
        for claim, value in (
            ("iss", "https://other.example/"),
            ("aud", "another-client"),
            ("exp", int(time.time()) - 30),
            ("nbf", int(time.time()) + 300),
            ("scope", ["spacemail:read"]),
        ):
            with self.subTest(claim=claim):
                self.assertIsNone(self.verify({**self.claims, claim: value}))

    def test_missing_required_claims(self):
        for claim in ("iss", "aud", "exp", "sub", "iat"):
            claims = dict(self.claims)
            del claims[claim]
            with self.subTest(claim=claim):
                self.assertIsNone(self.verify(claims))

    def test_wrong_signature(self):
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.assertIsNone(self.verify(key=wrong_key))

    def test_wrong_algorithm(self):
        self.assertIsNone(self.verify(key="a" * 64, algorithm="HS256"))

    def test_unavailable_jwks(self):
        with patch.object(
            self.verifier.jwks, "get_signing_key_from_jwt",
            side_effect=jwt.PyJWKClientConnectionError("unavailable"),
        ):
            self.assertIsNone(asyncio.run(self.verifier.verify_token("invalid")))


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {
            "AUTHENTIK_ISSUER": "https://auth.example/application/o/spacemail/",
            "AUTHENTIK_AUDIENCE": "spacemail-client",
            "AUTHENTIK_JWKS_URL": "https://auth.example/application/o/spacemail/jwks/",
            "MCP_RESOURCE_URL": "https://mail.example/mcp",
        }):
            import main
            cls.server = main

    def test_tools_require_their_own_scope_before_io(self):
        for tool, args in (
            (self.server.read_emails, ()),
            (self.server.send_email_to_self, ("subject", "body")),
            (self.server.delete_email, ("123",)),
        ):
            for token in (None, SimpleNamespace(scopes=["unrelated"])):
                with self.subTest(tool=tool.__name__, token=token):
                    with patch.object(self.server, "get_access_token", return_value=token):
                        with self.assertRaises(PermissionError):
                            tool(*args)

    def test_matching_permission(self):
        with patch.object(self.server, "get_access_token", return_value=SimpleNamespace(
            scopes=["spacemail:read"],
        )):
            self.server.require_scope("spacemail:read")
            with self.assertRaises(PermissionError):
                self.server.require_scope("spacemail:delete")


if __name__ == "__main__":
    unittest.main()
