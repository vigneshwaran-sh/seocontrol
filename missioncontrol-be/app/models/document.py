from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Folder models ---

class FolderCreate(BaseModel):
    name: str = Field(min_length=1)
    parent_id: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    position: Optional[int] = None


class FolderResponse(BaseModel):
    id: str
    space_id: str
    parent_id: Optional[str] = None
    name: str
    position: int
    created_by: str
    created_at: datetime
    updated_at: datetime


# --- Document models ---

class DocCreate(BaseModel):
    title: str = Field(min_length=1)
    folder_id: Optional[str] = None
    content: str = ""


class DocUpdate(BaseModel):
    title: Optional[str] = None
    folder_id: Optional[str] = None
    content: Optional[str] = None


class DocResponse(BaseModel):
    id: str
    space_id: str
    folder_id: Optional[str] = None
    title: str
    content: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
