"""WebSocket endpoint for real-time chat."""

import asyncio
import random
from uuid import UUID
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from jose import JWTError, jwt

from app.database import get_db, SessionLocal
from app.config import get_settings
from app.models.user import User
from app.models.message import Message, MessageStatus
from app.schemas.message import WSMessageType, MessageResponse
from app.services.connection_manager import get_connection_manager
from app.services.llm_service import get_llm_service
from app.services.protocol_service import get_protocol_service
from app.services.memory_service import get_memory_service
from app.services.onboarding_service import get_onboarding_service
from app.services.followup_service import get_followup_service
from app.services.profile_service import get_profile_service

router = APIRouter()
settings = get_settings()

# Constants
CONTEXT_MESSAGE_LIMIT = 20


def get_user_from_token_sync(token: str, db: Session) -> Optional[User]:
    """Validate JWT token and return user."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        return user
    except JWTError:
        return None


def calculate_typing_delay(response_length: int) -> float:
    """
    Calculate realistic typing delay based on response length.
    Simulates human typing speed with some randomness.
    """
    base_delay = response_length / 400 * 60
    randomness = random.uniform(0.8, 1.2)
    delay = max(1.5, min(5.0, base_delay * randomness))
    return delay


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time chat.
    Uses fresh database sessions for each operation to avoid connection timeouts.
    """
    connection_manager = get_connection_manager()
    user_id = None

    # Authenticate user with fresh session
    db = SessionLocal()
    try:
        user = get_user_from_token_sync(token, db)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
        user_id = user.id
    finally:
        db.close()

    # Accept connection
    await connection_manager.connect(websocket, user_id)

    try:
        # Check if user needs onboarding (fresh session)
        db = SessionLocal()
        try:
            onboarding_service = get_onboarding_service()
            user = db.query(User).filter(User.id == user_id).first()
            if user and onboarding_service.check_needs_onboarding(user_id, db):
                onboarding_msg = onboarding_service.create_onboarding_message(user, db)
                if onboarding_msg:
                    await asyncio.sleep(1.0)
                    await connection_manager.send_message(
                        user_id,
                        WSMessageType.ONBOARDING,
                        {
                            "message": {
                                "id": str(onboarding_msg.id),
                                "role": onboarding_msg.role,
                                "content": onboarding_msg.content,
                                "status": onboarding_msg.status,
                                "created_at": onboarding_msg.created_at.isoformat() + "Z",
                            }
                        }
                    )
        finally:
            db.close()

        # Listen for messages
        while True:
            try:
                data = await websocket.receive_json()

                if data.get("type") == WSMessageType.USER_MESSAGE.value:
                    content = data.get("data", {}).get("content", "")
                    await handle_user_message(
                        user_id=user_id,
                        content=content,
                        connection_manager=connection_manager,
                    )

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"Error processing message: {e}")
                await connection_manager.send_message(
                    user_id,
                    WSMessageType.ERROR,
                    {"message": "Something went wrong. Let me try that again..."}
                )

    finally:
        connection_manager.disconnect(user_id)


