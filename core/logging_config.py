import logging
import sys
import structlog
from structlog.types import Processor
from .config import settings # To potentially use settings.DEBUG_MODE

def setup_logging():
    """
    Configures structured logging for the application.
    Outputs JSON logs to stdout.
    """
    # Processors for structlog. These are applied in order.
    shared_processors: list[Processor] = [
        structlog.stdlib.add_logger_name,  # Adds the logger name (e.g., "main", "routers.poll")
        structlog.stdlib.add_log_level,    # Adds the log level (e.g., "info", "error")
        structlog.stdlib.PositionalArgumentsFormatter(), # Formats positional arguments from %s style
        structlog.processors.StackInfoRenderer(), # Renders stack info for exceptions
        structlog.dev.set_exc_info,        # Adds exception info if an exception is passed
        structlog.processors.format_exc_info, # Formats exception info
        structlog.processors.TimeStamper(fmt="iso"), # Adds an ISO formatted timestamp
        # structlog.processors.CallsiteParameterAdder( # Adds module, function, line number
        #     [
        #         structlog.processors.CallsiteParameter.MODULE,
        #         structlog.processors.CallsiteParameter.FUNC_NAME,
        #         structlog.processors.CallsiteParameter.LINENO,
        #     ]
        # ),
    ]

    # Configure structlog to integrate with standard logging
    structlog.configure(
        processors=shared_processors + [
            # This processor prepares the event_dict for the stdlib formatter instance
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the standard logging handler to output JSON or human-readable logs
    # THIS IS THE CORRECTED PART: Instantiate ProcessorFormatter
    formatter = structlog.stdlib.ProcessorFormatter(
        # The 'processor' here is the final structlog renderer (JSON or Console).
        processor=structlog.dev.ConsoleRenderer() if settings.DEBUG_MODE else structlog.processors.JSONRenderer(),
        # 'foreign_pre_chain' is used by this formatter to process logs
        # from non-structlog loggers (e.g., uvicorn, sqlalchemy) before
        # they hit the final renderer.
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter) # Set the instantiated formatter

    # Get the root logger and add our handler
    root_logger = logging.getLogger()
    # Remove any existing handlers to avoid duplicate logs if setup_logging is called multiple times
    # (though it should ideally be called once)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO) # Set the default log level for the application

    # Optionally, silence overly verbose loggers from libraries
    # logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO) # Or WARNING for less SQL

    # Use structlog for this print statement to ensure it uses the configured pipeline
    # if it's meant to be a log. If it's just a startup message, print() is fine.
    # For consistency, let's use a logger here.
    bootstrap_logger = structlog.get_logger("bootstrap")
    bootstrap_logger.info(
        "logging_configured",
        debug_mode=settings.DEBUG_MODE,
        output_format='Console (human-readable)' if settings.DEBUG_MODE else 'JSON'
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Convenience function to get a structlog logger.
    """
    return structlog.get_logger(name)
