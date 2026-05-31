from datetime import datetime, timezone

import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import get_db
from app.models.settings import (
    APIKeysUpdate,
    APIKeysResponse,
    NotionSettingsUpdate,
    NotionSettingsResponse,
)

router = APIRouter(
    prefix="/api/orgs/{org_id}/settings",
    tags=["settings"],
)

_KEY_FIELDS = [
    "openai_api_key",
    "gemini_api_key",
    "claude_api_key",
]


def _mask_key(value: str) -> str:
    """Return a masked version of the key, showing only last 4 characters."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _build_response(doc: dict | None) -> APIKeysResponse:
    if not doc:
        return APIKeysResponse()
    return APIKeysResponse(
        openai_api_key=_mask_key(doc.get("openai_api_key", "")),
        gemini_api_key=_mask_key(doc.get("gemini_api_key", "")),
        claude_api_key=_mask_key(doc.get("claude_api_key", "")),
    )


@router.get("/api-keys", response_model=APIKeysResponse)
async def get_api_keys(org_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )

    db = get_db()
    doc = await db.org_settings.find_one({"org_id": org_id})
    return _build_response(doc)


@router.put("/api-keys", response_model=APIKeysResponse)
async def update_api_keys(
    org_id: str, body: APIKeysUpdate, user: dict = Depends(get_current_user)
):
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )

    # Only admins can update API keys
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to manage API keys",
        )

    db = get_db()

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    for field in _KEY_FIELDS:
        value = getattr(body, field, None)
        if value is not None:
            updates[field] = value.strip()

    await db.org_settings.update_one(
        {"org_id": org_id},
        {
            "$set": updates,
            "$setOnInsert": {
                "org_id": org_id,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    doc = await db.org_settings.find_one({"org_id": org_id})
    return _build_response(doc)


# ---------------------------------------------------------------------------
# Provider model listing
# ---------------------------------------------------------------------------

_PROVIDER_KEY_MAP = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
    "claude": "claude_api_key",
}


@router.get("/providers/{provider}/models")
async def list_provider_models(
    org_id: str, provider: str, user: dict = Depends(get_current_user)
):
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )
    if provider not in _PROVIDER_KEY_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider}. Use one of: {', '.join(_PROVIDER_KEY_MAP)}",
        )

    db = get_db()
    doc = await db.org_settings.find_one({"org_id": org_id})
    key_field = _PROVIDER_KEY_MAP[provider]
    api_key = (doc or {}).get(key_field, "")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No API key configured for {provider}. Add one in Settings → API Keys.",
        )

    fetchers = {
        "openai": _fetch_openai_models,
        "gemini": _fetch_gemini_models,
        "claude": _fetch_claude_models,
    }
    try:
        models = await fetchers[provider](api_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch models from {provider}: {str(exc)}",
        )

    return {"provider": provider, "models": models}


async def _fetch_openai_models(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API key")
    resp.raise_for_status()

    data = resp.json().get("data", [])
    # Keep chat/completion models, skip embeddings, whisper, tts, dall-e etc.
    skip_prefixes = ("whisper", "tts", "dall-e", "text-embedding", "babbage", "davinci", "moderation")
    models = []
    for m in data:
        mid = m["id"]
        if any(mid.startswith(p) for p in skip_prefixes):
            continue
        models.append({"id": mid, "name": mid})
    models.sort(key=lambda x: x["id"])
    return models


async def _fetch_gemini_models(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
    if resp.status_code == 400 or resp.status_code == 403:
        raise HTTPException(status_code=401, detail="Invalid Gemini API key")
    resp.raise_for_status()

    data = resp.json().get("models", [])
    models = []
    for m in data:
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        full_name = m.get("name", "")
        model_id = full_name.replace("models/", "") if full_name.startswith("models/") else full_name
        display = m.get("displayName", model_id)
        models.append({"id": model_id, "name": display})
    models.sort(key=lambda x: x["id"])
    return models


async def _fetch_claude_models(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid Claude API key")
    resp.raise_for_status()

    data = resp.json().get("data", [])
    models = []
    for m in data:
        mid = m.get("id", "")
        display = m.get("display_name", mid)
        models.append({"id": mid, "name": display})
    models.sort(key=lambda x: x["id"])
    return models


# ---------------------------------------------------------------------------
# Notion integration
# ---------------------------------------------------------------------------


@router.get("/notion", response_model=NotionSettingsResponse)
async def get_notion_settings(org_id: str, user: dict = Depends(get_current_user)):
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )

    db = get_db()
    doc = await db.org_settings.find_one({"org_id": org_id})
    token = (doc or {}).get("notion_token", "")
    database_id = (doc or {}).get("notion_database_id", "")
    return NotionSettingsResponse(
        notion_token=_mask_key(token),
        notion_database_id=database_id,
        connected=bool(token),
    )


@router.put("/notion", response_model=NotionSettingsResponse)
async def update_notion_settings(
    org_id: str, body: NotionSettingsUpdate, user: dict = Depends(get_current_user)
):
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )

    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to manage Notion settings",
        )

    db = get_db()

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.notion_token is not None:
        updates["notion_token"] = body.notion_token.strip()
    if body.notion_database_id is not None:
        updates["notion_database_id"] = body.notion_database_id.strip()

    # Validate token if provided
    token = body.notion_token.strip() if body.notion_token else None
    if token:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": "2022-06-28",
                },
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Notion token. Please check and try again.",
            )

    await db.org_settings.update_one(
        {"org_id": org_id},
        {
            "$set": updates,
            "$setOnInsert": {
                "org_id": org_id,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    doc = await db.org_settings.find_one({"org_id": org_id})
    new_token = (doc or {}).get("notion_token", "")
    database_id = (doc or {}).get("notion_database_id", "")
    return NotionSettingsResponse(
        notion_token=_mask_key(new_token),
        notion_database_id=database_id,
        connected=bool(new_token),
    )


@router.post("/notion/test")
async def test_notion_connection(org_id: str, user: dict = Depends(get_current_user)):
    """Test the Notion connection and return workspace info."""
    if not ObjectId.is_valid(org_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID"
        )

    db = get_db()
    doc = await db.org_settings.find_one({"org_id": org_id})
    token = (doc or {}).get("notion_token", "")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Notion token configured.",
        )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.notion.com/v1/users/me",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notion connection failed. Token may be invalid or expired.",
        )

    data = resp.json()
    return {
        "status": "connected",
        "bot_name": data.get("name", ""),
        "workspace": data.get("bot", {}).get("workspace_name", ""),
    }