async def handle_user_message(
    user_id: UUID,
    content: str,
    connection_manager,
):
    """Handle incoming user message with WhatsApp-like flow."""
    if not content or not content.strip():
        return

    content = content.strip()

    # Create fresh database session for this message
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return

        followup_service = get_followup_service()

        # Update user activity tracking
        followup_service.update_user_activity(user.id, db)

        # Step 1: Save user message with 'sent' status
        user_message = Message(
            user_id=user.id,
            role="user",
            content=content,
            status=MessageStatus.SENT.value,
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        # Step 2: Send 'message_sent' (single tick)
        await connection_manager.send_message(
            user.id,
            WSMessageType.MESSAGE_SENT,
            {
                "message_id": str(user_message.id),
                "status": "sent",
            }
        )

        # Step 3: Small delay, then 'message_delivered' (double tick)
        await asyncio.sleep(random.uniform(0.3, 0.6))
        user_message.status = MessageStatus.DELIVERED.value
        db.commit()

        await connection_manager.send_message(
            user.id,
            WSMessageType.MESSAGE_DELIVERED,
            {
                "message_id": str(user_message.id),
                "status": "delivered",
            }
        )

        # Step 4: Delay before typing (human-like pause to read message)
        await asyncio.sleep(random.uniform(0.8, 1.5))

        # Step 5: Send 'typing_start'
        await connection_manager.send_message(
            user.id,
            WSMessageType.TYPING_START,
            {}
        )

        # Step 6: Generate AI response with scheduling detection
        try:
            structured_response = await generate_ai_response(user, content, db)
            ai_response = structured_response["message"]

            # Step 7: Handle scheduling intent detected by LLM
            if structured_response.get("scheduling") and structured_response["scheduling"].get("requested"):
                try:
                    from app.tasks.followup_tasks import schedule_user_reminder
                    minutes = structured_response["scheduling"]["minutes_from_now"]
                    reason = structured_response["scheduling"].get("reason", f"User asked: {content}")
                    schedule_user_reminder.delay(str(user.id), minutes, reason)
                    print(f"Scheduled reminder for user {user.id} in {minutes} minutes: {reason}")
                except Exception as e:
                    print(f"Error scheduling reminder: {e}")

            # Step 8: Calculate typing delay based on response length
            typing_delay = calculate_typing_delay(len(ai_response))
            await asyncio.sleep(typing_delay)

            # Step 9: Save assistant message
            assistant_message = Message(
                user_id=user.id,
                role="assistant",
                content=ai_response,
                status=MessageStatus.DELIVERED.value,
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # Step 10: Send assistant message
            await connection_manager.send_message(
                user.id,
                WSMessageType.ASSISTANT_MESSAGE,
                {
                    "message": {
                        "id": str(assistant_message.id),
                        "role": assistant_message.role,
                        "content": assistant_message.content,
                        "status": assistant_message.status,
                        "created_at": assistant_message.created_at.isoformat() + "Z",
                    }
                }
            )

            # Step 11: Extract memories from conversation (background)
            memory_service = get_memory_service()
            memory_service.extract_and_store_memories(
                user_id=user.id,
                user_message=content,
                assistant_response=ai_response,
                db=db,
            )

            # Step 12: Extract profile data from conversation (onboarding)
            profile_service = get_profile_service()
            profile = profile_service.get_or_create_profile(user.id, db)
            profile_service.extract_profile_data(
                user_message=content,
                assistant_response=ai_response,
                profile=profile,
                db=db,
            )

        except Exception as e:
            print(f"Error generating response: {e}")
            # Send a human-like error message instead of technical error
            error_message = Message(
                user_id=user.id,
                role="assistant",
                content="Sorry, got a bit distracted there. Could you say that again?",
                status=MessageStatus.DELIVERED.value,
            )
            db.add(error_message)
            db.commit()
            db.refresh(error_message)

            await connection_manager.send_message(
                user.id,
                WSMessageType.ASSISTANT_MESSAGE,
                {
                    "message": {
                        "id": str(error_message.id),
                        "role": error_message.role,
                        "content": error_message.content,
                        "status": error_message.status,
                        "created_at": error_message.created_at.isoformat() + "Z",
                    }
                }
            )

    finally:
        db.close()


async def generate_ai_response(
    user: User,
    content: str,
    db: Session,
) -> dict:
    """Generate AI response with context. Returns structured response with scheduling intent."""
    from app.services.llm_service import StructuredResponse

    # Get recent chat history
    recent_messages = (
        db.query(Message)
        .filter(Message.user_id == user.id)
        .order_by(desc(Message.created_at))
        .limit(CONTEXT_MESSAGE_LIMIT)
        .all()
    )
    recent_messages.reverse()

    # Format chat history
    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages
        if msg.content != content  # Exclude current message
    ]

    # Get user memories
    memory_service = get_memory_service()
    user_memories = memory_service.get_user_memories(user.id, db)

    # Add user name to memories if not already there
    if user.name and f"User's name is {user.name}" not in user_memories:
        user_memories.insert(0, f"User's name is {user.name}")

    # Add user profile context (onboarding data)
    profile_service = get_profile_service()
    profile_context = profile_service.get_profile_context_for_llm(user.id, db)
    if profile_context:
        user_memories.append(profile_context)

    # Get relevant protocols
    protocol_service = get_protocol_service()
    relevant_protocols = protocol_service.find_relevant_protocols(content, db)

    # Generate structured response with scheduling detection
    llm_service = get_llm_service()
    response = llm_service.generate_structured_response(
        user_message=content,
        chat_history=chat_history,
        user_memories=user_memories if user_memories else None,
        relevant_protocols=relevant_protocols if relevant_protocols else None,
    )

    return response
