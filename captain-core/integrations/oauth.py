"""OAuth 2.0 flow handler for app integrations."""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from urllib.parse import urlencode

import httpx

from config import settings
from integrations.credentials import credentials_store
from integrations.registry import get_integration

log = logging.getLogger(__name__)


def _env(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    # Map GOOGLE_CLIENT_ID → google_client_id on settings
    attr = key.lower()
    return str(getattr(settings, attr, "") or "")


def _redirect_uri(integration: dict) -> str:
    key = integration.get("redirect_uri_key", "OAUTH_REDIRECT_URI")
    return (
        os.environ.get(key)
        or os.environ.get("OAUTH_REDIRECT_URI")
        or f"http://{settings.app_host}:{settings.app_port}/api/integrations/callback"
    )


def check_env_keys(integration_id: str) -> dict:
    """Return which required env keys are set."""
    integration = get_integration(integration_id)
    if not integration:
        return {"configured": False, "missing": []}
    missing = []
    for key in integration.get("env_keys", []):
        if not _env(key):
            missing.append(key)
    return {"configured": len(missing) == 0, "missing": missing}


class OAuthHandler:
    async def get_auth_url(self, integration_id: str) -> dict:
        integration = get_integration(integration_id)
        if not integration:
            raise ValueError(f"Unknown integration: {integration_id}")

        env_status = check_env_keys(integration_id)
        if not env_status["configured"]:
            return {
                "error": "env_missing",
                "missing_keys": env_status["missing"],
                "message": (
                    f"To connect {integration['name']}, add these to your .env file: "
                    + ", ".join(env_status["missing"])
                ),
            }

        oauth_cfg = integration["oauth"]
        state = str(uuid.uuid4())
        await credentials_store.store_oauth_state(state, integration_id)

        provider = oauth_cfg.get("provider", "")
        client_id = _env(integration["env_keys"][0])

        params: dict[str, str] = {
            "client_id": client_id,
            "redirect_uri": _redirect_uri(integration),
            "scope": " ".join(oauth_cfg.get("scopes", [])),
            "state": state,
            "response_type": "code",
        }

        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "consent"

        auth_url = oauth_cfg["auth_url"] + "?" + urlencode(params)
        return {"auth_url": auth_url, "state": state}

    async def handle_callback(self, code: str, state: str) -> dict:
        integration_id = await credentials_store.pop_oauth_state(state)
        if not integration_id:
            raise ValueError("Invalid or expired OAuth state")

        integration = get_integration(integration_id)
        if not integration:
            raise ValueError("Unknown integration")

        oauth_cfg = integration["oauth"]
        provider = oauth_cfg.get("provider", "")
        env_keys = integration["env_keys"]
        client_id = _env(env_keys[0])
        client_secret = _env(env_keys[1]) if len(env_keys) > 1 else ""

        token_data: dict = {}

        async with httpx.AsyncClient() as client:
            if provider == "google":
                resp = await client.post(
                    oauth_cfg["token_url"],
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": _redirect_uri(integration),
                        "grant_type": "authorization_code",
                    },
                )
                resp.raise_for_status()
                token_data = resp.json()

            elif provider == "github":
                resp = await client.post(
                    oauth_cfg["token_url"],
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": _redirect_uri(integration),
                    },
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                token_data = resp.json()

            elif provider == "slack":
                resp = await client.post(
                    oauth_cfg["token_url"],
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": _redirect_uri(integration),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    token_data = {
                        "access_token": data.get("access_token"),
                        "team": data.get("team", {}),
                    }
                else:
                    raise ValueError(data.get("error", "Slack OAuth failed"))

            else:
                raise ValueError(f"Unsupported OAuth provider: {provider}")

        if token_data.get("expires_in"):
            token_data["expires_at"] = credentials_store.compute_expires_at(
                token_data["expires_in"]
            )

        await credentials_store.store_token(integration_id, token_data)
        return {"integration_id": integration_id, "connected": True}

    async def refresh_token(self, integration_id: str) -> bool:
        """Refresh Google OAuth token if refresh_token is available."""
        token = await credentials_store.get_token(integration_id)
        if not token or not token.get("refresh_token"):
            return False

        integration = get_integration(integration_id)
        if not integration:
            return False

        env_keys = integration["env_keys"]
        client_id = _env(env_keys[0])
        client_secret = _env(env_keys[1]) if len(env_keys) > 1 else ""

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                integration["oauth"]["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": token["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code != 200:
                return False
            new_data = resp.json()
            token.update(new_data)
            if new_data.get("expires_in"):
                token["expires_at"] = credentials_store.compute_expires_at(
                    new_data["expires_in"]
                )
            await credentials_store.store_token(integration_id, token)
            return True


oauth_handler = OAuthHandler()
