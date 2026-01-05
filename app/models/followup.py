"""Models for follow-up scheduling and user engagement tracking."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class FollowUpType(str, Enum):
    """Types of follow-up messages."""
    USER_REQUESTED = "user_requested"  # User asked to be reminded
    INACTIVITY = "inactivity"  # User hasn't messaged in a while
    PLAN_CHECKIN = "plan_checkin"  # Check on plan/goal progress
    DAILY_CHECKIN = "daily_checkin"  # Daily health check-in
    MOTIVATION = "motivation"  # Motivational/encouragement message


class FollowUpStatus(str, Enum):
    """Status of a scheduled follow-up."""
    PENDING = "pending"  # Waiting to be sent
    SENT = "sent"  # Successfully sent
    FAILED = "failed"  # Failed to send
    CANCELLED = "cancelled"  # Cancelled by user or system


class ScheduledFollowUp(Base):
    """Scheduled follow-up messages to be sent to users."""

    __tablename__ = "scheduled_followups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Scheduling
    scheduled_at = Column(DateTime, nullable=False, index=True)
    sent_at = Column(DateTime, nullable=True)

    # Follow-up details
    followup_type = Column(String(50), nullable=False)
    status = Column(String(20), default=FollowUpStatus.PENDING.value, index=True)

    # Content (can be pre-generated or generated at send time)
    context = Column(Text, nullable=True)  # Context for generating message (e.g., "user asked about weight loss")
    message_content = Column(Text, nullable=True)  # Pre-generated message content (if any)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    retry_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="scheduled_followups")

    def __repr__(self):
        return f"<ScheduledFollowUp {self.id} ({self.followup_type}) for user {self.user_id}>"


class UserEngagement(Base):
    """Track user engagement for intelligent follow-up scheduling."""

    __tablename__ = "user_engagements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Activity tracking
    last_message_at = Column(DateTime, nullable=True)  # Last time user sent a message
    last_followup_sent_at = Column(DateTime, nullable=True)  # Last time we sent a follow-up
    total_messages = Column(Integer, default=0)
    total_sessions = Column(Integer, default=0)

    # Engagement patterns
    preferred_time_hour = Column(Integer, nullable=True)  # Hour of day user is most active (0-23)
    avg_response_time_minutes = Column(Integer, nullable=True)  # Average time to respond

    # Health journey tracking
    has_active_plan = Column(Boolean, default=False)  # User has an active health plan
    plan_start_date = Column(DateTime, nullable=True)
    current_goals = Column(Text, nullable=True)  # JSON string of current goals

    # Follow-up preferences
    followup_enabled = Column(Boolean, default=True)  # User allows proactive follow-ups
    followup_frequency_hours = Column(Integer, default=24)  # How often to send follow-ups

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="engagement")

    def __repr__(self):
        return f"<UserEngagement for user {self.user_id}>"
