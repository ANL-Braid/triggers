"""
This module provides a function for initializing and configuring the logging
library for the app.
"""

import logging
import logging.config
import typing as t

import structlog
import typing_extensions as te

logger = structlog.get_logger(__name__)


def init_logging(
    log_level: t.Optional[str] = None,
    log_format: te.Literal["json", "console"] = "console",
):
    """
    This function configures the root logger to run in "console" or "json" mode.
    Whenever a module creates a new logger via logging.getLogger(__name__) or
    via structlog.get_logger(__name__), it will inherit these settings.
    """
    shared_processors: t.List[t.Callable] = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.contextvars.merge_contextvars,
    ]
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
                "foreign_pre_chain": shared_processors,
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "formatter": log_format
                if log_format.lower() in ["console", "json"]
                else "console",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "null": {
                "class": "logging.NullHandler",
            },
        },
        "loggers": {
            "werkzeug": {"handlers": ["null"], "propagate": False},
            "gunicorn": {
                "handlers": ["default"],
                "level": log_level.upper() if log_level else "INFO",
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["default"],
                "level": log_level.upper() if log_level else "INFO",
                "propagate": False,
            },
            "globus_sdk": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "globus_action_provider_tools": {
                "handlers": ["default"],
                "level": log_level.upper() if log_level else "INFO",
                "propagate": False,
            },
            "braid_triggers": {
                "handlers": ["default"],
                "level": log_level.upper() if log_level else "INFO",
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(logging_config)

    structlog.configure(
        logger_factory=structlog.stdlib.LoggerFactory(),
        processors=shared_processors
        + [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        cache_logger_on_first_use=True,
    )

    logger.info("Initialized logging", format=log_format, log_level=log_level)
