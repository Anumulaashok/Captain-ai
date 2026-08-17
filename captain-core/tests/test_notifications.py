"""Tests for notification priority engine."""
from notifications.priority import calculate_priority
from notifications.models import NotificationPriority


def test_urgent_priority():
    p = calculate_priority("URGENT: CI failed", "Production is down", "prs")
    assert p == NotificationPriority.URGENT


def test_low_priority():
    p = calculate_priority("Weekly stats", "FYI summary", "finance")
    assert p == NotificationPriority.LOW
