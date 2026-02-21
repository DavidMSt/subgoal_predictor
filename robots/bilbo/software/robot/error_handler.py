import enum
import dataclasses
import time

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.exit import exit_program
from core.utils.logging_utils import Logger

logger = Logger("ERROR_HANDLER")


class ErrorSeverity(enum.IntEnum):
    MINOR = 0
    MAJOR = 1
    CRITICAL = 2


@dataclasses.dataclass
class ErrorReport:
    severity: ErrorSeverity
    source: str
    message: str
    timestamp: float = dataclasses.field(default_factory=time.time)


@callback_definition
class ErrorHandlerCallbacks:
    on_error: CallbackContainer


callbacks = ErrorHandlerCallbacks()


def report_error(severity: ErrorSeverity, source: str, message: str) -> None:
    """Report an error through the centralized error handler.

    If no callbacks are registered (e.g. before supervisor init), CRITICAL
    errors fall back to exit_program(1) directly.
    """
    report = ErrorReport(severity=severity, source=source, message=message)

    if severity == ErrorSeverity.MINOR:
        logger.warning(f"[{source}] {message}")
    elif severity == ErrorSeverity.MAJOR:
        logger.error(f"[{source}] {message}")
    else:
        logger.critical(f"[{source}] {message}")

    if callbacks.on_error.callbacks:
        callbacks.on_error.call(report=report)
    elif severity == ErrorSeverity.CRITICAL:
        logger.critical("No error handler registered — forcing exit")
        exit_program(1)
