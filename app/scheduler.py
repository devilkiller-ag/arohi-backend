"""Background scheduler for follow-up tasks (replaces Celery for free tier)."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()


def process_scheduled_reminders_job():
    """Process pending follow-up messages."""
    from app.database import SessionLocal
    from app.services.followup_service import get_followup_service
    from app.services.llm_service import get_llm_service
    from app.services.memory_service import get_memory_service
    from app.services.profile_service import get_profile_service
    from app.models.message import Message, MessageStatus

    db = SessionLocal()
    try:
        followup_service = get_followup_service()
        pending = followup_service.get_pending_followups(db)

        for followup in pending:
            try:
                user = followup.user
                if not user:
                    continue

                # Generate follow-up message
                llm_service = get_llm_service()
                memory_service = get_memory_service()
                profile_service = get_profile_service()

                memories = memory_service.get_user_memories(user.id, db)
                profile_context = profile_service.get_profile_context_for_llm(user.id, db)
                if profile_context:
                    memories.append(profile_context)

                context = followup.context or "Check in with the user"
                prompt = f"Send a follow-up message. Context: {context}"

                response = llm_service.generate_response(
                    user_message=prompt,
                    user_memories=memories if memories else None,
                )

                # Save message
                message = Message(
                    user_id=user.id,
                    role="assistant",
                    content=response,
                    status=MessageStatus.DELIVERED.value,
                )
                db.add(message)
                followup_service.mark_followup_sent(followup.id, db)
                db.commit()
                print(f"Sent follow-up to user {user.id}")

            except Exception as e:
                print(f"Error processing follow-up {followup.id}: {e}")
                followup_service.mark_followup_failed(followup.id, db)

    finally:
        db.close()


def check_and_send_followups_job():
    """Check for users needing proactive follow-ups."""
    from app.database import SessionLocal
    from app.services.followup_service import get_followup_service

    db = SessionLocal()
    try:
        followup_service = get_followup_service()
        users = followup_service.get_users_needing_followup(db)

        for user_id, reason in users:
            try:
                context = followup_service.generate_followup_context(user_id, reason, db)
                followup_service.schedule_proactive_followup(
                    user_id=user_id,
                    followup_type=reason,
                    context=context,
                    db=db,
                )
                print(f"Scheduled follow-up for user {user_id}: {reason}")
            except Exception as e:
                print(f"Error scheduling follow-up for {user_id}: {e}")

    finally:
        db.close()


def start_scheduler():
    """Start the background scheduler."""
    # Process reminders every minute
    scheduler.add_job(
        process_scheduled_reminders_job,
        CronTrigger(minute="*"),
        id="process_reminders",
        replace_existing=True,
    )

    # Check for follow-ups every hour
    scheduler.add_job(
        check_and_send_followups_job,
        CronTrigger(minute=0),
        id="check_followups",
        replace_existing=True,
    )

    scheduler.start()
    print("Background scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        print("Background scheduler stopped")
