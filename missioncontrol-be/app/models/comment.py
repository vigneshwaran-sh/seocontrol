from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CommentCreate(BaseModel):
    content: str = Field(min_length=1)
    mentions: list[dict] = []  # [{"id": "...", "type": "user"|"agent", "name": "..."}]


class CommentUpdate(BaseModel):
    content: Optional[str] = None
    mentions: Optional[list[dict]] = None


class CommentResponse(BaseModel):
    id: str
    task_id: str
    content: str
    mentions: list[dict]
    created_by: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
