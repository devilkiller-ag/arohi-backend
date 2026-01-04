from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field


class MessageBase(BaseModel):
    """Base message schema."""
    content: str = Field(..., min_length=1, max_length=4000)


class MessageCreate(MessageBase):
    """Schema for creating a message."""
    pass


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: UUID
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Schema for paginated message list response."""
    messages: list[MessageResponse]
    has_more: bool
    next_cursor: Optional[str] = None


class ChatResponse(BaseModel):
    """Schema for chat response (user message + AI response)."""
    user_message: MessageResponse
    assistant_message: MessageResponse
