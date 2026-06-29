from pydantic import BaseModel, field_validator
from datetime import datetime
import re

class ProcessRequest(BaseModel):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        youtube_regex = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+"
        if not re.match(youtube_regex, value):
            raise ValueError("Invalid YouTube URL format.")
        return value

class ProcessInitResponse(BaseModel):
    video_id: str
    status: str

class VideoStatusResponse(BaseModel):
    status: str
    video_id: str
    transcript: str | None = None
    summary: str | None = None

class VideoListItemResponse(BaseModel):
    id: str
    url: str
    status: str
    created_at: datetime # Directly maps the Python datetime object

    class Config:
        from_attributes = True # @dev what is this?

class VideoListResponse(BaseModel):
    total_count: int
    page: int
    limit: int
    items: list[VideoListItemResponse]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    role: str
    content: str