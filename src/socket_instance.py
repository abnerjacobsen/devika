# socketio_instance.py
"""
Socket.IO helper module.

Migrated from ``Flask-SocketIO`` to ``python-socketio`` so it can be mounted
directly on a FastAPI (ASGI) application.  The public symbol ``socketio`` is
kept to avoid changes in the rest of the code base.
"""
import asyncio
import socketio as _socketio  # python-socketio

from src.logger import Logger

# AsyncServer instance – will be mounted on FastAPI as an ASGI app elsewhere.
socketio = _socketio.AsyncServer(
    async_mode="asgi",  # required for FastAPI/ASGI apps
    cors_allowed_origins="*",
)

# Logger instance for socket events
logger = Logger()


def emit_agent(channel, content, log=True):
    try:
        # ``python-socketio`` `emit` is a coroutine under AsyncServer.
        coro = socketio.emit(channel, content)
        if asyncio.iscoroutine(coro):
            # Schedule the coroutine to run in the background; no await needed.
            asyncio.create_task(coro)
        # else: sync path (unlikely with AsyncServer)
        if log:
            logger.info(f"SOCKET {channel} MESSAGE: {content}")
        return True
    except Exception as e:
        logger.error(f"SOCKET {channel} ERROR: {str(e)}")
        return False
