from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models.user import User
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageResponse, MessageListResponse, ChatResponse
from app.auth import get_current_user
from app.services.llm_service import get_llm_service
from app.services.protocol_service import get_protocol_service
from app.services.memory_service import get_memory_service

router = APIRouter()

# Default pagination limit
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
# Number of recent messages to include in LLM context
CONTEXT_MESSAGE_LIMIT = 20


@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    before: Optional[str] = Query(None, description="Cursor (message ID) to fetch messages before"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Number of messages to fetch"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get paginated chat messages for the current user (cursor-based pagination)."""
    query = db.query(Message).filter(Message.user_id == current_user.id)

    # If cursor provided, filter messages before that cursor
    if before:
        try:
            cursor_uuid = UUID(before)
            cursor_message = db.query(Message).filter(Message.id == cursor_uuid).first()
            if cursor_message:
                query = query.filter(Message.created_at < cursor_message.created_at)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor format",
            )

    # Order by created_at descending (newest first) and limit
    messages = query.order_by(desc(Message.created_at)).limit(limit + 1).all()

    # Check if there are more messages
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Reverse to get chronological order (oldest first in the batch)
    messages.reverse()

    # Get next cursor (oldest message in current batch)
    next_cursor = str(messages[0].id) if messages and has_more else None

    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.post("/messages", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message and get AI response."""
    # Save user message first
    user_message = Message(
        user_id=current_user.id,
        role="user",
        content=message_data.content,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # Get recent chat history for context
    recent_messages = (
        db.query(Message)
        .filter(Message.user_id == current_user.id)
        .filter(Message.id != user_message.id)  # Exclude the message we just saved
        .order_by(desc(Message.created_at))
        .limit(CONTEXT_MESSAGE_LIMIT)
        .all()
    )
    # Reverse to get chronological order
    recent_messages.reverse()

    # Format chat history for LLM
    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in recent_messages
    ]

    # Get user memories for context
    memory_service = get_memory_service()
    user_memories = memory_service.get_user_memories(current_user.id, db)

    # Find relevant protocols based on user message
    protocol_service = get_protocol_service()
    relevant_protocols = protocol_service.find_relevant_protocols(
        message_data.content, db
    )

    # Generate AI response using Vertex AI
    llm_service = get_llm_service()
    ai_response_content = llm_service.generate_response(
        user_message=message_data.content,
        chat_history=chat_history,
        user_memories=user_memories if user_memories else None,
        relevant_protocols=relevant_protocols if relevant_protocols else None,
    )

    # Save AI response
    assistant_message = Message(
        user_id=current_user.id,
        role="assistant",
        content=ai_response_content,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # Extract and store any new memories from the conversation
    memory_service.extract_and_store_memories(
        user_id=current_user.id,
        user_message=message_data.content,
        assistant_response=ai_response_content,
        db=db,
    )

    return ChatResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )
