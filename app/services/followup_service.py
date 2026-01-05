"""Service for managing follow-up messages and user engagement."""

from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.user import User
from app.models.message import Message
from app.models.followup import (
    ScheduledFollowUp,
    UserEngagement,
    FollowUpType,
    FollowUpStatus,
)
from app.models.memory import Memory
from app.config import get_settings

settings = get_settings()


class FollowUpService:
    """Service for scheduling and managing follow-up messages.

    Note: Scheduling intent detection is now handled by the LLM service
    which returns structured output with scheduling information.
    This allows language-agnostic detection (English, Hindi, Hinglish, etc.)
    """

    def schedule_user_reminder(
        self,
        user_id: UUID,
        minutes_from_now: int,
        context: str,
        db: Session,
    ) -> ScheduledFollowUp:
        """Schedule a user-requested reminder."""
        scheduled_time = datetime.utcnow() + timedelta(minutes=minutes_from_now)

        followup = ScheduledFollowUp(
            user_id=user_id,
            scheduled_at=scheduled_time,
            followup_type=FollowUpType.USER_REQUESTED.value,
            context=context,
            status=FollowUpStatus.PENDING.value,
        )
        db.add(followup)
        db.commit()
        db.refresh(followup)

        return followup

    def schedule_proactive_followup(
        self,
        user_id: UUID,
        followup_type: FollowUpType,
        scheduled_time: datetime,
        context: Optional[str],
        db: Session,
    ) -> ScheduledFollowUp:
        """Schedule a proactive follow-up (inactivity check, plan check-in, etc.)."""
        # Check if there's already a pending followup of this type
        existing = (
            db.query(ScheduledFollowUp)
            .filter(
                ScheduledFollowUp.user_id == user_id,
                ScheduledFollowUp.followup_type == followup_type.value,
                ScheduledFollowUp.status == FollowUpStatus.PENDING.value,
            )
            .first()
        )

        if existing:
            # Update existing followup time
            existing.scheduled_at = scheduled_time
            existing.context = context
            db.commit()
            return existing

        followup = ScheduledFollowUp(
            user_id=user_id,
            scheduled_at=scheduled_time,
            followup_type=followup_type.value,
            context=context,
            status=FollowUpStatus.PENDING.value,
        )
        db.add(followup)
        db.commit()
        db.refresh(followup)

        return followup

    def get_pending_followups(self, db: Session) -> List[ScheduledFollowUp]:
        """Get all follow-ups that are due to be sent."""
        now = datetime.utcnow()
        return (
            db.query(ScheduledFollowUp)
            .filter(
                ScheduledFollowUp.scheduled_at <= now,
                ScheduledFollowUp.status == FollowUpStatus.PENDING.value,
            )
            .order_by(ScheduledFollowUp.scheduled_at)
            .all()
        )

    def mark_followup_sent(
        self,
        followup_id: UUID,
        db: Session,
    ) -> None:
        """Mark a follow-up as sent."""
        followup = db.query(ScheduledFollowUp).filter(ScheduledFollowUp.id == followup_id).first()
        if followup:
            followup.status = FollowUpStatus.SENT.value
            followup.sent_at = datetime.utcnow()
            db.commit()

    def mark_followup_failed(
        self,
        followup_id: UUID,
        db: Session,
    ) -> None:
        """Mark a follow-up as failed and increment retry count."""
        followup = db.query(ScheduledFollowUp).filter(ScheduledFollowUp.id == followup_id).first()
        if followup:
            followup.retry_count += 1
            if followup.retry_count >= 3:
                followup.status = FollowUpStatus.FAILED.value
            db.commit()

    def cancel_user_followups(self, user_id: UUID, db: Session) -> int:
        """Cancel all pending follow-ups for a user. Returns count cancelled."""
        result = (
            db.query(ScheduledFollowUp)
            .filter(
                ScheduledFollowUp.user_id == user_id,
                ScheduledFollowUp.status == FollowUpStatus.PENDING.value,
            )
            .update({ScheduledFollowUp.status: FollowUpStatus.CANCELLED.value})
        )
        db.commit()
        return result

    # =========== User Engagement Tracking ===========

    def get_or_create_engagement(self, user_id: UUID, db: Session) -> UserEngagement:
        """Get or create user engagement record."""
        engagement = db.query(UserEngagement).filter(UserEngagement.user_id == user_id).first()

        if not engagement:
            engagement = UserEngagement(user_id=user_id)
            db.add(engagement)
            db.commit()
            db.refresh(engagement)

        return engagement

    def update_user_activity(self, user_id: UUID, db: Session) -> None:
        """Update user engagement when they send a message."""
        engagement = self.get_or_create_engagement(user_id, db)

        now = datetime.utcnow()
        engagement.last_message_at = now
        engagement.total_messages += 1

        # Update preferred time (simple rolling average approach)
        current_hour = now.hour
        if engagement.preferred_time_hour is None:
            engagement.preferred_time_hour = current_hour
        else:
            # Weighted average favoring recent activity
            engagement.preferred_time_hour = int(
                (engagement.preferred_time_hour * 0.7) + (current_hour * 0.3)
            )

        db.commit()

    def get_users_needing_followup(self, db: Session) -> List[Tuple[User, UserEngagement, str]]:
        """
        Find users who need a proactive follow-up.

        Returns list of (User, UserEngagement, followup_reason) tuples.
        """
        users_needing_followup = []
        now = datetime.utcnow()

        # Get all users with engagement records who have followups enabled
        engagements = (
            db.query(UserEngagement)
            .filter(UserEngagement.followup_enabled == True)
            .all()
        )

        for engagement in engagements:
            user = db.query(User).filter(User.id == engagement.user_id).first()
            if not user:
                continue

            # Skip if we sent a followup recently
            if engagement.last_followup_sent_at:
                hours_since_followup = (now - engagement.last_followup_sent_at).total_seconds() / 3600
                if hours_since_followup < engagement.followup_frequency_hours:
                    continue

            # Check for inactivity
            if engagement.last_message_at:
                hours_inactive = (now - engagement.last_message_at).total_seconds() / 3600

                # Inactivity follow-up
                if hours_inactive >= settings.followup_inactivity_hours:
                    users_needing_followup.append((user, engagement, "inactivity"))
                    continue

                # Plan check-in (if user has active plan)
                if engagement.has_active_plan and hours_inactive >= settings.followup_plan_checkin_hours:
                    users_needing_followup.append((user, engagement, "plan_checkin"))
                    continue

        return users_needing_followup

    def generate_followup_context(
        self,
        user: User,
        engagement: UserEngagement,
        followup_type: str,
        db: Session,
    ) -> str:
        """Generate context for the LLM to create a follow-up message."""
        # Get recent messages for context
        recent_messages = (
            db.query(Message)
            .filter(Message.user_id == user.id)
            .order_by(desc(Message.created_at))
            .limit(5)
            .all()
        )

        # Get user memories
        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user.id)
            .order_by(desc(Memory.created_at))
            .limit(10)
            .all()
        )

        context_parts = [f"User's name: {user.name or 'Unknown'}"]

        if memories:
            memory_facts = [m.fact for m in memories]
            context_parts.append(f"Known facts about user: {', '.join(memory_facts)}")

        if recent_messages:
            last_msg = recent_messages[0]
            time_ago = datetime.utcnow() - last_msg.created_at
            hours_ago = int(time_ago.total_seconds() / 3600)
            days_ago = hours_ago // 24

            if days_ago > 0:
                context_parts.append(f"Last conversation was {days_ago} day(s) ago")
            else:
                context_parts.append(f"Last conversation was {hours_ago} hour(s) ago")

            # Include last exchange
            last_exchange = []
            for msg in reversed(recent_messages[:2]):
                last_exchange.append(f"{msg.role}: {msg.content[:200]}...")
            context_parts.append(f"Last exchange:\n" + "\n".join(last_exchange))

        if engagement.current_goals:
            context_parts.append(f"Current goals: {engagement.current_goals}")

        if followup_type == "inactivity":
            context_parts.append(
                "FOLLOWUP REASON: User hasn't messaged in a while. "
                "Send a warm, non-pushy message checking in on them."
            )
        elif followup_type == "plan_checkin":
            context_parts.append(
                "FOLLOWUP REASON: Checking in on user's health plan progress. "
                "Ask how they're doing with their goals, if they're facing any challenges."
            )
        elif followup_type == "user_requested":
            context_parts.append(
                "FOLLOWUP REASON: User requested this reminder. "
                "Reference what they asked you to remind them about."
            )

        return "\n".join(context_parts)

    def update_followup_sent(self, user_id: UUID, db: Session) -> None:
        """Update engagement record when a follow-up is sent."""
        engagement = self.get_or_create_engagement(user_id, db)
        engagement.last_followup_sent_at = datetime.utcnow()
        db.commit()


# Singleton instance
followup_service = FollowUpService()


def get_followup_service() -> FollowUpService:
    """Get the follow-up service instance."""
    return followup_service
