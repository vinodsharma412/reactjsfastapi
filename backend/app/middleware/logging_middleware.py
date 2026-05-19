"""HTTP request/response logging middleware.

Logs every request with its method, path, response status code, and wall-clock
duration in milliseconds. Output goes to the application logger, which writes
to stdout via ``core/logging.py``.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that logs each HTTP request on completion."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Pass the request through the stack and log the outcome.

        Args:
            request: Incoming HTTP request from the ASGI framework.
            call_next: Next middleware or endpoint handler in the chain.

        Returns:
            The HTTP ``Response`` produced by the downstream handler.
        """
        start = time.time()
        response = await call_next(request)
        ms = round((time.time() - start) * 1000, 2)
        logger.info(
            "%s %s → %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response
