"""Application-wide logger factory.

All modules should obtain their logger via ``get_logger(__name__)`` rather
than calling ``logging.getLogger`` directly, so the formatter and level are
applied consistently.
"""

import logging
import sys

from app.config import settings

#: Log format: timestamp | level | module name | message
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a configured ``Logger`` for *name*.

    Idempotent — calling this function multiple times with the same *name*
    returns the same logger without adding duplicate handlers.

    Args:
        name: Typically ``__name__`` of the calling module
            (e.g. ``"app.services.stock_service"``).

    Returns:
        A ``logging.Logger`` writing to *stdout* at ``DEBUG`` level when
        ``settings.DEBUG`` is ``True``, or ``INFO`` level in production.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    return logger
