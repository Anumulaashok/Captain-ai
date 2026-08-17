"""Priority engine — calculates notification priority."""
from notifications.models import NotificationPriority

URGENT_KEYWORDS = {"urgent", "asap", "critical", "failed", "down", "emergency"}
HIGH_KEYWORDS = {"review", "deadline", "blocked", "needs attention", "reminder"}


def calculate_priority(
    title: str,
    summary: str,
    category: str,
    sender_importance: float = 0.5,
) -> int:
    """
    Calculate notification priority (1=urgent … 4=low).
    Lower number = higher priority.
    """
    text = f"{title} {summary}".lower()

    if any(kw in text for kw in URGENT_KEYWORDS):
        return NotificationPriority.URGENT

    if category in ("prs", "email") and any(kw in text for kw in HIGH_KEYWORDS):
        return NotificationPriority.HIGH

    if sender_importance >= 0.8:
        return NotificationPriority.HIGH

    if category in ("finance", "calendar") and any(kw in text for kw in HIGH_KEYWORDS):
        return NotificationPriority.HIGH

    if category in ("agents", "tasks"):
        return NotificationPriority.NORMAL

    return NotificationPriority.LOW
