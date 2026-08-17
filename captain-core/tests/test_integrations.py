"""Tests for integrations registry and credentials."""
import pytest
from integrations.registry import INTEGRATIONS, get_integration, list_integrations


def test_integrations_registry():
    assert "gmail" in INTEGRATIONS
    assert "github" in INTEGRATIONS
    assert get_integration("gmail")["name"] == "Gmail"
    items = list_integrations()
    assert len(items) >= 4


@pytest.mark.asyncio
async def test_credentials_store_roundtrip():
    from integrations.credentials import credentials_store

    try:
        await credentials_store.store_token("test_integration", {
            "access_token": "test_token",
            "expires_in": 3600,
        })
    except Exception:
        pytest.skip("Keychain unavailable in this environment")

    assert await credentials_store.has_valid_token("test_integration")
    token = await credentials_store.get_token("test_integration")
    assert token["access_token"] == "test_token"
    await credentials_store.delete_token("test_integration")
    assert not await credentials_store.has_valid_token("test_integration")
