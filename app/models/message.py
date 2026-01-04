import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class MessageStatus(str, Enum):
    """Message delivery status for WhatsApp-like experience."""
    SENDING = "sending"      # Message being sent (clock icon)
    SENT = "sent"            # Single tick - sent to server
    DELIVERED = "delivered"  # Double tick - server processed
    READ = "read"            # Blue ticks - recipient read (future use)
    FAILED = "failed"        # Message failed, will retry


class Message(Base):
    """Chat message model for storing conversation history."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    status = Column(String(20), default=MessageStatus.SENT.value)  # Message delivery status
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.id} ({self.role})>"
