"""OAuth token storage via macOS Keychain."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from security.keychain import keychain

log = logging.getLogger(__name__)

_KEY_PREFIX = "integration_token_"
_STATE_PREFIX = "oauth_state_"


class CredentialsStore:
    def _key(self, integration_id: str) -> str:
        return f"{_KEY_PREFIX}{integration_id}"

    async def store_token(self, integration_id: str, token_data: dict) -> None:
        token_data["stored_at"] = datetime.utcnow().isoformat()
        keychain.store(self._key(integration_id), json.dumps(token_data))
        log.info(f"Stored token for integration: {integration_id}")

    async def get_token(self, integration_id: str) -> dict | None:
        raw = keychain.retrieve(self._key(integration_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def delete_token(self, integration_id: str) -> None:
        keychain.delete(self._key(integration_id))
        log.info(f"Deleted token for integration: {integration_id}")

    async def has_valid_token(self, integration_id: str) -> bool:
        token = await self.get_token(integration_id)
        if not token:
            return False
        if token.get("access_token"):
            expires_at = token.get("expires_at")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at.replace("Z", ""))
                    if exp <= datetime.utcnow() and not token.get("refresh_token"):
                        return False
                except Exception:
                    pass
            return True
        return False

    async def store_oauth_state(self, state: str, integration_id: str) -> None:
        keychain.store(f"{_STATE_PREFIX}{state}", integration_id)

    async def pop_oauth_state(self, state: str) -> str | None:
        key = f"{_STATE_PREFIX}{state}"
        integration_id = keychain.retrieve(key)
        if integration_id:
            keychain.delete(key)
        return integration_id

    def compute_expires_at(self, expires_in: int | None) -> str | None:
        if not expires_in:
            return None
        return (datetime.utcnow() + timedelta(seconds=int(expires_in))).isoformat()


credentials_store = CredentialsStore()
