import subprocess
import time
import logging
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission, HealthStatus

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "email"
    name = "Email Agent"
    description = "Read, search and draft email replies via Apple Mail"
    capabilities = ["read_emails", "search_emails", "draft_reply", "send_draft"]
    required_permissions = [Permission.EMAIL_READ, Permission.EMAIL_WRITE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="read_emails",
                description="Read recent emails from a mailbox folder",
                parameters={
                    "type": "object",
                    "properties": {
                        "folder": {"type": "string", "default": "INBOX"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
                handler=self._read_emails,
            ),
            Tool(
                name="search_emails",
                description="Search emails by keyword",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
                handler=self._search_emails,
            ),
            Tool(
                name="draft_reply",
                description="Draft a reply to a specific email",
                parameters={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "original_body": {"type": "string"},
                        "tone": {"type": "string", "description": "professional | friendly | brief"},
                        "key_points": {"type": "string"},
                    },
                    "required": ["subject", "original_body"],
                },
                handler=self._draft_reply,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an email assistant. Help the user read, search and compose emails. "
                    "Always confirm before sending. Draft emails should be professional and concise."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=True,
            response=response,
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def health_check(self) -> HealthStatus:
        script = 'tell application "Mail" to return name of first account'
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=5
            )
            return HealthStatus.HEALTHY if result.returncode == 0 else HealthStatus.DEGRADED
        except Exception:
            return HealthStatus.UNHEALTHY

    async def _read_emails(self, folder: str = "INBOX", limit: int = 10) -> str:
        script = f"""
        tell application "Mail"
            set msgs to messages of mailbox "{folder}" of first account
            set result to ""
            repeat with i from 1 to (count of msgs)
                if i > {limit} then exit repeat
                set m to item i of msgs
                set result to result & "Subject: " & subject of m & "\\n"
                set result to result & "From: " & sender of m & "\\n"
                set result to result & "Date: " & (date received of m as string) & "\\n"
                set result to result & "---\\n"
            end repeat
            return result
        end tell
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=15
            )
            return result.stdout.strip() or "No emails found"
        except Exception as e:
            return f"Error reading emails: {e}"

    async def _search_emails(self, query: str, limit: int = 10) -> str:
        script = f"""
        tell application "Mail"
            set msgs to (search messages of inbox for "{query}")
            set result to ""
            repeat with i from 1 to (count of msgs)
                if i > {limit} then exit repeat
                set m to item i of msgs
                set result to result & "Subject: " & subject of m & "\\n"
                set result to result & "From: " & sender of m & "\\n---\\n"
            end repeat
            return result
        end tell
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=15
            )
            return result.stdout.strip() or "No matching emails"
        except Exception as e:
            return f"Search error: {e}"

    async def _draft_reply(
        self, subject: str, original_body: str, tone: str = "professional", key_points: str = ""
    ) -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"Draft a {tone} email reply to:\n\nSubject: {subject}\n\n{original_body[:1500]}\n\n"
            + (f"Include these points: {key_points}\n\n" if key_points else "")
            + "Return only the email body text."
        )
        draft = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.4,
        ):
            draft += token
        return draft
