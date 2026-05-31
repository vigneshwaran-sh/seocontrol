from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1)
    icon: str = "\U0001f4c1"
    color: str = "#C4956A"
    description: Optional[str] = None
    niche: str = ""  # content niche for the pipeline, e.g. "AI & Machine Learning"
    topic_count: int = 5  # how many topics the Content Researcher generates per run


class SpaceUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    niche: Optional[str] = None
    topic_count: Optional[int] = None


class SpaceResponse(BaseModel):
    id: str
    org_id: str
    name: str
    slug: str
    icon: str
    color: str
    description: Optional[str] = None
    niche: str = ""
    topic_count: int = 5
    created_by: str
    created_at: datetime
    updated_at: datetime
