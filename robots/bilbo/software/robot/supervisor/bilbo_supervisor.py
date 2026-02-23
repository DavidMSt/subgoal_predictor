from core.utils.exit import exit_program
from core.utils.logging_utils import Logger
from robot.communication.bilbo_communication import BILBO_Communication
from robot.error_handler import callbacks as error_callbacks, ErrorReport, ErrorSeverity


class BILBO_Supervisor:

    def __init__(self, comm: BILBO_Communication, control, utilities):
        self.comm = comm
        self.control = control
        self.utilities = utilities
        self.logger = Logger("Supervisor", "DEBUG")

    def init(self):
        error_callbacks.on_error.register(self._handle_error)

    def start(self):
        ...

    def _handle_error(self, report: ErrorReport):
        if report.severity == ErrorSeverity.MINOR:
            return

        if report.severity == ErrorSeverity.MAJOR:
            self.logger.error(f"MAJOR error from [{report.source}]: {report.message} — setting control OFF")
            self._set_control_off()
            self._play_warning()

        elif report.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"CRITICAL error from [{report.source}]: {report.message} — shutting down")
            self._set_control_off()
            self._play_warning()
            exit_program(1)

    def _set_control_off(self):
        try:
            from robot.control.bilbo_control_definitions import BILBO_Control_Mode
            self.control.set_mode(BILBO_Control_Mode.OFF)
        except Exception as e:
            self.logger.error(f"Failed to set control OFF: {e}")

    def _play_warning(self):
        try:
            self.utilities.playTone('warning')
        except Exception as e:
            self.logger.error(f"Failed to play warning tone: {e}")
