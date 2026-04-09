from typing import Dict, Optional
from fastapi import WebSocket
from loguru import logger
import asyncio


class PlivoWebSocketManager:
    """Manages active Plivo WebSocket connections for warm transfer."""
    
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}
        self._connections_by_call: Dict[str, WebSocket] = {}
        self._pipeline_tasks: Dict[str, asyncio.Task] = {}  # Track pipeline tasks by session_id
    
    def add_connection(self, session_id: str, websocket: WebSocket, call_uuid: str = None):
        """Store WebSocket connection by session_id and optionally by call_uuid."""
        self._connections[session_id] = websocket
        if call_uuid:
            self._connections_by_call[call_uuid] = websocket
        logger.debug(f"Added WebSocket connection for session {session_id}, call {call_uuid}")
    
    def remove_connection(self, session_id: str):
        """Remove WebSocket connection."""
        self._connections.pop(session_id, None)
        # Also remove from call-based tracking
        call_uuid_to_remove = None
        for call_uuid, ws in self._connections_by_call.items():
            if ws == self._connections.get(session_id):
                call_uuid_to_remove = call_uuid
                break
        if call_uuid_to_remove:
            self._connections_by_call.pop(call_uuid_to_remove, None)
        # Remove pipeline task tracking
        self._pipeline_tasks.pop(session_id, None)
        logger.debug(f"Removed WebSocket connection for session {session_id}")
    
    def get_connection(self, session_id: str) -> WebSocket | None:
        """Get WebSocket connection by session_id."""
        return self._connections.get(session_id)
    
    def get_connection_by_call(self, call_uuid: str) -> WebSocket | None:
        """Get WebSocket connection by call_uuid."""
        return self._connections_by_call.get(call_uuid)
    
    def set_pipeline_task(self, session_id: str, task: asyncio.Task):
        """Store pipeline task for a session."""
        self._pipeline_tasks[session_id] = task
        logger.debug(f"Stored pipeline task for session {session_id}")
    
    def get_pipeline_task(self, session_id: str) -> Optional[asyncio.Task]:
        """Get pipeline task for a session."""
        return self._pipeline_tasks.get(session_id)
    
    async def cancel_pipeline_task(self, session_id: str):
        """Cancel pipeline task for a session."""
        task = self._pipeline_tasks.get(session_id)
        if task and not task.done():
            logger.info(f"🛑 Cancelling pipeline task for session {session_id}")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"✅ Pipeline task cancelled for session {session_id}")
            except Exception as e:
                logger.error(f"Error cancelling pipeline task: {e}")
            finally:
                self._pipeline_tasks.pop(session_id, None)
        else:
            logger.debug(f"No active pipeline task to cancel for session {session_id}")
    
    async def close_connection(self, session_id: str):
        """Close WebSocket connection for warm transfer."""
        websocket = self._connections.get(session_id)
        if websocket:
            try:
                await websocket.close(code=1000)  # Normal closure
                logger.info(f"✅ Closed WebSocket for session {session_id} for warm transfer")
                self.remove_connection(session_id)
            except Exception as e:
                logger.error(f"Error closing WebSocket for session {session_id}: {e}")
        else:
            logger.warning(f"⚠️ No active WebSocket found for session {session_id}")


# Create singleton instance
plivo_websocket_manager = PlivoWebSocketManager()
