"""Integrations registry — defines available OAuth integrations."""
from __future__ import annotations

from typing import Any

INTEGRATIONS: dict[str, dict[str, Any]] = {
    "gmail": {
        "name": "Gmail",
        "description": "Read and send emails via Gmail API",
        "icon": "mail",
        "oauth": {
            "provider": "google",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
        },
        "env_keys": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        "redirect_uri_key": "GOOGLE_REDIRECT_URI",
        "agents": ["gmail"],
    },
    "github": {
        "name": "GitHub",
        "description": "Access repositories, PRs, and issues",
        "icon": "github",
        "oauth": {
            "provider": "github",
            "scopes": ["repo", "read:user"],
            "auth_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
        },
        "env_keys": ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"],
        "agents": ["github"],
    },
    "slack": {
        "name": "Slack",
        "description": "Monitor channels and send messages",
        "icon": "slack",
        "oauth": {
            "provider": "slack",
            "scopes": ["channels:read", "chat:write", "users:read"],
            "auth_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
        },
        "env_keys": ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET"],
        "agents": ["slack"],
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "View and manage calendar events",
        "icon": "calendar",
        "oauth": {
            "provider": "google",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
        },
        "env_keys": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        "redirect_uri_key": "GOOGLE_REDIRECT_URI",
        "agents": ["calendar"],
    },
}


def get_integration(integration_id: str) -> dict[str, Any] | None:
    return INTEGRATIONS.get(integration_id)


def list_integrations() -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in INTEGRATIONS.items()]
