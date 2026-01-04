from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str


class UserResponse(UserBase):
    """Schema for user response (public info)."""
    id: UUID
    name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserInDB(UserResponse):
    """Schema for user with password hash (internal use)."""
    password_hash: str
