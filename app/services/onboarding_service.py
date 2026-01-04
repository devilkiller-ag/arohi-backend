"""Service for generating onboarding messages for new users."""

from typing import Optional
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.message import Message, MessageStatus


class OnboardingService:
    """Service for handling new user onboarding."""

    def get_welcome_message(self, user_name: str) -> str:
        """
        Generate a personalized welcome message for a new user.
        This is the coach's first message to start the conversation.
        """
        # First name only for more personal feel
        first_name = user_name.split()[0] if user_name else "there"

        return f"""Hey {first_name}, welcome! I'm Arohi, and I'll be your health coach.

I've been helping people like you make real, lasting changes to their health for about 5 years now. Before we dive in, I'd love to understand what's bringing you here.

What's the one thing about your health you'd most like to change or improve?"""

    def check_needs_onboarding(self, user_id, db: Session) -> bool:
        """Check if user needs onboarding (has no messages yet)."""
        message_count = db.query(Message).filter(Message.user_id == user_id).count()
        return message_count == 0

    def create_onboarding_message(self, user: User, db: Session) -> Optional[Message]:
        """
        Create the initial onboarding message from the coach.
        Returns None if user already has messages.
        """
        if not self.check_needs_onboarding(user.id, db):
            return None

        welcome_content = self.get_welcome_message(user.name)

        message = Message(
            user_id=user.id,
            role="assistant",
            content=welcome_content,
            status=MessageStatus.DELIVERED.value,
        )
        db.add(message)
        db.commit()
        db.refresh(message)

        return message


# Singleton instance
onboarding_service = OnboardingService()


def get_onboarding_service() -> OnboardingService:
    """Get the onboarding service instance."""
    return onboarding_service
