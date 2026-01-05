"""Celery tasks for follow-up message handling."""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.message import Message, MessageStatus
from app.models.followup import ScheduledFollowUp, FollowUpType, FollowUpStatus
from app.services.followup_service import get_followup_service
from app.services.llm_service import get_llm_service
from app.services.memory_service import get_memory_service
from app.services.profile_service import get_profile_service
from app.models.user_profile import OnboardingStage
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Follow-up message prompts for different scenarios
FOLLOWUP_PROMPTS = {
    "inactivity": """Generate a short, warm follow-up message for a user who hasn't messaged in a while.
Be casual and caring, not pushy. Ask how they're doing.
Keep it to 1-2 sentences max, like a WhatsApp message from a friend.
Do not use any emojis.""",

    "inactivity_onboarding": """Generate a warm follow-up for a user who left mid-conversation during onboarding.
Reference what you were last discussing, and gently continue gathering info about them.
Be casual - like checking in on a friend. Don't make it feel like an interrogation.
Keep it to 2 sentences max.
Do not use any emojis.""",

    "plan_checkin": """Generate a follow-up message checking on the user's health plan progress.
Ask how things are going with their goals, if they're facing any challenges.
Be supportive and curious. Keep it short - 2-3 sentences max.
Do not use any emojis.""",

    "user_requested": """Generate a reminder message based on the context provided.
The user asked to be reminded about something. Reference their original request naturally.
Keep it brief and friendly - 1-2 sentences.
Do not use any emojis.""",

    "daily_checkin": """Generate a brief daily check-in message.
Ask about one specific aspect of their health journey.
Keep it very short - 1 sentence with a question.
Do not use any emojis.""",

    "motivation": """Generate a brief motivational message based on what you know about the user.
Be genuine, not cheesy. Reference their specific goals if known.
Keep it to 1-2 sentences.
Do not use any emojis.""",
}


@celery_app.task(bind=True, max_retries=3)
def process_scheduled_reminders(self):
    """
    Process all scheduled reminders that are due.
    Runs every minute via Celery Beat.
    """
    db = SessionLocal()
    followup_service = get_followup_service()

    try:
        pending_followups = followup_service.get_pending_followups(db)
        logger.info(f"Processing {len(pending_followups)} pending follow-ups")

        for followup in pending_followups:
            try:
                # Send the follow-up
                send_followup_message.delay(str(followup.id))
            except Exception as e:
                logger.error(f"Error queuing followup {followup.id}: {e}")

    except Exception as e:
        logger.error(f"Error in process_scheduled_reminders: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def check_and_send_followups(self):
    """
    Check for users who need proactive follow-ups and schedule them.
    Runs hourly via Celery Beat.
    """
    db = SessionLocal()
    followup_service = get_followup_service()

    try:
        users_needing_followup = followup_service.get_users_needing_followup(db)
        logger.info(f"Found {len(users_needing_followup)} users needing follow-up")

        for user, engagement, reason in users_needing_followup:
            try:
                # Generate context for the follow-up
                context = followup_service.generate_followup_context(
                    user, engagement, reason, db
                )

                # Determine follow-up type
                followup_type = FollowUpType.INACTIVITY
                if reason == "plan_checkin":
                    followup_type = FollowUpType.PLAN_CHECKIN

                # Schedule immediate follow-up
                followup = followup_service.schedule_proactive_followup(
                    user_id=user.id,
                    followup_type=followup_type,
                    scheduled_time=datetime.utcnow(),
                    context=context,
                    db=db,
                )

                logger.info(f"Scheduled {reason} follow-up for user {user.id}")

            except Exception as e:
                logger.error(f"Error scheduling followup for user {user.id}: {e}")

    except Exception as e:
        logger.error(f"Error in check_and_send_followups: {e}")
        raise self.retry(exc=e, countdown=300)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def send_followup_message(self, followup_id: str):
    """
    Generate and send a single follow-up message.
    Includes profile context so Arohi can continue onboarding if incomplete.
    """
    db = SessionLocal()
    followup_service = get_followup_service()
    llm_service = get_llm_service()
    memory_service = get_memory_service()
    profile_service = get_profile_service()

    try:
        followup = db.query(ScheduledFollowUp).filter(
            ScheduledFollowUp.id == UUID(followup_id)
        ).first()

        if not followup:
            logger.error(f"Follow-up {followup_id} not found")
            return

        if followup.status != FollowUpStatus.PENDING.value:
            logger.info(f"Follow-up {followup_id} is not pending, skipping")
            return

        user = db.query(User).filter(User.id == followup.user_id).first()
        if not user:
            logger.error(f"User {followup.user_id} not found for followup {followup_id}")
            followup_service.mark_followup_failed(UUID(followup_id), db)
            return

        # Get user profile to check onboarding status
        profile = profile_service.get_or_create_profile(user.id, db)
        is_onboarding_incomplete = profile.onboarding_stage != OnboardingStage.COMPLETED.value

        # Choose appropriate prompt based on onboarding status
        followup_type = followup.followup_type
        if followup_type == FollowUpType.INACTIVITY.value and is_onboarding_incomplete:
            prompt = FOLLOWUP_PROMPTS["inactivity_onboarding"]
        else:
            prompt = FOLLOWUP_PROMPTS.get(followup_type, FOLLOWUP_PROMPTS["inactivity"])

        # Get user memories for context
        user_memories = memory_service.get_user_memories(user.id, db)
        if user.name:
            user_memories.insert(0, f"User's name is {user.name}")

        # Add profile context (what we know + what we still need to ask)
        profile_context = profile_service.get_profile_context_for_llm(user.id, db)
        if profile_context:
            user_memories.append(profile_context)

        # Build the message for LLM
        context_message = f"{prompt}\n\nContext about this user:\n{followup.context or 'No specific context'}"

        try:
            # Generate the follow-up message
            response = llm_service.generate_response(
                user_message=context_message,
                chat_history=[],
                user_memories=user_memories,
                relevant_protocols=None,
            )

            # Save the message to the database
            message = Message(
                user_id=user.id,
                role="assistant",
                content=response,
                status=MessageStatus.DELIVERED.value,
            )
            db.add(message)
            db.commit()
            db.refresh(message)

            # Mark follow-up as sent
            followup_service.mark_followup_sent(UUID(followup_id), db)
            followup_service.update_followup_sent(user.id, db)

            logger.info(f"Successfully sent follow-up {followup_id} to user {user.id}")

            # Note: Real-time WebSocket delivery is handled separately
            # The message is saved to DB and will be loaded when user reconnects
            # For real-time push, we'd need a separate notification service

        except Exception as e:
            logger.error(f"Error generating follow-up message: {e}")
            followup_service.mark_followup_failed(UUID(followup_id), db)
            raise

    except Exception as e:
        logger.error(f"Error in send_followup_message: {e}")
        raise self.retry(exc=e, countdown=120)
    finally:
        db.close()


@celery_app.task
def schedule_user_reminder(user_id: str, minutes_from_now: int, context: str):
    """
    Schedule a user-requested reminder.
    Called from the WebSocket handler when user requests a reminder.
    """
    db = SessionLocal()
    followup_service = get_followup_service()

    try:
        followup = followup_service.schedule_user_reminder(
            user_id=UUID(user_id),
            minutes_from_now=minutes_from_now,
            context=context,
            db=db,
        )
        logger.info(f"Scheduled reminder for user {user_id} in {minutes_from_now} minutes")
        return str(followup.id)

    except Exception as e:
        logger.error(f"Error scheduling user reminder: {e}")
        raise
    finally:
        db.close()
