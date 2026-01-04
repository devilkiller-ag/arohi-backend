"""WebSocket connection manager for real-time chat."""

import json
import asyncio
from typing import Dict
from uuid import UUID
from fastapi import WebSocket

from app.schemas.message import WSMessageType


class ConnectionManager:
    """Manages WebSocket connections for all users."""

    def __init__(self):
        # Map user_id to their WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: UUID):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[str(user_id)] = websocket

    def disconnect(self, user_id: UUID):
        """Remove a WebSocket connection."""
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            del self.active_connections[user_id_str]

    async def send_message(self, user_id: UUID, message_type: WSMessageType, data: dict):
        """Send a message to a specific user."""
        user_id_str = str(user_id)
        if user_id_str in self.active_connections:
            websocket = self.active_connections[user_id_str]
            try:
                await websocket.send_json({
                    "type": message_type.value,
                    "data": data
                })
            except Exception as e:
                print(f"Error sending message to {user_id}: {e}")
                self.disconnect(user_id)

    async def send_with_delay(self, user_id: UUID, message_type: WSMessageType, data: dict, delay_seconds: float):
        """Send a message after a delay (for human-like timing)."""
        await asyncio.sleep(delay_seconds)
        await self.send_message(user_id, message_type, data)

    def is_connected(self, user_id: UUID) -> bool:
        """Check if a user is connected."""
        return str(user_id) in self.active_connections


# Singleton instance
connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the connection manager instance."""
    return connection_manager
