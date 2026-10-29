"""Generate a scoped, expiring JWT offline; no public token-issuing endpoint."""

import argparse
import os
import time
from pathlib import Path

import jwt
from dotenv import load_dotenv

from auth import JWTTokenVerifier, SCOPES


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"), override=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="personal-client")
    parser.add_argument("--expires-in", type=int, default=3600, help="Lifetime in seconds")
    parser.add_argument("--scopes", nargs="+", choices=SCOPES, default=["spacemail:read"])
    args = parser.parse_args()
    if args.expires_in <= 0 or not args.subject.strip():
        parser.error("Expiration must be positive and subject must not be empty")

    resource_url = os.environ["MCP_RESOURCE_URL"]
    verifier = JWTTokenVerifier(
        os.environ["JWT_SECRET"],
        os.environ.get("JWT_ISSUER", resource_url),
        os.environ.get("JWT_AUDIENCE", resource_url),
    )
    now = int(time.time())
    print(jwt.encode({
        "iss": verifier.issuer,
        "aud": verifier.audience,
        "sub": args.subject,
        "iat": now,
        "exp": now + args.expires_in,
        "scope": " ".join(args.scopes),
    }, verifier.secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
