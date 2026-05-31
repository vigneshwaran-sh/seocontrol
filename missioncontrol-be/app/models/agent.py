from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AgentCreate(BaseModel):
    name: str = Field(min_length=1)
    avatar: str = "\U0001f916"  # emoji
    description: str = ""
    role: str = ""  # pipeline role: content_researcher, topic_validator, content_writer, content_validator
    provider: str = ""  # "openai", "gemini", "claude"
    model: str = ""  # e.g. "gpt-4o", "claude-sonnet-4-20250514"
    skill_content: str = ""  # rich-text (HTML) instruction manual for the agent


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    is_active: Optional[bool] = None
    skill_content: Optional[str] = None


class AgentResponse(BaseModel):
    id: str
    space_id: str
    name: str
    avatar: str
    description: str
    role: str
    provider: str
    model: str
    skill_content: str
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
