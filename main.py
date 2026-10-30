import imaplib
import os
import smtplib
import ssl
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

# from auth import JWTTokenVerifier
from auth import AuthentikTokenVerifier

load_dotenv(Path(__file__).with_name(".env"), override=True)

resource_url = os.environ["MCP_RESOURCE_URL"]
# issuer = os.environ.get("JWT_ISSUER", resource_url)
# audience = os.environ.get("JWT_AUDIENCE", resource_url)
if not resource_url.startswith("https://"):
    raise ValueError("MCP_RESOURCE_URL must use HTTPS")

# resource_url = os.environ["MCP_RESOURCE_URL"]
issuer = os.environ["AUTHENTIK_ISSUER"]

mcp = FastMCP(
    "Spacemail",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
    stateless_http=True,
    token_verifier=AuthentikTokenVerifier(
        issuer,
        os.environ["AUTHENTIK_AUDIENCE"],
        os.environ["AUTHENTIK_JWKS_URL"],
    ),
    auth=AuthSettings(
        issuer_url=issuer,
        resource_server_url=resource_url,
        validate_token_resource=False,
    ),
)

# mcp = FastMCP(
#     "Spacemail",
#     host="0.0.0.0",
#     port=int(os.environ.get("PORT", "8000")),
#     stateless_http=True,
#     token_verifier=JWTTokenVerifier(os.environ["JWT_SECRET"], issuer, audience),
#     auth=AuthSettings(
#         issuer_url=issuer,
#         resource_server_url=resource_url,
#         validate_token_resource=False,  # JWT verifier checks the configured audience.
#     ),
# )


def require_scope(scope: str) -> None:
    token = get_access_token()
    if token is None or scope not in token.scopes:
        raise PermissionError(f"Required permission: {scope}")


@mcp.tool()
def read_emails(limit: int = 5) -> list[dict[str, str]]:
    """
    Read recent inbox emails without marking them as read.
    """
    require_scope("spacemail:read")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")

    username = os.environ["SPACEMAIL_USER"]
    password = os.environ["SPACEMAIL_PASSWORD"]

    with imaplib.IMAP4_SSL(
        "mail.spacemail.com",
        993,
        ssl_context=ssl.create_default_context(),
        timeout=30,
    ) as mailbox:
        mailbox.login(username, password)

        status, _ = mailbox.select("INBOX", readonly=True)
        if status != "OK":
            raise RuntimeError("Could not open inbox")

        status, data = mailbox.uid("search", None, "ALL")
        if status != "OK":
            raise RuntimeError("Could not search inbox")

        messages = []

        for uid in reversed(data[0].split()[-limit:]):
            status, parts = mailbox.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue

            raw = next(
                (part[1] for part in parts if isinstance(part, tuple)),
                None,
            )
            if raw is None:
                continue

            message = BytesParser(policy=policy.default).parsebytes(raw)
            body = message.get_body(preferencelist=("plain", "html"))
            text = body.get_content() if body else ""

            messages.append({
                "uid": uid.decode(),
                "from": str(message.get("From", "")),
                "subject": str(message.get("Subject", "")),
                "date": str(message.get("Date", "")),
                "body": text[:5000],
            })

        return messages


@mcp.tool()
def send_email_to_self(subject: str, body: str) -> dict[str, str]:
    """Send a plain-text email to the configured SPACEMAIL_USER address only."""
    require_scope("spacemail:send")
    username = os.environ["SPACEMAIL_USER"]
    password = os.environ["SPACEMAIL_PASSWORD"]

    message = EmailMessage()
    message["From"] = username
    message["To"] = username
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL(
        "mail.spacemail.com",
        465,
        context=ssl.create_default_context(),
        timeout=30,
    ) as smtp:
        smtp.login(username, password)
        refused = smtp.send_message(message, from_addr=username, to_addrs=[username])
        if refused:
            raise RuntimeError("The mail server refused the recipient")

    return {"status": "sent", "to": username}


@mcp.tool()
def delete_email(uid: str) -> dict[str, str]:
    """Move an INBOX email to Trash using its UID from read_emails."""
    require_scope("spacemail:delete")
    if not uid.isascii() or not uid.isdecimal() or not 1 <= int(uid) <= 4294967295:
        raise ValueError("uid must be a positive 32-bit IMAP UID")

    username = os.environ["SPACEMAIL_USER"]
    password = os.environ["SPACEMAIL_PASSWORD"]

    with imaplib.IMAP4_SSL(
        "mail.spacemail.com",
        993,
        ssl_context=ssl.create_default_context(),
        timeout=30,
    ) as mailbox:
        mailbox.login(username, password)

        status, _ = mailbox.select("INBOX", readonly=False)
        if status != "OK":
            raise RuntimeError("Could not open inbox")

        # if b"UIDPLUS" not in mailbox.capabilities:
        #     raise RuntimeError("Server must support UIDPLUS for safe targeted deletion")

        status, data = mailbox.uid("search", None, "UID", uid)
        if status != "OK":
            raise RuntimeError("Could not find email")
        if not data or not data[0]:
            raise ValueError("Email UID not found in INBOX")

        status, _ = mailbox.uid("move", uid, "Trash")
        if status != "OK":
            raise RuntimeError("Could not move email to Trash")

#         status, _ = mailbox.uid("store", uid, "+FLAGS.SILENT", r"(\Deleted)")
#         if status != "OK":
#             raise RuntimeError("Could not mark email for deletion")
#
#         status, _ = mailbox.uid("expunge", uid)
#         if status != "OK":
#             raise RuntimeError("Could not expunge email; it remains marked for deletion")

    # return {"status": "permanently_deleted", "uid": uid}
    return {"status": "moved_to_trash", "uid": uid}


if __name__ == "__main__":
    if os.environ.get("MCP_TRANSPORT", "streamable-http") != "streamable-http":
        raise ValueError("Authenticated server requires Streamable HTTP transport")
    mcp.run(transport="streamable-http")
