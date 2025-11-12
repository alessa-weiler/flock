"""
Logging Configuration for Flock Application

This module provides centralized logging configuration for the entire application.
It replaces print() statements with proper structured logging.

Usage:
    from logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("User logged in", extra={"user_id": user_id})
    logger.error("Payment failed", extra={"error": str(e)}, exc_info=True)
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Optional


class SensitiveDataFilter(logging.Filter):
    """Filter to remove sensitive data from logs"""

    SENSITIVE_KEYS = [
        'password', 'secret', 'token', 'api_key', 'apikey',
        'authorization', 'auth', 'key', 'credit_card', 'ssn',
        'email', 'phone', 'address'
    ]

    def filter(self, record):
        """Filter sensitive data from log records"""
        # Clean message
        message = str(record.msg).lower()
        for key in self.SENSITIVE_KEYS:
            if key in message:
                # Mask the value if it looks like a key=value pair
                if '=' in record.msg:
                    parts = str(record.msg).split('=')
                    if len(parts) > 1:
                        record.msg = f"{parts[0]}=***REDACTED***"

        # Clean extra data
        if hasattr(record, 'extra'):
            for key in self.SENSITIVE_KEYS:
                if key in record.extra:
                    record.extra[key] = "***REDACTED***"

        return True


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output (development)"""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record):
        """Add color to log level"""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True
) -> None:
    """
    Configure application-wide logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (default: logs/flock.log)
        enable_console: Enable console logging (default: True)
        enable_file: Enable file logging (default: True)
    """
    # Get log level from environment or parameter
    if log_level is None:
        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()

    # Validate log level
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers = []

    # Create formatters
    flask_env = os.environ.get('FLASK_ENV', 'development')

    if flask_env == 'development':
        # Colored formatter for development
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # JSON-like formatter for production (easier to parse)
        console_formatter = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"line":%(lineno)d,"message":"%(message)s"}',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )

    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-20s | Line:%(lineno)-4d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)

    # File handler
    if enable_file:
        if log_file is None:
            # Create logs directory if it doesn't exist
            log_dir = 'logs'
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'flock.log')

        # Rotating file handler (10MB max, keep 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)

    # Set levels for noisy third-party loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.INFO)

    # Log that logging has been configured
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured: level={log_level}, console={enable_console}, file={enable_file}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", extra={"user_id": 123})
    """
    return logging.getLogger(name)


# Exception hook to log uncaught exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    """Log uncaught exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        # Don't log keyboard interrupts
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = logging.getLogger(__name__)
    logger.critical(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback)
    )


# Install exception hook
sys.excepthook = handle_exception


# Initialize logging on import
if __name__ != '__main__':
    # Only setup logging if imported (not when run directly)
    setup_logging()
