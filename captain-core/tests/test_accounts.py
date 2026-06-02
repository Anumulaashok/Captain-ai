"""Accounts API tests — service connection status."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_neon_check_success():
    """Test Neon DB check when connection is healthy."""
    from api.routes.accounts import _check_neon

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock()))
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("api.routes.accounts.engine") as mock_engine:
        mock_engine.connect.return_value = mock_ctx
        result = await _check_neon()
        assert result["status"] == "connected"
        assert result["provider"] == "Neon"


@pytest.mark.asyncio
async def test_neon_check_failure():
    """Test Neon DB check when connection fails."""
    from api.routes.accounts import _check_neon

    with patch("api.routes.accounts.engine") as mock_engine:
        mock_engine.connect.side_effect = Exception("connection refused")
        result = await _check_neon()
        assert result["status"] == "error"
        assert "connection refused" in result["error"]


def test_check_cloud_key_not_configured():
    from api.routes.accounts import _check_cloud_key
    from unittest.mock import patch

    with patch("api.routes.accounts.keychain") as mock_kc:
        mock_kc.retrieve.return_value = None
        with patch("api.routes.accounts.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = _check_cloud_key("openai")
            assert result["status"] == "not_configured"


def test_check_cloud_key_from_env():
    from api.routes.accounts import _check_cloud_key
    from unittest.mock import patch

    with patch("api.routes.accounts.keychain") as mock_kc:
        mock_kc.retrieve.return_value = None
        with patch("api.routes.accounts.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test-key"
            mock_settings.anthropic_api_key = ""
            mock_settings.gemini_api_key = ""
            result = _check_cloud_key("openai")
            assert result["status"] == "configured"
            assert result["source"] == "env"
