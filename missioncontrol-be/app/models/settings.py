from pydantic import BaseModel
from typing import Optional


class APIKeysUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None


class APIKeysResponse(BaseModel):
    openai_api_key: str = ""
    gemini_api_key: str = ""
    claude_api_key: str = ""


class NotionSettingsUpdate(BaseModel):
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None


class NotionSettingsResponse(BaseModel):
    notion_token: str = ""
    notion_database_id: str = ""
    connected: bool = False
