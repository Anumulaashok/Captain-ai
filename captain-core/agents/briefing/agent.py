"""
Briefing Agent — "Hey Captain, what's the update?"

Reads briefing_items + active TaskRecords + pending approvals, ranks by priority,
and produces a spoken/text summary covering:
  1. Active agents and what they're doing
  2. Urgent notifications
  3. PRs / CI status
  4. Financial snapshot
  5. Today's calendar
  6. Tasks needing permission
"""
import logging
import time
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "briefing"
    name = "Briefing Agent"
    description = "Delivers a prioritized spoken status update across all agents and services"
    capabilities = ["morning_briefing", "status_update", "notification_summary"]
    required_permissions = []   # reads only internal DB — no external permissions needed

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="get_briefing_items",
                description="Fetch unread briefing items from all background agents",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._get_briefing_items,
            ),
            Tool(
                name="get_active_tasks",
                description="List currently running agent tasks",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._get_active_tasks,
            ),
            Tool(
                name="get_pending_approvals",
                description="List permissions requests waiting for user action",
                parameters={"type": "object", "properties": {}, "required": []},
                handler=self._get_pending_approvals,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()

        # Gather all data in parallel
        import asyncio
        items, active, pending = await asyncio.gather(
            self._get_briefing_items(),
            self._get_active_tasks(),
            self._get_pending_approvals(),
            return_exceptions=True,
        )

        # Build structured briefing text
        sections: list[str] = []

        # Active agents
        if isinstance(active, str) and active and "No tasks" not in active:
            sections.append(f"**Active agents:** {active}")

        # Pending approvals (highest priority — agent is BLOCKED)
        if isinstance(pending, str) and pending and "No pending" not in pending:
            sections.append(f"⚠️ **Waiting for your approval:** {pending}")

        # Briefing items by category priority
        if isinstance(items, str) and items and "No new" not in items:
            sections.append(items)

        if not sections:
            summary_text = (
                "All clear — no pending notifications, no active tasks, "
                "and no approvals needed. Your agents are idle."
            )
        else:
            summary_text = "\n\n".join(sections)

        # Ask LLM to turn the structured data into natural spoken language
        spoken = await self._synthesize(summary_text, task)

        # Mark delivered items as read
        try:
            from briefing.store import get_unread, mark_read
            unread = await get_unread()
            await mark_read([i["id"] for i in unread])
        except Exception:
            pass

        return AgentResult(
            task_id=task.id,
            success=True,
            response=spoken,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _get_briefing_items(self) -> str:
        from briefing.store import get_unread
        items = await get_unread(limit=30)
        if not items:
            return "No new notifications from background agents."

        # Group by category
        by_cat: dict[str, list] = {}
        for item in items:
            by_cat.setdefault(item["category"], []).append(item)

        cat_order = ["prs", "notifications", "emails", "calendar", "finance", "agents"]
        cat_labels = {
            "prs": "GitHub PRs",
            "notifications": "Notifications",
            "emails": "Email",
            "calendar": "Calendar",
            "finance": "Finance",
            "agents": "Agent activity",
        }

        sections = []
        for cat in cat_order + [c for c in by_cat if c not in cat_order]:
            if cat not in by_cat:
                continue
            label = cat_labels.get(cat, cat.title())
            lines = [f"• {i['title']}: {i['summary'][:120]}" for i in by_cat[cat][:3]]
            sections.append(f"**{label}:**\n" + "\n".join(lines))

        return "\n\n".join(sections)

    async def _get_active_tasks(self) -> str:
        from db.database import AsyncSessionLocal
        from db.models import TaskRecord
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            q = select(TaskRecord).where(TaskRecord.status == "running").limit(10)
            rows = (await db.execute(q)).scalars().all()

        if not rows:
            return "No tasks currently running."
        parts = [f"{r.agent_id} — {r.intent or 'task'}" for r in rows]
        return ", ".join(parts)

    async def _get_pending_approvals(self) -> str:
        from security.approvals import approval_manager
        pending = approval_manager.list_pending()
        if not pending:
            return "No pending permission requests."
        return f"{len(pending)} permission request(s) waiting: {', '.join(pending[:5])}"

    async def _synthesize(self, raw: str, task: AgentTask) -> str:
        """Convert the structured briefing into natural spoken language."""
        from models.ollama_client import OllamaClient
        from models.router import model_router, ModelRole
        from config import settings

        prompt = (
            "You are Captain, a personal AI assistant. "
            "Convert this status briefing into natural, concise spoken English. "
            "Sound like a calm assistant giving a morning update. "
            "Use 'you have', 'there are', 'I noticed' — personal and direct. "
            "Keep it under 150 words.\n\n"
            + raw
        )

        ollama = OllamaClient()
        if not await ollama.is_running():
            return raw  # fall back to raw structured text

        model = await model_router.get_model_for_role(ModelRole.CHAT)
        try:
            text = ""
            async for token in ollama.chat(
                model,
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=200,
            ):
                text += token
            return text.strip() or raw
        except Exception:
            return raw
