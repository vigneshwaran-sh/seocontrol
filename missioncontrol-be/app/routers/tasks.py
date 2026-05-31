from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import get_db
from app.models.task import (
    TaskCreate,
    TaskMoveRequest,
    TaskStatusCreate,
    TaskStatusUpdate,
    TaskStatusResponse,
    TaskUpdate,
    TaskResponse,
)
from app.models.comment import CommentCreate, CommentUpdate, CommentResponse
from app.utils import serialize_task, serialize_task_status, serialize_comment

import logging

log = logging.getLogger(__name__)


async def _maybe_dispatch_agent_task(
    task_id: str, space_id: str,
    assignee_type: str | None, assignee_id: str | None = None,
):
    """If the task is assigned to a pipeline agent, dispatch the right step."""
    if assignee_type != "agent" or not assignee_id:
        return

    try:
        from app.database import get_db as _get_db
        db = _get_db()
        agent = await db.agents.find_one({"_id": ObjectId(assignee_id)})
        if not agent:
            log.warning(f"Agent {assignee_id} not found, skipping dispatch.")
            return

        role = agent.get("role", "")

        if role == "content_writer":
            from app.worker.tasks import run_content_writer
            run_content_writer.delay(task_id, space_id)
            log.info(f"Dispatched Content Writer for task {task_id}")
        elif role == "topic_validator":
            from app.worker.tasks import run_topic_validator
            run_topic_validator.delay(task_id, space_id)
            log.info(f"Dispatched Topic Validator for task {task_id}")
        elif role == "content_validator":
            from app.worker.tasks import run_content_validator
            run_content_validator.delay(task_id, space_id)
            log.info(f"Dispatched Content Validator for task {task_id}")
        elif role == "content_researcher":
            from app.worker.tasks import run_content_researcher
            run_content_researcher.delay(space_id)
            log.info(f"Dispatched Content Researcher for space {space_id}")
        else:
            log.warning(f"Agent {assignee_id} has unknown role '{role}', skipping.")
    except Exception as exc:
        # Don't fail the API request if Celery/Redis is down
        log.warning(f"Could not dispatch agent task {task_id}: {exc}")

