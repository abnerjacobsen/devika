from functools import wraps

from fastlogging import LogInit
from src.config import Config

# Typing / runtime imports for FastAPI
from typing import Any
from fastapi import Request
from starlette.responses import Response as StarletteResponse


class Logger:
    def __init__(self, filename="devika_agent.log"):
        config = Config()
        logs_dir = config.get_logs_dir()
        self.logger = LogInit(pathName=logs_dir + "/" + filename, console=True, colors=True, encoding="utf-8")

    def read_log_file(self) -> str:
        with open(self.logger.pathName, "r") as file:
            return file.read()

    def info(self, message: str):
        self.logger.info(message)
        self.logger.flush()

    def error(self, message: str):
        self.logger.error(message)
        self.logger.flush()

    def warning(self, message: str):
        self.logger.warning(message)
        self.logger.flush()

    def debug(self, message: str):
        self.logger.debug(message)
        self.logger.flush()

    def exception(self, message: str):
        self.logger.exception(message)
        self.logger.flush()


def route_logger(logger: Logger):
    """
    Decorator factory that creates a decorator to log route entry and exit points.
    The decorator uses the provided logger to log the information.

    :param logger: The logger instance to use for logging.
    """

    log_enabled = Config().get_logging_rest_api()

    def decorator(func):

        import asyncio

        def _extract_request(*a, **kw) -> "Request | None":
            """
            Try to obtain a FastAPI Request object from positional/keyword args.
            """
            if "request" in kw and isinstance(kw["request"], Request):
                return kw["request"]  # type: ignore[return-value]
            for val in a:
                if isinstance(val, Request):
                    return val  # type: ignore[return-value]
            return None

        def _log_entry_exit(
            req: "Request | None",
            resp: Any,
            err: Exception | None = None,
        ) -> None:
            if not log_enabled:
                return

            path = req.url.path if req else "NO_PATH"
            method = req.method if req else "NO_METHOD"

            if err is None:
                # normal exit
                try:
                    if isinstance(resp, StarletteResponse):
                        body: str
                        try:
                            # May be bytes / str / memoryview
                            raw = resp.body
                            body = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
                        except Exception:
                            body = "Streaming/File response"
                    else:
                        body = str(resp)

                    if "settings" in path:
                        body = "*** Settings are not logged ***"

                    logger.debug(f"{path} {method} - Response: {body}")
                except Exception as e:  # pragma: no cover
                    logger.exception(f"{path} {method} - Logging response failed: {e}")
            else:
                logger.exception(f"{path} {method} - {err}")

        # ------------------------------------------------------------------ #
        # Select wrapper type (sync / async) depending on decorated function #
        # ------------------------------------------------------------------ #

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                request_obj = _extract_request(*args, **kwargs)

                # Entry log
                if log_enabled and request_obj:
                    logger.info(f"{request_obj.url.path} {request_obj.method}")

                try:
                    response = await func(*args, **kwargs)
                    _log_entry_exit(request_obj, response)
                    return response
                except Exception as e:  # pragma: no cover
                    _log_entry_exit(request_obj, None, err=e)
                    raise

            return async_wrapper

        # ---- synchronous route ------------------------------------------- #

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Extract FastAPI Request object if available
            request_obj = _extract_request(*args, **kwargs)

            if log_enabled and request_obj:
                logger.info(f"{request_obj.url.path} {request_obj.method}")

            try:
                response = func(*args, **kwargs)
                _log_entry_exit(request_obj, response)
                return response
            except Exception as e:  # pragma: no cover
                _log_entry_exit(request_obj, None, err=e)
                raise

        return sync_wrapper
    return decorator
