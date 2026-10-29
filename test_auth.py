import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt

from auth import JWTTokenVerifier


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-secret-not-for-production-" + "x" * 40
        self.verifier = JWTTokenVerifier(
            self.key, "https://mail.example/mcp", "spacemail-client",
        )
        self.claims = {
            "iss": self.verifier.issuer,
            "aud": self.verifier.audience,
            "sub": "user-123",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "scope": "spacemail:read spacemail:send",
        }

    def verify(self, claims=None, key=None, algorithm="HS256"):
        token = jwt.encode(
            self.claims if claims is None else claims,
            key or self.key,
            algorithm=algorithm,
        )
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
        self.assertIsNone(self.verify(key="another-secret-" + "y" * 64))

    def test_wrong_algorithm(self):
        self.assertIsNone(self.verify(algorithm="HS384"))

    def test_malformed_token(self):
        self.assertIsNone(asyncio.run(self.verifier.verify_token("invalid")))

    def test_weak_secret(self):
        with self.assertRaises(ValueError):
            JWTTokenVerifier("short", "issuer", "audience")


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {
            "JWT_SECRET": "test-secret-" + "x" * 64,
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
