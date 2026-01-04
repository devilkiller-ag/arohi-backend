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

router = APIRouter()

# Default pagination limit
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


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
    # Save user message
    user_message = Message(
        user_id=current_user.id,
        role="user",
        content=message_data.content,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # TODO: Generate AI response using Vertex AI
    # For now, return a placeholder response
    ai_response_content = f"Thank you for your message. I'm Arohi, your AI health coach. This is a placeholder response - Vertex AI integration coming soon!"

    # Save AI response
    assistant_message = Message(
        user_id=current_user.id,
        role="assistant",
        content=ai_response_content,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )
