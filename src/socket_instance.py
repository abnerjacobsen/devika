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
    """
    Envia uma mensagem via Socket.IO garantindo compatibilidade quando chamada
    de *threads* que não possuem um loop `asyncio` ativo.

    • Se houver loop de eventos em execução → agenda a coroutine com
      `asyncio.create_task()`.
    • Caso contrário (ex.: threads ‑ Agent executa em `threading.Thread`) →
      cria um loop temporário via `asyncio.run()`.
    """
    try:
        # ``python-socketio`` devolve uma *coroutine* em modo ASGI.
        coro = socketio.emit(channel, content)

        # Detecta loop em execução.
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sem loop → estamos provavelmente numa thread.
            asyncio.run(coro)
        else:
            # Loop existente → agenda normalmente.
            _loop.create_task(coro)

        if log:
            logger.info(f"SOCKET {channel} MESSAGE: {content}")
        return True

    except Exception as e:
        logger.error(f"SOCKET {channel} ERROR: {str(e)}")
        return False
