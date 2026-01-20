from core.utils.logging_utils import Logger
from robots.bilbo.robot.bilbo_core import BILBO_Core


# ======================================================================================================================
class BILBO_Estimation:
    """RobotManager-side estimation module for BILBO robot."""

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core):
        self.id = core.id
        self.device = core.device
        self.logger = Logger(f"Estimation [{core.id}]")
        self.core = core

        self._dead_reckoning_enabled: bool = True
        self._tracker_updates_enabled: bool = True

    # === METHODS ======================================================================================================
    def get_dead_reckoning_enabled(self) -> bool | None:
        """Get the dead-reckoning enabled state from the robot."""
        result = self.device.executeFunction(
            function_name='get_dead_reckoning_enabled',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result is not None:
            self._dead_reckoning_enabled = result
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_dead_reckoning_enabled(self, enable: bool) -> bool | None:
        """Set the dead-reckoning enabled state on the robot."""
        self.logger.info(f"Setting dead-reckoning enabled to {enable}")
        result = self.device.executeFunction(
            function_name='set_dead_reckoning_enabled',
            arguments={'enable': enable},
            return_type=bool,
            request_response=True
        )
        if result is not None:
            self._dead_reckoning_enabled = result
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def get_tracker_updates_enabled(self) -> bool | None:
        """Get whether tracker updates are being sent to lowlevel."""
        result = self.device.executeFunction(
            function_name='get_tracker_updates_enabled',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result is not None:
            self._tracker_updates_enabled = result
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_tracker_updates_enabled(self, enable: bool) -> bool | None:
        """Enable or disable sending tracker updates to lowlevel."""
        self.logger.info(f"Setting tracker updates enabled to {enable}")
        result = self.device.executeFunction(
            function_name='set_tracker_updates_enabled',
            arguments={'enable': enable},
            return_type=bool,
            request_response=True
        )
        if result is not None:
            self._tracker_updates_enabled = result
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        """Reset the lowlevel estimation (EKF, filters, position state)."""
        self.logger.info("Resetting lowlevel estimation")
        self.device.executeFunction(
            function_name='reset_estimation',
            arguments=None,
            return_type=None,
            request_response=False
        )

    # === PROPERTIES ===================================================================================================
    @property
    def dead_reckoning_enabled(self) -> bool:
        """Local cache of dead-reckoning enabled state."""
        return self._dead_reckoning_enabled

    @property
    def tracker_updates_enabled(self) -> bool:
        """Local cache of tracker updates enabled state."""
        return self._tracker_updates_enabled
