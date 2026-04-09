import asyncio

from loguru import logger
from pipecat.transports.smallwebrtc.transport import SmallWebRTCConnection


class WebRTCManager:
    def __init__(self):
        self._connections: dict[str, SmallWebRTCConnection] = {}

    async def get_connection(self, pc_id: str | None = None) -> SmallWebRTCConnection:
        if pc_id and pc_id in self._connections:
            logger.info(f"Reusing existing connection for pc_id: {pc_id}")
            return self._connections[pc_id]

        connection = SmallWebRTCConnection()

        @connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            logger.info(f"Discarding peer connection for pc_id: {webrtc_connection.pc_id}")
            self._connections.pop(webrtc_connection.pc_id, None)

        return connection

    def add_connection(self, connection: SmallWebRTCConnection):
        self._connections[connection.pc_id] = connection

    async def disconnect_all(self):
        coros = [pc.disconnect() for pc in self._connections.values()]
        await asyncio.gather(*coros)
        self._connections.clear()


# Create a singleton instance of the WebRTCManager
webrtc_manager = WebRTCManager()
