# spacemail-mcp

Install and run (Python 3.10+; configure Authentik below first):

```bash
pip install -r requirements.txt
python main.py
```

Set `SPACEMAIL_USER` (your full email address) and `SPACEMAIL_PASSWORD` in
`.env` beside `main.py`, or in the OS environment. Values in `.env` take precedence.

## Tools

- `read_emails(limit=5)`: Read up to 20 recent INBOX emails without marking them
  as read. Returns UIDs for use with deletion.
- `send_email_to_self(subject, body)`: Send a plain-text email only to your own
  configured address, using SMTP over TLS on port 465.
- `delete_email(uid)`: **Permanently and irreversibly delete** one INBOX email
  by UID, without moving it to Trash. Requires IMAP UIDPLUS support so other
  emails marked for deletion are not also purged.

IMAP uses TLS on port 993. Both protocols connect to `mail.spacemail.com`.

## Deploy with Dokploy

1. Create an application from this repository and select the Dockerfile build type.
2. Set mail credentials and the Authentik variables below in Dokploy's environment settings.
3. Route your HTTPS domain to container port **8000**.
4. Connect your MCP client to `https://your-domain/mcp` using Streamable HTTP.

The image runs as a non-root user and excludes `.env` files. It defaults to
`MCP_TRANSPORT=streamable-http` and `PORT=8000`. Authentication requires HTTP;
stdio is no longer supported. Missing authentication configuration prevents startup.

## Authentik authentication

Create an OAuth2/OpenID Connect provider and application in Authentik:

1. Select an **asymmetric signing key** for the provider (RSA / RS256).
2. Configure redirect URIs for your MCP client's OAuth callback. Use authorization
   code with PKCE where supported. Restrict application access to the intended
   users/groups using Authentik policies: this server accesses one shared mailbox.
3. Add/select scope mappings for the permissions you want to grant:
   `spacemail:read`, `spacemail:send`, and `spacemail:delete`. Ensure those names
   appear in the **access token's space-separated `scope` claim**. Clients must
   request the desired scopes. Restrict who can receive destructive permissions
   in Authentik; a requested scope is not itself proof of entitlement.
4. From the provider's OpenID discovery document, copy the exact `issuer` and
   `jwks_uri`. Configure the following variables (example values only):

```dotenv
AUTHENTIK_ISSUER=https://auth.example.com/application/o/spacemail/
AUTHENTIK_JWKS_URL=https://auth.example.com/application/o/spacemail/jwks/
AUTHENTIK_AUDIENCE=your-expected-access-token-audience
MCP_RESOURCE_URL=https://mail.example.com/mcp
```

The expected audience must match the access tokens Authentik issues for this
server (often the provider's client ID); do not use an unrelated application's
client ID. Prefer a dedicated provider/audience for this mailbox. The issuer
must match exactly, including any trailing slash. Only HTTPS issuer/JWKS URLs
and RS256 signatures are accepted; keys are cached and refreshed via JWKS.
No client secret is needed by this server to verify tokens.

Clients send `Authorization: Bearer <access_token>` on every MCP HTTP request.
Use an **access token**, not an ID token or Authentik browser-session cookie.
The server verifies signature, issuer, audience, expiration, issued-at and,
when present, not-before. Each tool then checks its required scope before mail
access. Read permission does not grant send or delete permission.
Invalid/missing tokens are rejected by the HTTP authentication middleware;
missing tool permissions return a tool error without executing the operation.

The SDK publishes OAuth protected-resource metadata for discovery. This does
not add OAuth client registration to Authentik: configure the client there
explicitly if needed. Your client must support Authentik's OAuth flow or accept
an externally obtained access token. Forward the Authorization header through
Dokploy's proxy unchanged, use HTTPS, and do not expose an alternative unprotected
mail endpoint. Stateless HTTP avoids sharing MCP sessions between identities.

Run authentication tests with `python -m unittest test_auth.py`.
