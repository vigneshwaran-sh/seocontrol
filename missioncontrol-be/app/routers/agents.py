from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import get_db
from app.models.agent import AgentCreate, AgentUpdate, AgentResponse
from app.utils import serialize_agent

router = APIRouter(prefix="/api/spaces/{space_id}/agents", tags=["agents"])

# Pipeline role ordering for consistent display
_ROLE_ORDER = {
    "content_researcher": 0,
    "topic_validator": 1,
    "content_writer": 2,
    "content_validator": 3,
}


# ---------------------------------------------------------------------------
# Agents CRUD
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[AgentResponse])
async def list_agents(space_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    agents = await db.agents.find({"space_id": space_id}).to_list(length=100)
    # Sort by pipeline role order, then by name for non-pipeline agents
    agents.sort(key=lambda a: (_ROLE_ORDER.get(a.get("role", ""), 99), a.get("name", "")))
    return [serialize_agent(a) for a in agents]


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    space_id: str, body: AgentCreate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    now = datetime.utcnow()
    doc = {
        "space_id": space_id,
        "name": body.name,
        "avatar": body.avatar,
        "description": body.description,
        "role": body.role,
        "provider": body.provider,
        "model": body.model,
        "skill_content": body.skill_content,
        "is_active": True,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.agents.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_agent(doc)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    space_id: str, agent_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(agent_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    agent = await db.agents.find_one({"_id": ObjectId(agent_id), "space_id": space_id})
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return serialize_agent(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    space_id: str,
    agent_id: str,
    body: AgentUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(agent_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        updates["name"] = body.name
    if body.avatar is not None:
        updates["avatar"] = body.avatar
    if body.description is not None:
        updates["description"] = body.description
    if body.provider is not None:
        updates["provider"] = body.provider
    if body.model is not None:
        updates["model"] = body.model
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.skill_content is not None:
        updates["skill_content"] = body.skill_content

    result = await db.agents.find_one_and_update(
        {"_id": ObjectId(agent_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return serialize_agent(result)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    space_id: str, agent_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(agent_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    result = await db.agents.delete_one({"_id": ObjectId(agent_id), "space_id": space_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Clean up: unassign this agent from any tasks
    await db.tasks.update_many(
        {"assignee_id": agent_id, "assignee_type": "agent"},
        {"$set": {"assignee_id": None, "assignee_type": None}},
    )
