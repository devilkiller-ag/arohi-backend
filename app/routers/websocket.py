"""WebSocket endpoint for real-time chat."""

import asyncio
import random
from uuid import UUID
from typing import Optional

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

router = APIRouter()
settings = get_settings()

# Constants
CONTEXT_MESSAGE_LIMIT = 20


async def get_user_from_token(token: str, db: Session) -> Optional[User]:
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
    # Average typing speed: ~40 words per minute = ~200 chars per minute
    # But we want it faster for UX, so ~400 chars per minute
    base_delay = len(response_length) / 400 * 60 if isinstance(response_length, str) else response_length / 400 * 60

    # Add some randomness (±20%)
    randomness = random.uniform(0.8, 1.2)

    # Minimum 1.5 seconds, maximum 5 seconds
    delay = max(1.5, min(5.0, base_delay * randomness))

    return delay


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time chat.

    Connection: ws://localhost:8000/api/ws/chat?token=<jwt_token>

    Message Flow:
    1. Client sends: {"type": "user_message", "data": {"content": "Hello"}}
    2. Server sends: {"type": "message_sent", "data": {"message_id": "...", "status": "sent"}}
    3. Server sends: {"type": "message_delivered", "data": {"message_id": "...", "status": "delivered"}}
    4. Server sends: {"type": "typing_start", "data": {}}
    5. [After delay] Server sends: {"type": "assistant_message", "data": {"message": {...}}}
    """
    # Get database session
    db = SessionLocal()
    connection_manager = get_connection_manager()

    try:
        # Authenticate user
        user = await get_user_from_token(token, db)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return

        # Accept connection
        await connection_manager.connect(websocket, user.id)

        # Check if user needs onboarding
        onboarding_service = get_onboarding_service()
        if onboarding_service.check_needs_onboarding(user.id, db):
            # Create and send onboarding message
            onboarding_msg = onboarding_service.create_onboarding_message(user, db)
            if onboarding_msg:
                # Small delay before sending onboarding
                await asyncio.sleep(1.0)
                await connection_manager.send_message(
                    user.id,
                    WSMessageType.ONBOARDING,
                    {
                        "message": {
                            "id": str(onboarding_msg.id),
                            "role": onboarding_msg.role,
                            "content": onboarding_msg.content,
                            "status": onboarding_msg.status,
                            "created_at": onboarding_msg.created_at.isoformat(),
                        }
                    }
                )

        # Listen for messages
        while True:
            try:
                data = await websocket.receive_json()

                if data.get("type") == WSMessageType.USER_MESSAGE.value:
                    await handle_user_message(
                        user=user,
                        content=data.get("data", {}).get("content", ""),
                        db=db,
                        connection_manager=connection_manager,
                    )

            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"Error processing message: {e}")
                await connection_manager.send_message(
                    user.id,
                    WSMessageType.ERROR,
                    {"message": "Something went wrong. Let me try that again..."}
                )

    finally:
        connection_manager.disconnect(user.id)
        db.close()


async def handle_user_message(
    user: User,
    content: str,
    db: Session,
    connection_manager,
):
    """Handle incoming user message with WhatsApp-like flow."""
    if not content or not content.strip():
        return

    content = content.strip()

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

    # Step 6: Generate AI response
    try:
        ai_response = await generate_ai_response(user, content, db)

        # Step 7: Calculate typing delay based on response length
        typing_delay = calculate_typing_delay(len(ai_response))
        await asyncio.sleep(typing_delay)

        # Step 8: Save assistant message
        assistant_message = Message(
            user_id=user.id,
            role="assistant",
            content=ai_response,
            status=MessageStatus.DELIVERED.value,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        # Step 9: Send assistant message
        await connection_manager.send_message(
            user.id,
            WSMessageType.ASSISTANT_MESSAGE,
            {
                "message": {
                    "id": str(assistant_message.id),
                    "role": assistant_message.role,
                    "content": assistant_message.content,
                    "status": assistant_message.status,
                    "created_at": assistant_message.created_at.isoformat(),
                }
            }
        )

        # Step 10: Extract memories from conversation (background)
        memory_service = get_memory_service()
        memory_service.extract_and_store_memories(
            user_id=user.id,
            user_message=content,
            assistant_response=ai_response,
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
                    "created_at": error_message.created_at.isoformat(),
                }
            }
        )


async def generate_ai_response(user: User, content: str, db: Session) -> str:
    """Generate AI response with context."""
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

    # Get relevant protocols
    protocol_service = get_protocol_service()
    relevant_protocols = protocol_service.find_relevant_protocols(content, db)

    # Generate response
    llm_service = get_llm_service()
    response = llm_service.generate_response(
        user_message=content,
        chat_history=chat_history,
        user_memories=user_memories if user_memories else None,
        relevant_protocols=relevant_protocols if relevant_protocols else None,
    )

    return response
