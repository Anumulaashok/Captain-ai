"""Seed default agents into the database on first run."""
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import AgentRecord
import logging

log = logging.getLogger(__name__)

DEFAULT_AGENTS = [
    {
        "id": "coding",
        "name": "Coding Agent",
        "description": "Generate, debug, review and explain code in any language",
        "permissions": ["filesystem:read", "filesystem:write"],
        "is_enabled": True,
    },
    {
        "id": "email",
        "name": "Email Agent",
        "description": "Read, search and draft email replies via Apple Mail",
        "permissions": ["email:read", "email:write"],
        "is_enabled": False,
    },
    {
        "id": "gmail",
        "name": "Gmail Agent",
        "description": "Read and search Gmail via Gmail API (OAuth) or IMAP App Password",
        "permissions": ["network:fetch"],
        "is_enabled": True,
    },
    {
        "id": "browser",
        "name": "Browser Agent",
        "description": "Search the web, open URLs and summarize pages",
        "permissions": ["network:fetch", "browser:open"],
        "is_enabled": True,
    },
    {
        "id": "calendar",
        "name": "Calendar Agent",
        "description": "Create, update and query calendar events",
        "permissions": ["calendar:read", "calendar:write"],
        "is_enabled": False,
    },
    {
        "id": "file",
        "name": "File Agent",
        "description": "Search, read, write and summarize local files",
        "permissions": ["filesystem:read", "filesystem:write"],
        "is_enabled": True,
    },
    {
        "id": "terminal",
        "name": "Terminal Agent",
        "description": "Execute approved shell commands and explain output",
        "permissions": ["terminal:execute"],
        "is_enabled": True,
    },
    {
        "id": "research",
        "name": "Research Agent",
        "description": "Multi-step web research with memory storage",
        "permissions": ["network:fetch", "browser:open"],
        "is_enabled": True,
    },
    {
        "id": "github",
        "name": "GitHub Agent",
        "description": "Access repositories, PRs, issues, and CI status",
        "permissions": ["network:fetch"],
        "is_enabled": True,
    },
    {
        "id": "finance",
        "name": "Finance Agent",
        "description": "Monitor accounts, spending, and financial alerts",
        "permissions": ["network:fetch"],
        "is_enabled": False,
    },
    {
        "id": "briefing",
        "name": "Briefing Agent",
        "description": "Morning briefing and status updates",
        "permissions": ["network:fetch"],
        "is_enabled": True,
    },
    {
        "id": "builder",
        "name": "Agent Builder",
        "description": "Builds new agents when Captain lacks capability",
        "permissions": ["filesystem:read", "filesystem:write", "network:fetch"],
        "is_enabled": True,
    },
    {
        "id": "goal",
        "name": "Goal Agent",
        "description": "Tracks goals, milestones, blockers, and progress",
        "permissions": ["network:fetch"],
        "is_enabled": True,
    },
]


async def seed_defaults() -> None:
    async with AsyncSessionLocal() as session:
        for data in DEFAULT_AGENTS:
            result = await session.execute(
                select(AgentRecord).where(AgentRecord.id == data["id"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                session.add(AgentRecord(**data))
                log.info(f"Seeded agent: {data['id']}")
            else:
                # Update description for existing records
                existing.description = data["description"]
        await session.commit()
