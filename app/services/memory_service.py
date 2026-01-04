from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.memory import Memory


# Categories for organizing memories
MEMORY_CATEGORIES = ["health", "preference", "personal", "lifestyle"]


class MemoryService:
    """Service for managing long-term user memories."""

    def get_user_memories(
        self,
        user_id: UUID,
        db: Session,
        limit: int = 20,
    ) -> list[str]:
        """
        Get all memories for a user.

        Args:
            user_id: The user's ID
            db: Database session
            limit: Maximum memories to retrieve

        Returns:
            List of memory content strings
        """
        memories = (
            db.query(Memory)
            .filter(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .all()
        )

        return [m.content for m in memories]

    def add_memory(
        self,
        user_id: UUID,
        content: str,
        db: Session,
        category: Optional[str] = None,
    ) -> Memory:
        """
        Add a new memory for a user.

        Args:
            user_id: The user's ID
            content: The memory content (fact about user)
            db: Database session
            category: Optional category for the memory

        Returns:
            The created Memory object
        """
        # Validate category
        if category and category not in MEMORY_CATEGORIES:
            category = None

        memory = Memory(
            user_id=user_id,
            content=content,
            category=category,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)

        return memory

    def extract_and_store_memories(
        self,
        user_id: UUID,
        user_message: str,
        assistant_response: str,
        db: Session,
    ) -> list[Memory]:
        """
        Extract facts from conversation and store as memories.
        Uses simple keyword-based extraction for MVP.

        Args:
            user_id: The user's ID
            user_message: The user's message
            assistant_response: The AI's response
            db: Database session

        Returns:
            List of created Memory objects
        """
        memories_created = []
        message_lower = user_message.lower()

        # Simple pattern matching for common health-related facts
        # Format: (keywords, extraction_pattern, category)
        patterns = [
            # Age patterns
            (["i am", "years old", "i'm"], self._extract_age, "personal"),
            # Health conditions
            (["i have", "diagnosed with", "suffering from"], self._extract_condition, "health"),
            # Allergies
            (["allergic to", "allergy"], self._extract_allergy, "health"),
            # Medications
            (["taking", "medication", "medicine", "prescribed"], self._extract_medication, "health"),
            # Lifestyle
            (["vegetarian", "vegan", "non-veg"], self._extract_diet, "lifestyle"),
            # Exercise
            (["exercise", "workout", "gym", "yoga", "running"], self._extract_exercise, "lifestyle"),
            # Sleep
            (["sleep", "insomnia", "hours of sleep"], self._extract_sleep, "lifestyle"),
        ]

        for keywords, extractor, category in patterns:
            if any(kw in message_lower for kw in keywords):
                extracted = extractor(user_message)
                if extracted:
                    # Check if similar memory exists
                    existing = (
                        db.query(Memory)
                        .filter(Memory.user_id == user_id)
                        .filter(Memory.content.ilike(f"%{extracted[:30]}%"))
                        .first()
                    )

                    if not existing:
                        memory = self.add_memory(user_id, extracted, db, category)
                        memories_created.append(memory)

        return memories_created

    def _extract_age(self, message: str) -> Optional[str]:
        """Extract age-related information."""
        import re
        # Match patterns like "I am 25 years old" or "I'm 30"
        match = re.search(r"i['\s]?(?:am|m)\s+(\d+)\s*(?:years?\s*old)?", message, re.IGNORECASE)
        if match:
            return f"User is {match.group(1)} years old"
        return None

    def _extract_condition(self, message: str) -> Optional[str]:
        """Extract health condition mentions."""
        import re
        # Match patterns like "I have diabetes" or "diagnosed with hypertension"
        patterns = [
            r"i\s+have\s+([a-zA-Z\s]+?)(?:\.|,|$|\s+and)",
            r"diagnosed\s+with\s+([a-zA-Z\s]+?)(?:\.|,|$|\s+and)",
            r"suffering\s+from\s+([a-zA-Z\s]+?)(?:\.|,|$|\s+and)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                condition = match.group(1).strip()
                if len(condition) > 2 and len(condition) < 50:
                    return f"User has {condition}"
        return None

    def _extract_allergy(self, message: str) -> Optional[str]:
        """Extract allergy information."""
        import re
        match = re.search(r"allergic\s+to\s+([a-zA-Z\s,]+?)(?:\.|$)", message, re.IGNORECASE)
        if match:
            return f"User is allergic to {match.group(1).strip()}"
        return None

    def _extract_medication(self, message: str) -> Optional[str]:
        """Extract medication information."""
        import re
        patterns = [
            r"taking\s+([a-zA-Z\s]+?)(?:\s+for|\.|,|$)",
            r"prescribed\s+([a-zA-Z\s]+?)(?:\.|,|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                med = match.group(1).strip()
                if len(med) > 2 and len(med) < 50:
                    return f"User is taking {med}"
        return None

    def _extract_diet(self, message: str) -> Optional[str]:
        """Extract diet preference."""
        message_lower = message.lower()
        if "vegetarian" in message_lower:
            return "User follows a vegetarian diet"
        if "vegan" in message_lower:
            return "User follows a vegan diet"
        if "non-veg" in message_lower or "non veg" in message_lower:
            return "User eats non-vegetarian food"
        return None

    def _extract_exercise(self, message: str) -> Optional[str]:
        """Extract exercise habits."""
        message_lower = message.lower()
        if "don't exercise" in message_lower or "no exercise" in message_lower:
            return "User does not exercise regularly"
        if "gym" in message_lower:
            return "User goes to the gym"
        if "yoga" in message_lower:
            return "User practices yoga"
        if "running" in message_lower or "jog" in message_lower:
            return "User runs/jogs regularly"
        return None

    def _extract_sleep(self, message: str) -> Optional[str]:
        """Extract sleep patterns."""
        import re
        match = re.search(r"(\d+)\s*hours?\s*(?:of\s*)?sleep", message, re.IGNORECASE)
        if match:
            return f"User sleeps about {match.group(1)} hours"
        if "insomnia" in message.lower():
            return "User has trouble sleeping (insomnia)"
        return None


# Singleton instance
memory_service = MemoryService()


def get_memory_service() -> MemoryService:
    """Get the memory service instance."""
    return memory_service
