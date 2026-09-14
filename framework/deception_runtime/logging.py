"""
Structured logging for deception runtime.
"""

import logging
from typing import Any


def get_logger(name: str) -> logging.Logger:
    """Get a logger with structured format."""
    logger = logging.getLogger(name)

    # Configure handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger


class StructuredLogger:
    """
    Logger wrapper that adds structured context fields to log messages.
    """

    def __init__(self, name: str):
        self.logger = get_logger(name)

    def _format_with_context(self, message: str, **context: Any) -> str:
        """Format message with context fields."""
        if not context:
            return message

        context_str = " ".join(f"{k}={v}" for k, v in context.items())
        return f"{message} | {context_str}"

    def debug(self, message: str, **context: Any) -> None:
        """Log debug message with context."""
        self.logger.debug(self._format_with_context(message, **context))

    def info(self, message: str, **context: Any) -> None:
        """Log info message with context."""
        self.logger.info(self._format_with_context(message, **context))

    def warning(self, message: str, **context: Any) -> None:
        """Log warning message with context."""
        self.logger.warning(self._format_with_context(message, **context))

    def error(self, message: str, **context: Any) -> None:
        """Log error message with context."""
        self.logger.error(self._format_with_context(message, **context))

    def exception(self, message: str, **context: Any) -> None:
        """Log exception with context."""
        self.logger.exception(self._format_with_context(message, **context))
