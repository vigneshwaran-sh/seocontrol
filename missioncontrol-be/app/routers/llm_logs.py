"""
Router for querying LLM call logs.
Supports filtering by agent, date range, and task title search.
"""

import math
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import get_db
from app.models.llm_log import LLMLogResponse, LLMLogListResponse
from app.utils import serialize_llm_log

router = APIRouter(prefix="/api/spaces/{space_id}/llm-logs", tags=["llm-logs"])


@router.get("/", response_model=LLMLogListResponse)
async def list_llm_logs(
    space_id: str,
    agent_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid space ID"
        )

    # Build query filter
    query: dict = {"space_id": space_id}

    if agent_id:
        query["agent_id"] = agent_id

    if date_from or date_to:
        date_filter: dict = {}
        if date_from:
            try:
                date_filter["$gte"] = datetime.fromisoformat(date_from)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date_from format (use ISO 8601)",
                )
        if date_to:
            try:
                # Include the entire end date
                dt = datetime.fromisoformat(date_to)
                date_filter["$lte"] = dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date_to format (use ISO 8601)",
                )
        query["created_at"] = date_filter

    if search:
        query["task_title"] = {"$regex": search, "$options": "i"}

    # Count total
    total = await db.llm_logs.count_documents(query)
    pages = max(1, math.ceil(total / limit))

    # Fetch page
    skip = (page - 1) * limit
    logs = (
        await db.llm_logs.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )

    return {
        "logs": [serialize_llm_log(log) for log in logs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }


@router.get("/{log_id}", response_model=LLMLogResponse)
async def get_llm_log(
    space_id: str,
    log_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if not ObjectId.is_valid(space_id) or not ObjectId.is_valid(log_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ID"
        )

    log = await db.llm_logs.find_one(
        {"_id": ObjectId(log_id), "space_id": space_id}
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Log not found"
        )
    return serialize_llm_log(log)
