from typing import Optional
from sqlalchemy.orm import Session

from app.models.protocol import Protocol


class ProtocolService:
    """Service for matching user queries to medical protocols."""

    def find_relevant_protocols(
        self,
        user_message: str,
        db: Session,
        max_results: int = 3,
    ) -> list[str]:
        """
        Find protocols relevant to the user's message based on keyword matching.

        Args:
            user_message: The user's current message
            db: Database session
            max_results: Maximum number of protocols to return

        Returns:
            List of protocol content strings
        """
        message_lower = user_message.lower()

        # Get all protocols
        protocols = db.query(Protocol).all()

        # Score each protocol based on keyword matches
        scored_protocols: list[tuple[Protocol, int]] = []

        for protocol in protocols:
            score = 0
            for keyword in protocol.keywords:
                if keyword.lower() in message_lower:
                    score += 1

            if score > 0:
                # Add priority to score for tie-breaking
                total_score = score * 10 + protocol.priority
                scored_protocols.append((protocol, total_score))

        # Sort by score (descending) and take top results
        scored_protocols.sort(key=lambda x: x[1], reverse=True)
        top_protocols = scored_protocols[:max_results]

        # Return protocol content
        return [p.content for p, _ in top_protocols]


# Singleton instance
protocol_service = ProtocolService()


def get_protocol_service() -> ProtocolService:
    """Get the protocol service instance."""
    return protocol_service
