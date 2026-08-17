"""REST API for app integrations."""
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from integrations.credentials import credentials_store
from integrations.oauth import check_env_keys, oauth_handler
from integrations.registry import INTEGRATIONS, list_integrations

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/integrations")
async def list_all_integrations():
    """List all integrations with connection status."""
    result = []
    for item in list_integrations():
        iid = item["id"]
        connected = await credentials_store.has_valid_token(iid)
        env_status = check_env_keys(iid)
        result.append({
            **item,
            "connected": connected,
            "env_configured": env_status["configured"],
            "missing_env_keys": env_status["missing"],
        })
    return result


@router.get("/integrations/{integration_id}")
async def get_integration_status(integration_id: str):
    if integration_id not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail="Integration not found")
    connected = await credentials_store.has_valid_token(integration_id)
    env_status = check_env_keys(integration_id)
    return {
        "id": integration_id,
        **INTEGRATIONS[integration_id],
        "connected": connected,
        "env_configured": env_status["configured"],
        "missing_env_keys": env_status["missing"],
    }


@router.get("/integrations/{integration_id}/auth")
async def start_oauth(integration_id: str):
    """Start OAuth flow — returns redirect URL."""
    if integration_id not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        result = await oauth_handler.get_auth_url(integration_id)
        if result.get("error") == "env_missing":
            raise HTTPException(status_code=400, detail=result)
        return result
    except Exception as e:
        log.error(f"OAuth start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrations/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    """OAuth callback — exchange code for tokens."""
    try:
        result = await oauth_handler.handle_callback(code, state)
        return RedirectResponse(
            url=f"http://localhost:1420/settings?integration={result['integration_id']}&connected=1"
        )
    except Exception as e:
        log.error(f"OAuth callback failed: {e}")
        return RedirectResponse(
            url=f"http://localhost:1420/settings?integration_error={str(e)[:100]}"
        )


@router.post("/integrations/{integration_id}/disconnect")
async def disconnect(integration_id: str):
    if integration_id not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail="Integration not found")
    await credentials_store.delete_token(integration_id)
    return {"ok": True, "integration_id": integration_id}


@router.get("/integrations/{integration_id}/env-status")
async def env_status(integration_id: str):
    if integration_id not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail="Integration not found")
    return check_env_keys(integration_id)
