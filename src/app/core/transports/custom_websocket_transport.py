from loguru import logger
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport
from starlette.websockets import WebSocketDisconnect


class CustomFastAPIWebsocketTransport(FastAPIWebsocketTransport):
    """
    A custom transport that gracefully handles WebSocketDisconnect exceptions
    to prevent unnecessary error logging when a client disconnects.
    """

    async def send(self, data: bytes):
        try:
            await super().send(data)
        except WebSocketDisconnect:
            # This is expected when the client disconnects, so we log it
            # as a debug message instead of an error.
            logger.debug("WebSocket client disconnected. Unable to send data.")
        except Exception as e:
            # Re-raise other exceptions to ensure we don't hide real problems.
            logger.error(f"An unexpected error occurred while sending data: {e}")
            raise
