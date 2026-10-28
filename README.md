# spacemail-mcp

Install and run (Python 3.10+):

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
2. Set `SPACEMAIL_USER` and `SPACEMAIL_PASSWORD` in Dokploy's environment settings.
3. Route your HTTPS domain to container port **8000**.
4. Connect your MCP client to `https://your-domain/mcp` using Streamable HTTP.

The image runs as a non-root user and excludes `.env` files. It defaults to
`MCP_TRANSPORT=streamable-http` and `PORT=8000`. Local runs still default to stdio.

**Security:** This server does not implement authentication. Keep it private
(e.g. VPN), or put authenticated access in front of it before exposing it.
Anyone with access can read your mail, send mail to you, and permanently delete it.
