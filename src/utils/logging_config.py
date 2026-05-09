"""Logging configuration for Docker and local development."""
import logging
import sys
import os
from pythonjsonlogger import jsonlogger


def setup_logging(level=logging.INFO, docker_mode=True):
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        docker_mode: If True, output JSON logs to stdout (for Docker) and file
                    If False, output readable format to both stdout and stderr
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers = []

    if docker_mode:
        # Docker mode: JSON to stdout for log aggregation
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            fmt="%(timestamp)s %(level)s %(name)s %(message)s %(exc_info)s",
            timestamp=True,
            rename_fields={"levelname": "level", "name": "logger"}
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        # File handler: write readable logs to log.log
        log_dir = "/app/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "log.log")
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Separate handler for errors to stderr (for visibility)
        error_handler = logging.StreamHandler(sys.stderr)
        error_handler.setLevel(logging.ERROR)
        error_formatter = jsonlogger.JsonFormatter(
            fmt="%(timestamp)s ERROR %(name)s %(message)s %(exc_info)s %(exc_text)s",
            timestamp=True,
            rename_fields={"levelname": "level", "name": "logger"}
        )
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)

    else:
        # Local mode: readable format to stdout
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        # Also send errors to stderr with more detail
        error_handler = logging.StreamHandler(sys.stderr)
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | ERROR | %(message)s | %(exc_info)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        error_handler.setFormatter(error_formatter)
        root_logger.addHandler(error_handler)

        # File handler for local mode too
        log_file = "log.log"
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Set specific loggers to avoid too much noise
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
