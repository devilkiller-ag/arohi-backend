from datetime import datetime
from uuid import UUID
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator, field_serializer


class MessageStatusEnum(str, Enum):
    """Message delivery status."""
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


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
    status: Optional[str] = "delivered"
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('status', mode='before')
    @classmethod
    def set_default_status(cls, v):
        return v if v is not None else 'delivered'

    @field_serializer('created_at')
    def serialize_created_at(self, dt: datetime) -> str:
        """Serialize datetime as UTC ISO string with Z suffix."""
        return dt.isoformat() + "Z"


class MessageListResponse(BaseModel):
    """Schema for paginated message list response."""
    messages: list[MessageResponse]
    has_more: bool
    next_cursor: Optional[str] = None


class ChatResponse(BaseModel):
    """Schema for chat response (user message + AI response)."""
    user_message: MessageResponse
    assistant_message: MessageResponse


# WebSocket message types
class WSMessageType(str, Enum):
    """WebSocket message types for real-time communication."""
    USER_MESSAGE = "user_message"         # User sends a message
    MESSAGE_SENT = "message_sent"         # Server confirms receipt (single tick)
    MESSAGE_DELIVERED = "message_delivered"  # Message processed (double tick)
    TYPING_START = "typing_start"         # Coach started typing
    TYPING_STOP = "typing_stop"           # Coach stopped typing
    ASSISTANT_MESSAGE = "assistant_message"  # Coach's response
    ERROR = "error"                       # Error occurred
    ONBOARDING = "onboarding"             # Onboarding message for new users


class WSMessage(BaseModel):
    """WebSocket message format."""
    type: WSMessageType
    data: dict = {}
