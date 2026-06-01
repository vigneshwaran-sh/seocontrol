from pydantic import BaseModel
from datetime import datetime


class LLMLogResponse(BaseModel):
    id: str
    task_id: str
    agent_id: str
    space_id: str
    provider: str
    model: str
    request: dict
    response: str
    duration_ms: int
    requested_at: datetime
    created_at: datetime


class LLMLogListResponse(BaseModel):
    logs: list[LLMLogResponse]
    total: int
    page: int
    limit: int
    pages: int
