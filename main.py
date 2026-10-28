import imaplib
import os
import smtplib
import ssl
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).with_name(".env"), override=True)

mcp = FastMCP(
    "Spacemail",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


@mcp.tool()
def read_emails(limit: int = 5) -> list[dict[str, str]]:
    """
    Read recent inbox emails without marking them as read.
    """
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
    """Permanently delete an INBOX email using its UID from read_emails.

    This is irreversible and does not move the email to Trash.
    """
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

        if b"UIDPLUS" not in mailbox.capabilities:
            raise RuntimeError("Server must support UIDPLUS for safe targeted deletion")

        status, data = mailbox.uid("search", None, "UID", uid)
        if status != "OK":
            raise RuntimeError("Could not find email")
        if not data or not data[0]:
            raise ValueError("Email UID not found in INBOX")

        status, _ = mailbox.uid("store", uid, "+FLAGS.SILENT", r"(\Deleted)")
        if status != "OK":
            raise RuntimeError("Could not mark email for deletion")

        status, _ = mailbox.uid("expunge", uid)
        if status != "OK":
            raise RuntimeError("Could not expunge email; it remains marked for deletion")

    return {"status": "permanently_deleted", "uid": uid}


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
