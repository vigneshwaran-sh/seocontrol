from pydantic import BaseModel
from datetime import datetime


class LLMLogResponse(BaseModel):
    id: str
    task_id: str
    task_title: str
    space_id: str
    agent_id: str
    agent_name: str
    agent_role: str
    provider: str
    model: str
    request: list[dict]
    response: str
    is_cached: bool
    duration_ms: int
    created_at: datetime


class LLMLogListResponse(BaseModel):
    logs: list[LLMLogResponse]
    total: int
    page: int
    limit: int
    pages: int
