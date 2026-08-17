"""
Gmail Agent — reads email via Gmail API (OAuth) with IMAP App Password fallback.
"""
import asyncio
import email as email_lib
import imaplib
import logging
import time
from email.header import decode_header

from agents.base import (
    AgentBase, AgentTask, AgentResult, Tool, Permission, HealthStatus,
)
from integrations.credentials import credentials_store
from integrations.oauth import oauth_handler

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


class Agent(AgentBase):
    id = "gmail"
    name = "Gmail Agent"
    description = "Read and search Gmail via Gmail API (OAuth) or IMAP App Password fallback."
    capabilities = ["read_inbox", "search_email", "get_email", "summarize_inbox"]
    required_permissions = [Permission.NETWORK_FETCH]
    required_integrations = ["gmail"]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="list_inbox",
                description="List the most recent emails in your Gmail inbox",
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "default": 10},
                        "unread_only": {"type": "boolean", "default": False},
                    },
                    "required": [],
                },
                handler=self._list_inbox,
            ),
            Tool(
                name="search_gmail",
                description="Search Gmail (e.g. 'from:boss subject:urgent')",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "count": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=self._search_gmail,
            ),
            Tool(
                name="read_email",
                description="Read full email content by message ID",
                parameters={
                    "type": "object",
                    "properties": {"email_id": {"type": "string"}},
                    "required": ["email_id"],
                },
                handler=self._read_email,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()

        ok, missing = await self.check_integrations()
        creds_imap = await self._get_imap_credentials()
        if not ok and not creds_imap:
            return self._integration_required_response(task, missing)

        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Gmail agent. Use list_inbox, search_gmail, read_email. "
                    "Summarize what matters with clear priorities."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=bool(response),
            response=response or "Could not read Gmail.",
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _get_gmail_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token = await credentials_store.get_token("gmail")
        if not token or not token.get("access_token"):
            return None

        creds = Credentials(
            token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
        )
        try:
            return build("gmail", "v1", credentials=creds, cache_discovery=False)
        except Exception as e:
            log.warning(f"Gmail API build failed: {e}")
            if token.get("refresh_token"):
                await oauth_handler.refresh_token("gmail")
                token = await credentials_store.get_token("gmail")
                if token:
                    creds = Credentials(token=token["access_token"])
                    return build("gmail", "v1", credentials=creds, cache_discovery=False)
            return None

    async def _api_list_inbox(self, count: int, unread_only: bool) -> str:
        service = await self._get_gmail_service()
        if not service:
            return None
        q = "is:unread" if unread_only else ""
        result = service.users().messages().list(
            userId="me", maxResults=count, q=q
        ).execute()
        messages = result.get("messages", [])
        lines = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            lines.append(
                f"[{m['id']}] {headers.get('Date', '')[:16]}\n"
                f"  From: {headers.get('From', '')}\n"
                f"  Subject: {headers.get('Subject', '')}"
            )
        return "\n\n".join(lines) if lines else "Inbox is empty."

    async def _api_search(self, query: str, count: int) -> str:
        service = await self._get_gmail_service()
        if not service:
            return None
        result = service.users().messages().list(
            userId="me", maxResults=count, q=query
        ).execute()
        messages = result.get("messages", [])
        lines = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            lines.append(f"[{m['id']}] {headers.get('From')} — {headers.get('Subject')}")
        return "\n\n".join(lines) if lines else f"No emails for: {query}"

    async def _api_read(self, email_id: str) -> str:
        service = await self._get_gmail_service()
        if not service:
            return None
        import base64
        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = ""
        payload = msg.get("payload", {})
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        elif payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        return (
            f"From: {headers.get('From')}\n"
            f"Date: {headers.get('Date')}\n"
            f"Subject: {headers.get('Subject')}\n\n{body[:3000]}"
        )

    async def _get_imap_credentials(self) -> dict | None:
        try:
            from memory.preferences import preference_store
            prefs = await preference_store.get_all()
            email_addr = prefs.get("gmail_address") or prefs.get("email_address")
            app_password = prefs.get("gmail_app_password")
            if email_addr and app_password:
                return {"email": email_addr, "password": app_password}
            import keyring
            pw = keyring.get_password("CaptainAI", "gmail_app_password")
            addr = keyring.get_password("CaptainAI", "gmail_address")
            if pw and addr:
                return {"email": addr, "password": pw}
        except Exception:
            pass
        return None

    def _imap_connect(self, creds: dict) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(creds["email"], creds["password"])
        return imap

    def _decode_header_value(self, value: str | None) -> str:
        if not value:
            return ""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    def _parse_message(self, raw: bytes) -> dict:
        msg = email_lib.message_from_bytes(raw)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                        break
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )
            except Exception:
                body = ""
        return {
            "from": self._decode_header_value(msg.get("From")),
            "subject": self._decode_header_value(msg.get("Subject")),
            "date": msg.get("Date", ""),
            "body": body[:3000],
        }

    def _fetch_inbox_sync(self, creds: dict, count: int, unread_only: bool) -> list[dict]:
        imap = self._imap_connect(creds)
        try:
            imap.select("INBOX")
            criteria = "UNSEEN" if unread_only else "ALL"
            _, uids = imap.uid("search", None, criteria)
            uid_list = uids[0].split()[-count:]
            messages = []
            for uid in reversed(uid_list):
                _, data = imap.uid("fetch", uid, "(RFC822)")
                if data and data[0]:
                    parsed = self._parse_message(data[0][1])
                    parsed["id"] = uid.decode()
                    messages.append(parsed)
            return messages
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    async def _list_inbox(self, count: int = 10, unread_only: bool = False) -> str:
        api_result = await self._api_list_inbox(count, unread_only)
        if api_result:
            return api_result
        creds = await self._get_imap_credentials()
        if not creds:
            return "Gmail not connected. Connect in Settings > Integrations."
        try:
            messages = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_inbox_sync, creds, count, unread_only
            )
            if not messages:
                return "Inbox is empty."
            lines = [
                f"[{m['id']}] {m['date'][:16]}\n  From: {m['from']}\n  Subject: {m['subject']}"
                for m in messages
            ]
            return "\n\n".join(lines)
        except Exception as e:
            return f"Gmail error: {e}"

    async def _search_gmail(self, query: str, count: int = 5) -> str:
        api_result = await self._api_search(query, count)
        if api_result:
            return api_result
        creds = await self._get_imap_credentials()
        if not creds:
            return "Gmail not connected."
        return f"IMAP search for '{query}' — connect Gmail OAuth for full search syntax."

    async def _read_email(self, email_id: str) -> str:
        api_result = await self._api_read(email_id)
        if api_result:
            return api_result
        creds = await self._get_imap_credentials()
        if not creds:
            return "Gmail not connected."
        return f"Cannot read email {email_id} without OAuth or valid IMAP setup."

    async def health_check(self) -> HealthStatus:
        if await credentials_store.has_valid_token("gmail"):
            return HealthStatus.HEALTHY
        creds = await self._get_imap_credentials()
        return HealthStatus.DEGRADED if creds else HealthStatus.UNHEALTHY
