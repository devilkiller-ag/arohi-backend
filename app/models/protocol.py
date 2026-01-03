import uuid

from sqlalchemy import Column, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.database import Base


class Protocol(Base):
    """Medical protocol model for health guidelines."""

    __tablename__ = "protocols"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    keywords = Column(ARRAY(String), nullable=False)  # Keywords for matching
    content = Column(Text, nullable=False)  # The protocol guidelines
    priority = Column(Integer, default=0)  # Higher priority = more important

    def __repr__(self):
        return f"<Protocol {self.name}>"