router = APIRouter(prefix="/api/spaces/{space_id}/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Assignees (combined users + agents for task assignment dropdown)
# ---------------------------------------------------------------------------


@router.get("/assignees", response_model=list)
async def list_assignees(space_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    # Get all active users
    users = await db.users.find({"is_active": True}).to_list(length=100)
    user_list = [
        {"id": str(u["_id"]), "name": u["full_name"], "type": "user", "avatar": None}
        for u in users
    ]

    # Get all active agents in this space
    agents = await db.agents.find({"space_id": space_id, "is_active": True}).to_list(length=100)
    agent_list = [
        {"id": str(a["_id"]), "name": a["name"], "type": "agent", "avatar": a.get("avatar", "\U0001f916")}
        for a in agents
    ]

    return user_list + agent_list


# ---------------------------------------------------------------------------
# Task Statuses
# ---------------------------------------------------------------------------


@router.get("/statuses", response_model=list[TaskStatusResponse])
async def list_statuses(space_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    statuses = (
        await db.task_statuses.find({"space_id": space_id})
        .sort("position", 1)
        .to_list(length=100)
    )
    return [serialize_task_status(s) for s in statuses]


@router.post("/statuses", response_model=TaskStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_status(
    space_id: str, body: TaskStatusCreate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    # Determine next position
    last = await db.task_statuses.find_one(
        {"space_id": space_id}, sort=[("position", -1)]
    )
    next_pos = (last["position"] + 1) if last else 0

    doc = {
        "space_id": space_id,
        "name": body.name,
        "color": body.color,
        "position": next_pos,
        "is_default": False,
    }
    result = await db.task_statuses.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_task_status(doc)


@router.put("/statuses/{status_id}", response_model=TaskStatusResponse)
async def update_status(
    space_id: str,
    status_id: str,
    body: TaskStatusUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(status_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.color is not None:
        updates["color"] = body.color
    if body.position is not None:
        updates["position"] = body.position

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    result = await db.task_statuses.find_one_and_update(
        {"_id": ObjectId(status_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")
    return serialize_task_status(result)


@router.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_status(
    space_id: str, status_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(status_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    # Prevent deletion if tasks use this status
    task_count = await db.tasks.count_documents({"status_id": status_id})
    if task_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete status: {task_count} task(s) still use it",
        )

    result = await db.task_statuses.delete_one(
        {"_id": ObjectId(status_id), "space_id": space_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    space_id: str,
    status_id: str | None = Query(default=None),
    assignee_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    query: dict = {"space_id": space_id}
    if status_id:
        query["status_id"] = status_id
    if assignee_id:
        query["assignee_id"] = assignee_id

    tasks = await db.tasks.find(query).sort("position", 1).to_list(length=500)
    return [serialize_task(t) for t in tasks]


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    space_id: str, body: TaskCreate, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID")

    # Resolve status_id
    task_status_id = body.status_id
    if not task_status_id:
        default_status = await db.task_statuses.find_one(
            {"space_id": space_id, "is_default": True}
        )
        if not default_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No default status found for this space",
            )
        task_status_id = str(default_status["_id"])

    # Auto-set position to end
    last_task = await db.tasks.find_one(
        {"space_id": space_id, "status_id": task_status_id},
        sort=[("position", -1)],
    )
    next_pos = (last_task["position"] + 1) if last_task else 0

    now = datetime.utcnow()
    doc = {
        "space_id": space_id,
        "status_id": task_status_id,
        "title": body.title,
        "description": body.description,
        "priority": body.priority.value,
        "assignee_id": body.assignee_id,
        "assignee_type": body.assignee_type,
        "due_date": body.due_date,
        "tags": body.tags,
        "position": next_pos,
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.tasks.insert_one(doc)
    doc["_id"] = result.inserted_id

    # If assigned to an agent, dispatch immediately
    await _maybe_dispatch_agent_task(
        str(result.inserted_id), space_id, body.assignee_type, body.assignee_id,
    )

    return serialize_task(doc)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    space_id: str, task_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    task = await db.tasks.find_one({"_id": ObjectId(task_id), "space_id": space_id})
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return serialize_task(task)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    space_id: str,
    task_id: str,
    body: TaskUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.title is not None:
        updates["title"] = body.title
    if body.status_id is not None:
        updates["status_id"] = body.status_id
    if body.description is not None:
        updates["description"] = body.description
    if body.priority is not None:
        updates["priority"] = body.priority.value
    if body.assignee_id is not None:
        updates["assignee_id"] = body.assignee_id
    if body.assignee_type is not None:
        updates["assignee_type"] = body.assignee_type
    if body.due_date is not None:
        updates["due_date"] = body.due_date
    if body.tags is not None:
        updates["tags"] = body.tags
    if body.position is not None:
        updates["position"] = body.position

    # Check if assignee changed to an agent
    old_task = await db.tasks.find_one({"_id": ObjectId(task_id), "space_id": space_id})

    result = await db.tasks.find_one_and_update(
        {"_id": ObjectId(task_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # If newly assigned to an agent, dispatch
    if (
        body.assignee_type == "agent"
        and body.assignee_id
        and old_task
        and (old_task.get("assignee_id") != body.assignee_id or old_task.get("assignee_type") != "agent")
    ):
        await _maybe_dispatch_agent_task(task_id, space_id, "agent", body.assignee_id)

    return serialize_task(result)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    space_id: str, task_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    result = await db.tasks.delete_one({"_id": ObjectId(task_id), "space_id": space_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@router.put("/{task_id}/move", response_model=TaskResponse)
async def move_task(
    space_id: str,
    task_id: str,
    body: TaskMoveRequest,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    updates = {
        "status_id": body.status_id,
        "position": body.position,
        "updated_at": datetime.utcnow(),
    }

    result = await db.tasks.find_one_and_update(
        {"_id": ObjectId(task_id), "space_id": space_id},
        {"$set": updates},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return serialize_task(result)


# ---------------------------------------------------------------------------
# Task Comments
# ---------------------------------------------------------------------------


@router.get("/{task_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    space_id: str, task_id: str, user: dict = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    comments = (
        await db.comments.find({"task_id": task_id})
        .sort("created_at", 1)
        .to_list(length=500)
    )
    return [serialize_comment(c) for c in comments]


@router.post(
    "/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    space_id: str,
    task_id: str,
    body: CommentCreate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    # Verify task exists
    task = await db.tasks.find_one({"_id": ObjectId(task_id), "space_id": space_id})
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    now = datetime.utcnow()
    doc = {
        "task_id": task_id,
        "content": body.content,
        "mentions": body.mentions,
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": now,
        "updated_at": now,
    }
    result = await db.comments.insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_comment(doc)


@router.put("/{task_id}/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    space_id: str,
    task_id: str,
    comment_id: str,
    body: CommentUpdate,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if (
        not ObjectId.is_valid(space_id)
        or not ObjectId.is_valid(task_id)
        or not ObjectId.is_valid(comment_id)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    comment = await db.comments.find_one({"_id": ObjectId(comment_id), "task_id": task_id})
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Only the author can edit
    if comment["created_by"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own comments",
        )

    updates: dict = {"updated_at": datetime.utcnow()}
    if body.content is not None:
        updates["content"] = body.content
    if body.mentions is not None:
        updates["mentions"] = body.mentions

    result = await db.comments.find_one_and_update(
        {"_id": ObjectId(comment_id)},
        {"$set": updates},
        return_document=True,
    )
    return serialize_comment(result)


@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    space_id: str,
    task_id: str,
    comment_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if (
        not ObjectId.is_valid(space_id)
        or not ObjectId.is_valid(task_id)
        or not ObjectId.is_valid(comment_id)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID")

    comment = await db.comments.find_one({"_id": ObjectId(comment_id), "task_id": task_id})
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Only the author or admins can delete
    if comment["created_by"] != user["id"] and user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own comments",
        )

    await db.comments.delete_one({"_id": ObjectId(comment_id)})
