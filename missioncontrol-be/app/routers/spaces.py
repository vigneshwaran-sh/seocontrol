import re
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import get_db
from app.models.space import SpaceCreate, SpaceUpdate, SpaceResponse
from app.utils import serialize_space

router = APIRouter(prefix="/api/orgs/{org_id}/spaces", tags=["spaces"])

DEFAULT_STATUSES = [
    {"name": "To Do", "color": "#6B7280", "position": 0, "is_default": True},
    {"name": "In Progress", "color": "#F59E0B", "position": 1, "is_default": False},
    {"name": "In Review", "color": "#8B5CF6", "position": 2, "is_default": False},
    {"name": "Done", "color": "#10B981", "position": 3, "is_default": False},
]

PIPELINE_AGENTS = [
    {
        "role": "content_researcher",
        "name": "Content Researcher",
        "avatar": "\U0001f50d",
        "description": "Discovers trending topics and content ideas based on your niche. Runs daily.",
    },
    {
        "role": "topic_validator",
        "name": "Topic Validator",
        "avatar": "✅",
        "description": "Validates and shortlists topics for content creation.",
    },
    {
        "role": "content_writer",
        "name": "Content Writer",
        "avatar": "✍️",
        "description": "Writes blog content and publishes to Notion database.",
    },
    {
        "role": "content_validator",
        "name": "Content Validator",
        "avatar": "\U0001f4cb",
        "description": "Reviews content quality and approves or requests changes.",
    },
]


def _make_slug(name: str) -> str:
    slug = name.lower().strip().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug


@router.post("", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_space(org_id: str, body: SpaceCreate, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID")

    # Verify org exists
    org = await db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    now = datetime.utcnow()
    slug = _make_slug(body.name)

    doc = {
        "org_id": org_id,
        "name": body.name,
        "slug": slug,
        "icon": body.icon,
        "color": body.color,
        "description": body.description,
        "niche": body.niche,
        "topic_count": body.topic_count,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.spaces.insert_one(doc)
    doc["_id"] = result.inserted_id
    space_id = str(result.inserted_id)

    # Auto-create default task statuses
    status_docs = [
        {
            "space_id": space_id,
            "name": s["name"],
            "color": s["color"],
            "position": s["position"],
            "is_default": s["is_default"],
        }
        for s in DEFAULT_STATUSES
    ]
    await db.task_statuses.insert_many(status_docs)

    # Auto-seed pipeline agents
    agent_docs = [
        {
            "space_id": space_id,
            "role": a["role"],
            "name": a["name"],
            "avatar": a["avatar"],
            "description": a["description"],
            "provider": "",
            "model": "",
            "skill_content": "",
            "is_active": True,
            "created_by": user["id"],
            "created_at": now,
            "updated_at": now,
        }
        for a in PIPELINE_AGENTS
    ]
    await db.agents.insert_many(agent_docs)

    return serialize_space(doc)


@router.get("", response_model=list[SpaceResponse])
async def list_spaces(org_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid org ID")

    spaces = await db.spaces.find({"org_id": org_id}).sort("created_at", 1).to_list(length=100)
    return [serialize_space(s) for s in spaces]


@router.get("/{space_id}", response_model=SpaceResponse)
async def get_space(org_id: str, space_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id) or not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    space = await db.spaces.find_one({"_id": ObjectId(space_id), "org_id": org_id})
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return serialize_space(space)


@router.put("/{space_id}", response_model=SpaceResponse)
async def update_space(
    org_id: str, space_id: str, body: SpaceUpdate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(org_id) or not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        updates["name"] = body.name
        updates["slug"] = _make_slug(body.name)
    if body.icon is not None:
        updates["icon"] = body.icon
    if body.color is not None:
        updates["color"] = body.color
    if body.description is not None:
        updates["description"] = body.description
    if body.niche is not None:
        updates["niche"] = body.niche
    if body.topic_count is not None:
        updates["topic_count"] = body.topic_count

    result = await db.spaces.find_one_and_update(
        {"_id": ObjectId(space_id), "org_id": org_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return serialize_space(result)


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space(org_id: str, space_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(org_id) or not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    space = await db.spaces.find_one({"_id": ObjectId(space_id), "org_id": org_id})
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    # Cascade delete all related data
    await db.tasks.delete_many({"space_id": space_id})
    await db.task_statuses.delete_many({"space_id": space_id})
    await db.agents.delete_many({"space_id": space_id})

    await db.spaces.delete_one({"_id": ObjectId(space_id)})
