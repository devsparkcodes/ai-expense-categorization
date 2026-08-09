"""Centralized logging configuration for the application.

Services use the standard library `logging` with module loggers; this module
ensures a consistent level and format is applied to the root logger exactly
once (idempotent, safe under uvicorn reload and multiple startup runs).

No secrets, API keys, or sensitive transaction data are logged by the
application's log messages; the format below only shapes metadata around
whatever message is emitted.
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_HANDLER_MARKER = "_app_log_handler"


def setup_logging() -> None:
    """Configure root logging once.

    Level defaults to INFO and can be overridden with the LOG_LEVEL
    environment variable (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = _LEVELS.get(level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if any(getattr(handler, _HANDLER_MARKER, False) for handler in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
