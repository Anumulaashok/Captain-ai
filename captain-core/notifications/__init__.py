"""Smart notification system."""

from notifications.models import NotificationPriority
from notifications.store import notification_store

__all__ = ["NotificationPriority", "notification_store"]
