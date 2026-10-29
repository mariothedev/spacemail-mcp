# spacemail-mcp

An authenticated Streamable HTTP MCP server for your Spacemail mailbox.

## Configuration

Set these variables in Dokploy, or in `.env` beside `main.py` for local runs
(`.env` values take precedence):

```dotenv
SPACEMAIL_USER=you@example.com
SPACEMAIL_PASSWORD=your-mail-password
MCP_RESOURCE_URL=https://mail.example.com/mcp
JWT_SECRET=replace-with-a-long-random-secret
```

Generate a secret with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

The secret must contain at least 32 bytes. Store it securely, never commit it,
and never give it to MCP clients: anyone with the secret can mint any permission.
Optional `JWT_ISSUER` and `JWT_AUDIENCE` both default to `MCP_RESOURCE_URL`.
The issuer must be an HTTPS URL (as required by the SDK's auth metadata).
Missing configuration or a short secret prevents startup.

## Generate a client token

Install dependencies (Python 3.10+), then generate a token using the same
configuration/secret as the server:

```bash
pip install -r requirements.txt
# Read-only token, valid for one hour by default:
python generate_token.py
# Explicit permissions and lifetime in seconds:
python generate_token.py --subject personal-client --expires-in 3600 \
  --scopes spacemail:read spacemail:send spacemail:delete
```

The script prints the token. Treat it like a password. On Dokploy you can also
run `python generate_token.py` inside the container, where the environment is set.
There is no public login or token-issuing endpoint.

Configure your MCP client to connect to `https://mail.example.com/mcp` and send:

```http
Authorization: Bearer <generated-token>
```

Clients must support custom bearer tokens; this is not an OAuth login flow.
Tokens are HS256-signed JWTs. The server validates signature, issuer, audience,
expiration, issued-at and, if present, not-before. Every tool checks its own
required scope before accessing mail. Invalid/missing tokens return HTTP 401;
missing tool permissions return a tool error without performing the operation.
Tokens expire automatically. There is no per-token revocation list; rotating
`JWT_SECRET` and restarting the server revokes all existing tokens.

## Tools

- `read_emails(limit=5)`: Read up to 20 recent INBOX emails without marking them
  as read. Returns UIDs for deletion. Requires `spacemail:read`.
- `send_email_to_self(subject, body)`: Send plain-text mail only to your configured
  address. Requires `spacemail:send`.
- `delete_email(uid)`: **Permanently and irreversibly delete** one INBOX email,
  not to Trash. Requires `spacemail:delete` and server UIDPLUS support for safe
  targeted deletion.

All clients access the same configured mailbox. IMAP uses TLS on port 993 and
SMTP uses TLS on port 465, both at `mail.spacemail.com`.

## Deploy with Dokploy

1. Create an application from this repository; select the Dockerfile build type.
2. Set the configuration variables above in Dokploy's environment settings.
3. Route your HTTPS domain to container port **8000**.
4. Forward the Authorization header unchanged and use the `/mcp` endpoint.

The image runs as a non-root user and excludes `.env` files. `PORT` defaults to
8000. Only `MCP_TRANSPORT=streamable-http` is supported; authentication requires
HTTP. Stateless HTTP avoids sharing MCP sessions between identities.

For local runs with configuration set: `python main.py`.
Run tests with `python -m unittest test_auth.py`.
