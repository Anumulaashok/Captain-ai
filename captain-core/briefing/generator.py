"""Morning briefing and end-of-day summary generator."""
import logging

log = logging.getLogger(__name__)


async def generate_briefing(briefing_type: str = "morning") -> str:
    """Aggregate notifications, goals, and tasks into a natural language briefing."""
    from briefing import store as briefing_store
    from goals.store import goal_store
    from notifications.store import notification_store

    items = await notification_store.list_notifications(unread_only=True, limit=20)
    goals = await goal_store.list_goals(active_only=True)

    sections: list[str] = []

    if briefing_type == "morning":
        sections.append("Good morning! Here's what's happening today:\n")
    else:
        sections.append("Here's your end-of-day summary:\n")

    # Notifications by priority
    urgent = [i for i in items if i.get("priority", 5) <= 2]
    high = [i for i in items if 2 < i.get("priority", 5) <= 4]
    normal = [i for i in items if i.get("priority", 5) > 4]

    if urgent:
        sections.append("**Urgent:**")
        for item in urgent[:5]:
            sections.append(f"  - {item['title']}: {item['summary'][:100]}")

    if high:
        sections.append("**Needs attention:**")
        for item in high[:5]:
            sections.append(f"  - {item['title']}")

    if normal and briefing_type == "morning":
        sections.append(f"**Also:** {len(normal)} other updates")

    # Goals
    if goals:
        sections.append("\n**Goals:**")
        for g in goals[:3]:
            pct = int((g.get("progress") or 0) * 100)
            sections.append(f"  - {g['title']}: {pct}% complete")

    if not items and not goals:
        sections.append("All quiet — no urgent items right now.")

    text = "\n".join(sections)

    # Store as briefing item
    await briefing_store.add_item(
        category="briefing",
        title=f"{'Morning' if briefing_type == 'morning' else 'End of day'} briefing",
        summary=text[:500],
        source_agent="briefing",
        priority=4 if briefing_type == "morning" else 6,
    )

    return text
