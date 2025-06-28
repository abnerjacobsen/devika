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

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract FastAPI Request object if available
            request_obj: Request | None = None
            for value in list(args) + list(kwargs.values()):
                if isinstance(value, Request):
                    request_obj = value  # type: ignore[assignment]
                    break

            path = request_obj.url.path if request_obj else "UNKNOWN_PATH"
            method = request_obj.method if request_obj else "UNKNOWN_METHOD"

            # Log entry point
            if log_enabled:
                logger.info(f"{path} {method}")

            # Call the actual route function
            response = func(*args, **kwargs)

            # Log exit point, including response summary if possible
            try:
                if log_enabled:
                    if isinstance(response, StarletteResponse):
                        # Attempt to read response body (may be empty for StreamingResponse)
                        try:
                            body = (
                                response.body.decode("utf-8")
                                if isinstance(response.body, (bytes, bytearray))
                                else str(response.body)
                            )
                        except Exception:  # pragma: no cover
                            body = "File/Streaming response"

                        if "settings" in path:
                            body = "*** Settings are not logged ***"
                        logger.debug(f"{path} {method} - Response: {body}")
            except Exception as e:
                logger.exception(f"{path} {method} - {e})")

            return response
        return wrapper
    return decorator
