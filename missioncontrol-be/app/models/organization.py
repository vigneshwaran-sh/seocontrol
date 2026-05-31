from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OrgCreate(BaseModel):
    name: str = Field(min_length=1)


class OrgUpdate(BaseModel):
    name: Optional[str] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_by: str
    created_at: datetime
    updated_at: datetime
