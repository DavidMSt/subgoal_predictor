"""
BILBO Position Control

High-level interface to the position control subsystem on the STM32.
Maintains a local representation of the waypoint queue and controller state,
synchronized via serial events from the firmware.

Control modes:
- IDLE: No active command
- TURN_TO_HEADING: Rotating in place to target heading
- DRIVE_TO_POINT: Driving to a single point
- FOLLOW_PATH: Following a waypoint path
"""

import ctypes
import dataclasses
import enum
import json
import math
import os
from typing import Any

import yaml

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent, WifiEventFlag,
)
from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, EventFlag, wait_for_events, OR, TIMEOUT
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control_definitions import PositionControl_Config, BILBO_Control_Mode
from robot.lowlevel.stm32_addresses import TWIPR_AddressTables, TWIPR_PositionControlAddresses
from robot.lowlevel.stm32_control import (
    BILBO_PositionControl_Event_Message,
    position_control_event_t,
    position_control_event_data,
    bilbo_position_control_data,
    bilbo_position_control_data_t,
    bilbo_waypoint_t,
    bilbo_path_start_cmd_t,
    turn_to_heading_command_t,
    move_to_point_command_t,
    bilbo_position_control_config_t,
)
from robot.lowlevel.stm32_sample import BILBO_LL_Sample


# =============================================================================
# ENUMS
# =============================================================================

class WaypointType(enum.IntEnum):
    """Waypoint arrival behavior"""
    PASS = 0  # Smooth transition, corner cutting allowed
    STOP = 1  # Must stop at this waypoint


class PositionControlMode(enum.IntEnum):
    """Position control operating modes"""
    IDLE = 0
    TURN_TO_HEADING = 1
    DRIVE_TO_POINT = 2
    FOLLOW_PATH = 3


class PathState(enum.IntEnum):
    """Path execution state"""
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclasses.dataclass
class Waypoint:
    """A single waypoint in the path

    Attributes:
        x: World X coordinate [m]
        y: World Y coordinate [m]
        type: PASS (smooth transition) or STOP (must stop at waypoint)
        weight: Corner sharpness [0-1], 1=sharp corner, 0=smooth cut
        speed: Maximum speed when approaching this waypoint [m/s].
               0 means use the path's default max_speed setting.
               Speed transitions smoothly between waypoints (~0.5s).
               Corner angle slowdown still applies (takes minimum).
    """
    x: float  # [m] world X coordinate
    y: float  # [m] world Y coordinate
    type: WaypointType = WaypointType.PASS  # arrival behavior
    weight: float = 0.75  # [0-1] corner sharpness (1=sharp, 0=smooth)
    speed: float = 0.0  # [m/s] max speed (0 = use path default)

    def to_ctypes(self) -> bilbo_waypoint_t:
        """Convert to ctypes struct for serial transmission"""
        return bilbo_waypoint_t(
            x=self.x,
            y=self.y,
            type=self.type.value,
            weight=self.weight,
            speed=self.speed
        )


def position_control_config_to_ctypes(config: PositionControl_Config) -> bilbo_position_control_config_t:
    """Convert PositionControl_Config to ctypes struct for serial transmission"""
    return bilbo_position_control_config_t(
        Ts=config.Ts,
        kp_angular=config.kp_angular,
        ki_angular=config.ki_angular,
        kp_linear=config.kp_linear,
        ki_linear=config.ki_linear,
        max_speed=config.max_speed,
        max_turn_rate=config.max_turn_rate,
        speed_transition_time=config.speed_transition_time,
        lookahead_base=config.lookahead_base,
        lookahead_gain=config.lookahead_gain,
        lookahead_max=config.lookahead_max,
        arrival_tolerance=config.arrival_tolerance,
        arrival_dwell_time=config.arrival_dwell_time,
        reverse_enter_angle=config.reverse_enter_angle,
        reverse_exit_angle=config.reverse_exit_angle,
        corner_slowdown_distance=config.corner_slowdown_distance,
    )


@dataclasses.dataclass
class PositionControlData:
    """Telemetry data from the position controller"""
    mode: PositionControlMode = PositionControlMode.IDLE
    path_state: PathState = PathState.IDLE
    buffer_capacity: int = 0  # max waypoints the STM32 buffer can hold
    buffer_used: int = 0  # current waypoints in STM32 buffer
    waypoint_count: int = 0
    current_segment: int = 0
    carrot_x: float = 0.0
    carrot_y: float = 0.0
    carrot_distance: float = 0.0  # [m] distance from robot to carrot
    heading_error: float = 0.0  # [rad] heading error to carrot
    speed_limit: float = 0.0  # [m/s] current speed limit
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0
    elapsed_time: float = 0.0
    remaining_path_length: float = 0.0


@dataclasses.dataclass
class MoveToPointCommand:
    """Tracking data for active move_to_point command"""
    x: float = 0.0
    y: float = 0.0
    max_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


@dataclasses.dataclass
class TurnToHeadingCommand:
    """Tracking data for active turn_to_heading command"""
    heading: float = 0.0
    max_angular_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


# =============================================================================
# EVENTS AND CALLBACKS
# =============================================================================

@event_definition
class PositionControlEvents:
    """Events emitted by the position controller"""
    # Path events
    path_started: Event
    path_paused: Event
    path_resumed: Event
    path_finished: Event
    path_aborted: Event
    path_timeout: Event

    # Waypoint events
    waypoint_passed: Event = Event(flags=EventFlag('index', int))
    waypoint_reached: Event = Event(flags=EventFlag('index', int))
    waypoint_completed: Event = Event(flags=EventFlag('index', int))
    waypoint_buffer_full: Event  # STM32 buffer is full, add_waypoint failed

    # Single-point command events
    move_to_point_started: Event
    move_to_point_completed: Event
    move_to_point_timeout: Event
    turn_to_heading_started: Event
    turn_to_heading_completed: Event
    turn_to_heading_timeout: Event

    # Mode change
    mode_changed: Event = Event(flags=EventFlag('mode', PositionControlMode))


@callback_definition
class PositionControlCallbacks:
    """Callbacks for position control events"""
    path_started: CallbackContainer
    path_finished: CallbackContainer
    path_timeout: CallbackContainer
    path_aborted: CallbackContainer
    waypoint_completed: CallbackContainer
    waypoint_buffer_full: CallbackContainer
    mode_changed: CallbackContainer


# =============================================================================
# WIFI EVENTS
# =============================================================================

@dataclasses.dataclass
class PositionControlCommonData:
    """Common data sent with every position control WiFi event"""
    mode: int = 0
    mode_name: str = ''
    path_state: int = 0
    waypoint_count: int = 0
    current_waypoint_index: int = 0


# Template: every position control WiFi event carries a 'group' flag
_PC_WIFI_EVENT = WifiEvent(data_type=dict, flags=WifiEventFlag('group', str))


@wifi_event_definition
class PositionControlWifiEvents(WifiEventContainer):
    """WiFi events sent by position control to host"""
    # Path events
    path_loaded: WifiEvent = _PC_WIFI_EVENT
    path_started: WifiEvent = _PC_WIFI_EVENT
    path_paused: WifiEvent = _PC_WIFI_EVENT
    path_resumed: WifiEvent = _PC_WIFI_EVENT
    path_finished: WifiEvent = _PC_WIFI_EVENT
    path_timeout: WifiEvent = _PC_WIFI_EVENT
    path_aborted: WifiEvent = _PC_WIFI_EVENT

    # Waypoint events
    waypoint_passed: WifiEvent = _PC_WIFI_EVENT
    waypoint_reached: WifiEvent = _PC_WIFI_EVENT
    waypoint_completed: WifiEvent = _PC_WIFI_EVENT
    waypoint_buffer_full: WifiEvent = _PC_WIFI_EVENT

    # Single-point command events
    move_to_point_started: WifiEvent = _PC_WIFI_EVENT
    move_to_point_completed: WifiEvent = _PC_WIFI_EVENT
    move_to_point_timeout: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_started: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_completed: WifiEvent = _PC_WIFI_EVENT
    turn_to_heading_timeout: WifiEvent = _PC_WIFI_EVENT

    # Mode change
    mode_changed: WifiEvent = _PC_WIFI_EVENT


# =============================================================================
# MAIN CLASS
# =============================================================================

class BILBO_PositionControl:
    """
    High-level interface to STM32 position control subsystem.

    Maintains a local waypoint queue that mirrors the STM32 buffer.
    Events from the firmware update local state automatically.
    """

    def __init__(self, common: BILBO_Common, communication: BILBO_Communication):
        self.logger = Logger("POS_CTRL", "DEBUG")
        self.common = common
        self.communication = communication

        # Events and callbacks
        self.events = PositionControlEvents()
        self.callbacks = PositionControlCallbacks()

        # WiFi events (registered on the interface, each sent as its own event)
        self.wifi_events = PositionControlWifiEvents(
            wifi=communication.wifi.wifi,
            id='position_control',
        )

        # Local state (mirrors STM32)
        self._mode = PositionControlMode.IDLE
        self._path_state = PathState.IDLE
        self._waypoint_queue: list[Waypoint] = []
        self._current_waypoint_index: int = 0
        self._data = PositionControlData()
        self._config = PositionControl_Config()

        # Track top-level control mode for waypoint validation
        self._top_level_control_mode = None

        # Command tracking
        self._command_id_counter: int = 0

        # Track active single-point commands for logging
        self._current_move_to_point = MoveToPointCommand()
        self._current_turn_to_heading = TurnToHeadingCommand()

        # Track current path data for visualization
        self._current_path_data: dict | None = None
        self._current_path_settings: dict = {}

        # Register for position control events from STM32
        self.communication.serial.callbacks.event.register(
            self._handle_position_control_event,
            parameters={'messages': [BILBO_PositionControl_Event_Message]}
        )

        # Register for sample updates to sync state
        self.communication.callbacks.rx_stm32_sample.register(self._lowlevel_sample_callback)

        # Register for control mode changes
        self.common.events.control_mode_change.on(self._on_control_mode_change)

        # Register WiFi commands
        self._register_wifi_commands()

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def mode(self) -> PositionControlMode:
        """Current position control mode"""
        return self._mode

    @property
    def path_state(self) -> PathState:
        """Current path execution state"""
        return self._path_state

    @property
    def waypoint_count(self) -> int:
        """Number of waypoints in local queue"""
        return len(self._waypoint_queue)

    @property
    def current_waypoint_index(self) -> int:
        """Index of current target waypoint"""
        return self._current_waypoint_index

    @property
    def is_busy(self) -> bool:
        """True if executing any command"""
        return self._mode != PositionControlMode.IDLE

    @property
    def is_path_running(self) -> bool:
        """True if currently following a path"""
        return self._mode == PositionControlMode.FOLLOW_PATH and self._path_state == PathState.RUNNING

    @property
    def data(self) -> PositionControlData:
        """Current telemetry data"""
        return self._data

    @property
    def buffer_capacity(self) -> int:
        """Maximum waypoints the STM32 buffer can hold"""
        return self._data.buffer_capacity

    @property
    def buffer_used(self) -> int:
        """Current number of waypoints in STM32 buffer"""
        return self._data.buffer_used

    @property
    def buffer_available(self) -> int:
        """Number of waypoints that can still be added"""
        return max(0, self._data.buffer_capacity - self._data.buffer_used)

    @property
    def waypoints(self) -> list[Waypoint]:
        """Copy of current waypoint queue"""
        return self._waypoint_queue.copy()

    @property
    def current_waypoint(self) -> Waypoint | None:
        """Current target waypoint, or None if queue is empty"""
        return self._waypoint_queue[0] if self._waypoint_queue else None

    @property
    def current_move_to_point_command(self) -> MoveToPointCommand | None:
        """Active move_to_point command, or None if not active"""
        return self._current_move_to_point if self._current_move_to_point.active else None

    @property
    def current_turn_to_heading_command(self) -> TurnToHeadingCommand | None:
        """Active turn_to_heading command, or None if not active"""
        return self._current_turn_to_heading if self._current_turn_to_heading.active else None

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def set_config(self, config: PositionControl_Config) -> bool:
        """Set position control configuration on STM32"""
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.SET_CONFIG,
            input_type=bilbo_position_control_config_t,
            output_type=ctypes.c_bool,
            data=position_control_config_to_ctypes(config)
        )
        if result:
            self._config = config
            self.logger.info("Position control config set successfully")
        else:
            self.logger.error("Failed to set position control config")
        return result or False

    def get_config(self) -> PositionControl_Config:
        """Get current configuration"""
        return self._config

    # =========================================================================
    # WAYPOINT MANAGEMENT
    # =========================================================================

    def clear_waypoints(self) -> bool:
        """Clear all waypoints from queue (local and STM32)"""
        if self.is_busy:
            self.logger.warning("Cannot clear waypoints while busy")
            return False

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.CLEAR_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self._waypoint_queue.clear()
            self._current_waypoint_index = 0
            self.logger.debug("Waypoints cleared")
        else:
            self.logger.error("Failed to clear waypoints on STM32")

        return result or False

    def add_waypoint(self, waypoint: Waypoint) -> bool:
        """Add a waypoint to the queue"""
        from robot.control.bilbo_control_definitions import BILBO_Control_Mode

        # Check if in POSITION mode - waypoints can only be added in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot add waypoints when not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning("Cannot add waypoint while busy")
            return False

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.ADD_WAYPOINT,
            input_type=bilbo_waypoint_t,
            output_type=ctypes.c_bool,
            data=waypoint.to_ctypes()
        )

        if result:
            self._waypoint_queue.append(waypoint)
            self.logger.debug(f"Added waypoint ({waypoint.x:.2f}, {waypoint.y:.2f})")
        else:
            self.logger.error("Failed to add waypoint to STM32")

        return result or False

    def add_waypoint_xy(self, x: float, y: float,
                        type: WaypointType = WaypointType.PASS,
                        weight: float = 0.75,
                        speed: float = 0.0) -> bool:
        """Convenience method to add waypoint by coordinates

        Args:
            x: World X coordinate [m]
            y: World Y coordinate [m]
            type: PASS (smooth transition) or STOP (must stop)
            weight: Corner sharpness [0-1], 1=sharp, 0=smooth
            speed: Max speed for this waypoint [m/s], 0=use path default
        """
        return self.add_waypoint(Waypoint(x=x, y=y, type=type, weight=weight, speed=speed))

    def add_waypoints(self, waypoints: list[Waypoint]) -> bool:
        """Add multiple waypoints to the queue"""
        for wp in waypoints:
            if not self.add_waypoint(wp):
                return False
        return True

    def get_waypoints(self) -> list[Waypoint]:
        """Get copy of current waypoint queue"""
        return self._waypoint_queue.copy()

    def get_current_waypoint(self) -> Waypoint | None:
        """Get the current target waypoint from STM32"""
        wp_data = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.READ_CURRENT_WAYPOINT,
            input_type=None,
            output_type=bilbo_waypoint_t
        )
        if wp_data is None:
            return None

        return Waypoint(
            x=wp_data.x,
            y=wp_data.y,
            type=WaypointType(wp_data.type),
            weight=wp_data.weight,
            speed=wp_data.speed
        )

    # =========================================================================
    # PATH FOLLOWING
    # =========================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def start_path(self, allow_reverse: bool = False,
                   timeout: float = 0.0,
                   max_speed: float = 0.0) -> bool:
        """
        Start following the loaded waypoint path.

        Args:
            allow_reverse: If True, robot may drive backwards when efficient
            timeout: Maximum time for path execution (0 = no timeout)
            max_speed: Speed override (0 = use config default)
        """
        if self.is_busy:
            self.logger.warning("Cannot start path: already busy")
            return False

        if len(self._waypoint_queue) < 2:
            self.logger.warning("Cannot start path: need at least 2 waypoints")
            return False

        cmd = bilbo_path_start_cmd_t(
            allow_reverse=1 if allow_reverse else 0,
            timeout=timeout,
            max_speed=max_speed
        )

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.START_PATH,
            input_type=bilbo_path_start_cmd_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self._current_waypoint_index = 0
            # Update path settings
            self._current_path_settings = {
                'max_speed': max_speed,
                'allow_reverse': allow_reverse,
                'timeout': timeout
            }
            self.logger.info(f"Started path with {len(self._waypoint_queue)} waypoints")
        else:
            self.logger.error("Failed to start path on STM32")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def pause_path(self) -> bool:
        """Pause path execution (can be resumed)"""
        if not self.is_path_running:
            self.logger.warning("Cannot pause: not running")
            return False

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.PAUSE_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self.logger.info("Path paused")
        else:
            self.logger.error("Failed to pause path")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def resume_path(self) -> bool:
        """Resume paused path execution"""
        if self._path_state != PathState.PAUSED:
            self.logger.warning("Cannot resume: not paused")
            return False

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.RESUME_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self.logger.info("Path resumed")
        else:
            self.logger.error("Failed to resume path")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def abort_path(self) -> bool:
        """Abort path execution"""
        if self._mode != PositionControlMode.FOLLOW_PATH:
            self.logger.warning("Cannot abort: not following path")
            return False

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.ABORT_PATH,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self.logger.info("Path aborted")
        else:
            self.logger.error("Failed to abort path")

        return result or False

    # ------------------------------------------------------------------------------------------------------------------
    def load_path(self, path_data: dict,
                  start: bool = False,
                  clear_existing: bool = True,
                  allow_reverse: bool | None = None,
                  timeout: float | None = None,
                  max_speed: float | None = None) -> bool:
        """
        Load waypoints from a path dictionary.

        Path dict format:
            {
                "max_speed": 0.3,        # optional, m/s (0 = use default)
                "allow_reverse": true,   # optional, default: true
                "timeout": 30.0,         # optional, seconds (0 = no timeout)
                "waypoints": [
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.5, "y": -0.3, "type": "STOP", "weight": 0.9, "speed": 0.2}
                ]
            }

        Waypoint fields:
            - x, y: Required, position in world coordinates [m]
            - type: Optional, "PASS" (default) or "STOP"
            - weight: Optional [0-1], corner sharpness (default 0.75)
            - speed: Optional [m/s], max speed for this waypoint (0 = use path default)
                     Speed transitions smoothly between waypoints over ~0.5s

        Args:
            path_data: Dictionary containing waypoints and optional settings
            start: If True, automatically start the path after loading
            clear_existing: If True, clear existing waypoints before loading
            allow_reverse: Override for allow_reverse (None = use dict value or default True)
            timeout: Override for timeout (None = use dict value or default 0)
            max_speed: Override for max_speed (None = use dict value or default 0)

        Returns:
            True if waypoints were loaded (and started if requested) successfully
        """
        # Extract optional path settings from dict (function args override if provided)
        dict_max_speed = float(path_data.get('max_speed', 0.0))
        dict_allow_reverse = bool(path_data.get('allow_reverse', True))
        dict_timeout = float(path_data.get('timeout', 0.0))

        # Use function arguments if provided, otherwise use dict values
        effective_max_speed = max_speed if max_speed is not None else dict_max_speed
        effective_allow_reverse = allow_reverse if allow_reverse is not None else dict_allow_reverse
        effective_timeout = timeout if timeout is not None else dict_timeout

        # Extract waypoints
        if 'waypoints' not in path_data:
            self.logger.error("Path data missing 'waypoints' key")
            return False

        waypoints_data = path_data['waypoints']
        if not isinstance(waypoints_data, list) or len(waypoints_data) == 0:
            self.logger.error("Path data 'waypoints' must be a non-empty list")
            return False

        # Parse waypoints
        waypoints: list[Waypoint] = []
        for i, wp_data in enumerate(waypoints_data):
            try:
                # Required fields
                if 'x' not in wp_data or 'y' not in wp_data:
                    self.logger.error(f"Waypoint {i} missing 'x' or 'y' coordinate")
                    return False

                x = float(wp_data['x'])
                y = float(wp_data['y'])

                # Optional fields with defaults
                weight = float(wp_data.get('weight', 0.75))
                speed = float(wp_data.get('speed', 0.0))

                # Parse type (string or int)
                type_value = wp_data.get('type', 'PASS')
                if isinstance(type_value, str):
                    type_value = type_value.upper()
                    if type_value == 'PASS':
                        wp_type = WaypointType.PASS
                    elif type_value == 'STOP':
                        wp_type = WaypointType.STOP
                    else:
                        self.logger.error(f"Waypoint {i} has invalid type: {type_value}. Use 'PASS' or 'STOP'")
                        return False
                else:
                    wp_type = WaypointType(int(type_value))

                waypoints.append(Waypoint(x=x, y=y, type=wp_type, weight=weight, speed=speed))

            except (ValueError, KeyError) as e:
                self.logger.error(f"Failed to parse waypoint {i}: {e}")
                return False

        # Clear existing waypoints if requested
        if clear_existing:
            if not self.clear_waypoints():
                self.logger.error("Failed to clear existing waypoints")
                return False

        # Add waypoints to STM32
        self.logger.info(f"Loading {len(waypoints)} waypoints")
        for i, wp in enumerate(waypoints):
            if not self.add_waypoint(wp):
                self.logger.error(f"Failed to add waypoint {i}: ({wp.x:.2f}, {wp.y:.2f})")
                return False

        self.logger.info(f"Loaded path: {' -> '.join([f'({wp.x:.2f}, {wp.y:.2f})' for wp in waypoints])}")

        # Store path data for visualization
        self._current_path_data = path_data
        self._current_path_settings = {
            'max_speed': effective_max_speed,
            'allow_reverse': effective_allow_reverse,
            'timeout': effective_timeout
        }

        # Send path_loaded event with full path data
        self.wifi_events.path_loaded.send(
            data=self._common_event_data(
                waypoints=[{'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'type_name': wp.type.name,
                            'weight': wp.weight, 'speed': wp.speed} for wp in waypoints],
                settings=self._current_path_settings,
            ),
            flags=self._WIFI_FLAGS,
        )

        # Start path if requested
        if start:
            return self.start_path(
                allow_reverse=effective_allow_reverse,
                timeout=effective_timeout,
                max_speed=effective_max_speed
            )

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def load_path_from_file(self, filepath: str,
                            start: bool = False,
                            clear_existing: bool = True,
                            allow_reverse: bool | None = None,
                            timeout: float | None = None,
                            max_speed: float | None = None) -> bool:
        """
        Load waypoints from a JSON or YAML file.

        YAML format (simple, for manual definition):
            max_speed: 0.3          # optional, m/s (0 = use default)
            allow_reverse: true     # optional, default: true
            timeout: 30.0           # optional, seconds (0 = no timeout)
            waypoints:
              - x: 1.0
                y: 0.0
              - x: 1.5
                y: -0.3
                type: STOP          # optional, default: PASS
                weight: 0.9         # optional, default: 0.75
                speed: 0.2          # optional, m/s (0 = use path default)

        JSON format (for generated paths):
            {
                "max_speed": 0.3,
                "allow_reverse": true,
                "timeout": 30.0,
                "waypoints": [
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.5, "y": -0.3, "type": "STOP", "weight": 0.9, "speed": 0.2}
                ]
            }

        Speed transitions smoothly between waypoints over ~0.5s.
        Corner angle slowdown still applies (takes minimum of waypoint speed and corner limit).

        Args:
            filepath: Path to .json or .yaml/.yml file
            start: If True, automatically start the path after loading
            clear_existing: If True, clear existing waypoints before loading
            allow_reverse: Override for allow_reverse (None = use file value or default True)
            timeout: Override for timeout (None = use file value or default 0)
            max_speed: Override for max_speed (None = use file value or default 0)

        Returns:
            True if waypoints were loaded (and started if requested) successfully
        """
        # Check file exists
        if not os.path.isfile(filepath):
            self.logger.error(f"Path file not found: {filepath}")
            return False

        # Determine file type
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        if ext not in ['.json', '.yaml', '.yml']:
            self.logger.error(f"Unsupported file type: {ext}. Use .json, .yaml, or .yml")
            return False

        # Load and parse file
        try:
            with open(filepath, 'r') as f:
                if ext == '.json':
                    path_data = json.load(f)
                else:
                    path_data = yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Failed to parse path file: {e}")
            return False

        self.logger.info(f"Loading path from {os.path.basename(filepath)}")

        # Delegate to load_path()
        return self.load_path(
            path_data=path_data,
            start=start,
            clear_existing=clear_existing,
            allow_reverse=allow_reverse,
            timeout=timeout,
            max_speed=max_speed
        )

    # =========================================================================
    # SINGLE-POINT COMMANDS
    # =========================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def move_to_point(self, x: float, y: float,
                      max_speed: float = 0.0,
                      timeout: float = 0.0,
                      blocking: bool = False) -> bool:
        """
        Drive to a single point.

        Args:
            x, y: Target position in world coordinates [m]
            max_speed: Maximum speed (0 = use config default)
            timeout: Command timeout (0 = no timeout)
        """

        # Check if in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot move to point: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning(f"Cannot move to point: already busy (mode: {self._mode.name})")
            return False

        self._command_id_counter = (self._command_id_counter + 1) % 256
        cmd = move_to_point_command_t(
            id=self._command_id_counter,
            x_target=x,
            y_target=y,
            timeout=timeout,
            max_speed=max_speed
        )

        # Track the command BEFORE sending (event may arrive before executeFunction returns)
        self._current_move_to_point = MoveToPointCommand(
            x=x, y=y, max_speed=max_speed, timeout=timeout, active=True
        )

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.MOVE_TO_POINT,
            input_type=move_to_point_command_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self.logger.info(f"Moving to point ({x:.2f}, {y:.2f})")
        else:
            # Reset tracking if command failed
            self._current_move_to_point = MoveToPointCommand()
            self.logger.error("Failed to start move_to_point command")
            return False

        if not blocking:
            return True

        wait_timeout = timeout + 5.0 if timeout > 0 else 30.0  # maximum time of 30 seconds to go to a point
        data, trace = wait_for_events(
            OR(
                self.events.move_to_point_completed,
                self.events.move_to_point_timeout
            ),
            timeout=wait_timeout
        )

        if data is TIMEOUT or trace.caused_by(self.events.move_to_point_timeout):
            self.logger.warning(f"Move to point timed out")
            self._current_move_to_point = MoveToPointCommand()
            if data is TIMEOUT:
                # Python wait expired but firmware still running — force stop
                self.reset()
            return False

        self.logger.info(f"Move to point completed ({x:.2f}, {y:.2f})")
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to_heading(self, heading: float,
                        max_angular_speed: float = 0.0,
                        timeout: float = 0.0,
                        blocking: bool = False) -> bool:
        """
        Rotate in place to face target heading.

        Args:
            heading: Target heading [rad]
            max_angular_speed: Maximum turn rate (0 = use config default)
            timeout: Command timeout (0 = no timeout)
            blocking: If True, block until heading reached or timeout
        """
        from robot.control.bilbo_control_definitions import BILBO_Control_Mode

        # Check if in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot turn to heading: not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if self.is_busy:
            self.logger.warning(f"Cannot turn to heading: already busy (mode: {self._mode.name})")
            return False

        self._command_id_counter = (self._command_id_counter + 1) % 256
        cmd = turn_to_heading_command_t(
            id=self._command_id_counter,
            heading_ref=heading,
            timeout=timeout,
            max_angular_speed=max_angular_speed
        )

        # Track the command BEFORE sending (event may arrive before executeFunction returns)
        self._current_turn_to_heading = TurnToHeadingCommand(
            heading=heading, max_angular_speed=max_angular_speed, timeout=timeout, active=True
        )

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.TURN_TO_HEADING,
            input_type=turn_to_heading_command_t,
            output_type=ctypes.c_bool,
            data=cmd
        )

        if result:
            self.logger.info(f"Turning to heading {heading:.2f} rad ({math.degrees(heading):.1f} deg)")
        else:
            # Reset tracking if command failed
            self._current_turn_to_heading = TurnToHeadingCommand()
            self.logger.error("Failed to start turn_to_heading command")
            return False

        if not blocking:
            return True

        wait_timeout = timeout + 5.0 if timeout > 0 else 15.0
        data, trace = wait_for_events(
            OR(
                self.events.turn_to_heading_completed,
                self.events.turn_to_heading_timeout
            ),
            timeout=wait_timeout
        )

        if data is TIMEOUT or trace.caused_by(self.events.turn_to_heading_timeout):
            self.logger.warning(f"Turn to heading timed out")
            self._current_turn_to_heading = TurnToHeadingCommand()
            if data is TIMEOUT:
                # Python wait expired but firmware still running — force stop
                self.reset()
            return False

        self.logger.info(f"Turn to heading completed ({math.degrees(heading):.1f} deg)")
        return True

    # =========================================================================
    # RESET
    # =========================================================================

    def reset(self) -> bool:
        """Reset position control to idle state"""
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.RESET,
            input_type=None,
            output_type=ctypes.c_bool,
        )

        if result:
            self._mode = PositionControlMode.IDLE
            self._path_state = PathState.IDLE
            self._waypoint_queue.clear()
            self._current_waypoint_index = 0
            # Clear command tracking
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
            self.logger.info("Position control reset")
        else:
            self.logger.error("Failed to reset position control")

        return result or False

    # =========================================================================
    # DATA RETRIEVAL
    # =========================================================================

    def get_data_from_stm32(self) -> PositionControlData | None:
        """Read current telemetry data from STM32"""
        data = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_PositionControlAddresses.READ_DATA,
            input_type=None,
            output_type=bilbo_position_control_data_t
        )
        if data is None:
            return None

        data_dict = from_dict_auto(bilbo_position_control_data, data)
        self._update_data_from_dict(dataclasses.asdict(data_dict))
        return self._data

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================

    def _handle_position_control_event(self, message: BILBO_PositionControl_Event_Message):
        """Handle events from STM32 position controller"""
        try:
            event_data = from_dict_auto(position_control_event_data, message.data)
            event = position_control_event_t(event_data.event)
        except (KeyError, ValueError) as e:
            self.logger.warning(f"Invalid position control event: {e}")
            return

        self.logger.debug(f"Position control event: {event.name}")

        # Update local data from event
        self._update_data_from_dict(dataclasses.asdict(event_data.data))

        match event:
            # Path events
            case position_control_event_t.PATH_STARTED:
                self._mode = PositionControlMode.FOLLOW_PATH
                self._path_state = PathState.RUNNING
                self.events.path_started.set()
                self.callbacks.path_started.call()
                # Send path data with event for visualization
                self.wifi_events.path_started.send(
                    data=self._common_event_data(
                        waypoints=[{'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'type_name': wp.type.name,
                                    'weight': wp.weight, 'speed': wp.speed} for wp in self._waypoint_queue],
                        settings=self._current_path_settings,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.PATH_PAUSED:
                self._path_state = PathState.PAUSED
                self.events.path_paused.set()
                self.wifi_events.path_paused.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_RESUMED:
                self._path_state = PathState.RUNNING
                self.events.path_resumed.set()
                self.wifi_events.path_resumed.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_FINISHED:
                self._mode = PositionControlMode.IDLE
                self._path_state = PathState.IDLE
                # Log final waypoint before clearing
                if self._waypoint_queue:
                    final_wp = self._waypoint_queue[-1]
                    self.logger.info(f"Path finished! Reached final waypoint: ({final_wp.x:.2f}, {final_wp.y:.2f})")
                else:
                    self.logger.info("Path finished!")
                self._waypoint_queue.clear()
                self.events.path_finished.set()
                self.callbacks.path_finished.call()
                self.wifi_events.path_finished.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_TIMEOUT:
                self._mode = PositionControlMode.IDLE
                self._path_state = PathState.IDLE
                # Log where we timed out
                if self._waypoint_queue:
                    target_wp = self._waypoint_queue[0]
                    self.logger.warning(f"Path timed out! Target was: ({target_wp.x:.2f}, {target_wp.y:.2f})")
                else:
                    self.logger.warning("Path timed out!")
                self._waypoint_queue.clear()
                self.events.path_timeout.set()
                self.callbacks.path_timeout.call()
                self.wifi_events.path_timeout.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case position_control_event_t.PATH_ABORTED:
                self._mode = PositionControlMode.IDLE
                self._path_state = PathState.IDLE
                # Log where we aborted
                if self._waypoint_queue:
                    target_wp = self._waypoint_queue[0]
                    self.logger.warning(f"Path aborted! Was heading to: ({target_wp.x:.2f}, {target_wp.y:.2f})")
                else:
                    self.logger.warning("Path aborted!")
                self._waypoint_queue.clear()
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()
                self.wifi_events.path_aborted.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            # Waypoint events
            case position_control_event_t.WAYPOINT_PASSED:
                idx = event_data.waypoint_index
                self._current_waypoint_index = idx
                # Log waypoint coordinates
                wp_data = None
                if idx < len(self._waypoint_queue):
                    wp = self._waypoint_queue[idx]
                    wp_data = {'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'type_name': wp.type.name,
                               'weight': wp.weight, 'speed': wp.speed}
                    self.logger.info(f"Passed waypoint {idx}: ({wp.x:.2f}, {wp.y:.2f}) [{wp.type.name}]")
                else:
                    self.logger.info(f"Passed waypoint {idx}")
                self.events.waypoint_passed.set(flags={'index': idx})
                self.wifi_events.waypoint_passed.send(
                    data=self._common_event_data(waypoint_index=idx, waypoint=wp_data),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.WAYPOINT_REACHED:
                idx = event_data.waypoint_index
                # Log waypoint coordinates
                wp_data = None
                if idx < len(self._waypoint_queue):
                    wp = self._waypoint_queue[idx]
                    wp_data = {'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'type_name': wp.type.name,
                               'weight': wp.weight, 'speed': wp.speed}
                    self.logger.info(f"Reached waypoint {idx}: ({wp.x:.2f}, {wp.y:.2f}) [{wp.type.name}]")
                else:
                    self.logger.info(f"Reached waypoint {idx}")
                self.events.waypoint_reached.set(flags={'index': idx})
                self.wifi_events.waypoint_reached.send(
                    data=self._common_event_data(waypoint_index=idx, waypoint=wp_data),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.WAYPOINT_COMPLETED:
                idx = event_data.waypoint_index
                # Log waypoint coordinates before removing from queue
                wp_data = None
                next_wp_data = None
                if self._waypoint_queue:
                    wp = self._waypoint_queue[0]
                    wp_data = {'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'type_name': wp.type.name,
                               'weight': wp.weight, 'speed': wp.speed}
                    next_wp_info = ""
                    if len(self._waypoint_queue) > 1:
                        next_wp = self._waypoint_queue[1]
                        next_wp_data = {'x': next_wp.x, 'y': next_wp.y, 'type': next_wp.type.value,
                                        'type_name': next_wp.type.name, 'weight': next_wp.weight,
                                        'speed': next_wp.speed}
                        next_wp_info = f" -> Next: ({next_wp.x:.2f}, {next_wp.y:.2f})"
                    self.logger.info(
                        f"Completed waypoint {idx}: ({wp.x:.2f}, {wp.y:.2f}) [{wp.type.name}]{next_wp_info}")
                    self._waypoint_queue.pop(0)
                else:
                    self.logger.info(f"Completed waypoint {idx}")
                self._current_waypoint_index = idx + 1
                self.events.waypoint_completed.set(flags={'index': idx})
                self.callbacks.waypoint_completed.call(idx)
                self.wifi_events.waypoint_completed.send(
                    data=self._common_event_data(waypoint_index=idx, waypoint=wp_data, next_waypoint=next_wp_data),
                    flags=self._WIFI_FLAGS,
                )

            # Single-point command events
            case position_control_event_t.MOVE_TO_POINT_STARTED:
                self._mode = PositionControlMode.DRIVE_TO_POINT
                self.events.move_to_point_started.set()
                # Send target coordinates with event
                cmd = self._current_move_to_point
                self.wifi_events.move_to_point_started.send(
                    data=self._common_event_data(
                        target={'x': cmd.x, 'y': cmd.y}, max_speed=cmd.max_speed, timeout=cmd.timeout,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.MOVE_TO_POINT_COMPLETED:
                self._mode = PositionControlMode.IDLE
                # Log with target coordinates
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                if cmd.active:
                    self.logger.info(f"Reached point ({cmd.x:.2f}, {cmd.y:.2f})")
                    self._current_move_to_point.active = False
                else:
                    self.logger.info("Move to point completed")
                self.events.move_to_point_completed.set()
                self.wifi_events.move_to_point_completed.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.MOVE_TO_POINT_TIMEOUT:
                self._mode = PositionControlMode.IDLE
                # Log with target coordinates
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                if cmd.active:
                    self.logger.warning(f"Move to point ({cmd.x:.2f}, {cmd.y:.2f}) timed out")
                    self._current_move_to_point.active = False
                else:
                    self.logger.warning("Move to point timed out")
                self.events.move_to_point_timeout.set()
                self.wifi_events.move_to_point_timeout.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_STARTED:
                self._mode = PositionControlMode.TURN_TO_HEADING
                self.events.turn_to_heading_started.set()
                # Send target heading with event
                cmd = self._current_turn_to_heading
                self.wifi_events.turn_to_heading_started.send(
                    data=self._common_event_data(
                        heading=cmd.heading, heading_deg=math.degrees(cmd.heading),
                        max_angular_speed=cmd.max_angular_speed, timeout=cmd.timeout,
                    ),
                    flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_COMPLETED:
                self._mode = PositionControlMode.IDLE
                # Log with target heading
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                if cmd.active:
                    self.logger.info(f"Reached heading {cmd.heading:.2f} rad ({math.degrees(cmd.heading):.1f} deg)")
                    self._current_turn_to_heading.active = False
                else:
                    self.logger.info("Turn to heading completed")
                self.events.turn_to_heading_completed.set()
                self.wifi_events.turn_to_heading_completed.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )

            case position_control_event_t.TURN_TO_HEADING_TIMEOUT:
                self._mode = PositionControlMode.IDLE
                # Log with target heading
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                if cmd.active:
                    self.logger.warning(
                        f"Turn to heading {cmd.heading:.2f} rad ({math.degrees(cmd.heading):.1f} deg) timed out")
                    self._current_turn_to_heading.active = False
                else:
                    self.logger.warning("Turn to heading timed out")
                self.events.turn_to_heading_timeout.set()
                self.wifi_events.turn_to_heading_timeout.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )

            # Mode change
            case position_control_event_t.MODE_CHANGED:
                new_mode = PositionControlMode(event_data.data.mode)
                self._mode = new_mode
                self.events.mode_changed.set(flags={'mode': new_mode})
                self.callbacks.mode_changed.call(new_mode)
                self.wifi_events.mode_changed.send(
                    data=self._common_event_data(new_mode=new_mode.value, new_mode_name=new_mode.name),
                    flags=self._WIFI_FLAGS,
                )

            # Buffer full
            case position_control_event_t.WAYPOINT_BUFFER_FULL:
                self.logger.warning("Waypoint buffer full on STM32")
                self.events.waypoint_buffer_full.set()
                self.callbacks.waypoint_buffer_full.call()
                self.wifi_events.waypoint_buffer_full.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)

            case _:
                self.logger.warning(f"Unhandled position control event: {event}")

    def _update_data_from_dict(self, data_dict: dict):
        """Update local telemetry data from dictionary"""
        try:
            self._data.mode = PositionControlMode(data_dict.get('mode', 0))
            self._data.path_state = PathState(data_dict.get('path_state', 0))
            self._data.buffer_capacity = data_dict.get('buffer_capacity', 0)
            self._data.buffer_used = data_dict.get('buffer_used', 0)
            self._data.waypoint_count = data_dict.get('waypoint_count', 0)
            self._data.current_segment = data_dict.get('current_segment', 0)
            self._data.carrot_x = data_dict.get('carrot_x', 0.0)
            self._data.carrot_y = data_dict.get('carrot_y', 0.0)
            self._data.carrot_distance = data_dict.get('carrot_distance', 0.0)
            self._data.heading_error = data_dict.get('heading_error', 0.0)
            self._data.speed_limit = data_dict.get('speed_limit', 0.0)
            self._data.elapsed_time = data_dict.get('elapsed_time', 0.0)
            self._data.remaining_path_length = data_dict.get('remaining_path_length', 0.0)

            if 'output' in data_dict:
                self._data.v_cmd = data_dict['output'].get('v_cmd', 0.0)
                self._data.psi_dot_cmd = data_dict['output'].get('psi_dot_cmd', 0.0)
        except Exception as e:
            self.logger.warning(f"Failed to update data from dict: {e}")

    def _lowlevel_sample_callback(self, sample: BILBO_LL_Sample):
        """Handle low-level sample updates"""
        # Sync position control data from sample if available
        if hasattr(sample, 'control') and hasattr(sample.control, 'position_control_data'):
            pos_data = sample.control.position_control_data
            # Check for mode mismatch
            stm32_mode = PositionControlMode(pos_data.mode)
            if stm32_mode != self._mode:
                self.logger.debug(f"Mode mismatch: local={self._mode.name}, STM32={stm32_mode.name}")
                self._mode = stm32_mode

    def _on_control_mode_change(self, mode, *args, **kwargs):
        """Handle top-level control mode changes"""
        from robot.control.bilbo_control_definitions import BILBO_Control_Mode

        # Track top-level control mode
        self._top_level_control_mode = mode

        if mode == BILBO_Control_Mode.POSITION:
            # Entering POSITION mode: clear local waypoints to sync with firmware
            # (firmware clears waypoints when entering POSITION mode)
            if self._waypoint_queue:
                self.logger.info("Entering POSITION mode, clearing local waypoint queue to sync with firmware")
            self._waypoint_queue.clear()
            self._current_waypoint_index = 0
            self._mode = PositionControlMode.IDLE
            self._path_state = PathState.IDLE
            # Clear command tracking
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
        else:
            # Leaving POSITION mode: fire termination events if commands were active.
            # The firmware also sends these events on reset(), but this acts as a safety net
            # in case the serial events are delayed or lost.
            if self._mode == PositionControlMode.FOLLOW_PATH:
                self.logger.warning(f"Control mode changed to {mode.name} while path was running, aborting path")
                self._mode = PositionControlMode.IDLE
                self._path_state = PathState.IDLE
                self._waypoint_queue.clear()
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()
                self.wifi_events.path_aborted.send(data=self._common_event_data(), flags=self._WIFI_FLAGS)
            elif self._mode == PositionControlMode.DRIVE_TO_POINT:
                self.logger.warning(f"Control mode changed to {mode.name} while move_to_point was active")
                cmd = self._current_move_to_point
                target_data = {'x': cmd.x, 'y': cmd.y} if cmd.active else None
                self._mode = PositionControlMode.IDLE
                self._current_move_to_point = MoveToPointCommand()
                self.events.move_to_point_timeout.set()
                self.wifi_events.move_to_point_timeout.send(
                    data=self._common_event_data(target=target_data), flags=self._WIFI_FLAGS,
                )
            elif self._mode == PositionControlMode.TURN_TO_HEADING:
                self.logger.warning(f"Control mode changed to {mode.name} while turn_to_heading was active")
                cmd = self._current_turn_to_heading
                heading_data = {'heading': cmd.heading,
                                'heading_deg': math.degrees(cmd.heading)} if cmd.active else None
                self._mode = PositionControlMode.IDLE
                self._current_turn_to_heading = TurnToHeadingCommand()
                self.events.turn_to_heading_timeout.set()
                self.wifi_events.turn_to_heading_timeout.send(
                    data=self._common_event_data(**(heading_data or {})), flags=self._WIFI_FLAGS,
                )
            elif self._mode != PositionControlMode.IDLE:
                self.logger.info(f"Control mode changed to {mode.name}, resetting position control state")

            # Always clean up local state
            self._mode = PositionControlMode.IDLE
            self._path_state = PathState.IDLE
            self._waypoint_queue.clear()
            self._current_waypoint_index = 0
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_sample_dict(self) -> dict:
        """Get current state as dictionary for logging/streaming"""
        return {
            'mode': self._mode.value,
            'mode_name': self._mode.name,
            'path_state': self._path_state.value,
            'path_state_name': self._path_state.name,
            'waypoint_count': len(self._waypoint_queue),
            'current_waypoint_index': self._current_waypoint_index,
            'is_busy': self.is_busy,
            'data': dataclasses.asdict(self._data),
            'waypoints': list(self._waypoint_queue)  # List of Waypoint dataclass instances
        }

    # =========================================================================
    # WIFI COMMANDS
    # =========================================================================

    def _register_wifi_commands(self):
        """Register WiFi commands for remote position control"""

        # Configuration
        self.communication.wifi.newCommand(
            identifier='position_control_set_config',
            function=self._wifi_set_config,
            arguments=['config'],
            description='Set position control configuration'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_get_config',
            function=lambda: dataclasses.asdict(self._config),
            arguments=[],
            description='Get position control configuration'
        )

        # Waypoint management
        self.communication.wifi.newCommand(
            identifier='position_control_clear_waypoints',
            function=self.clear_waypoints,
            arguments=[],
            description='Clear all waypoints'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_add_waypoint',
            function=self._wifi_add_waypoint,
            arguments=[
                'x', 'y',
                CommandArgument(name='type', type=int, optional=True, default=0),
                CommandArgument(name='weight', type=float, optional=True, default=0.75),
                CommandArgument(name='speed', type=float, optional=True, default=0.0)
            ],
            description='Add a waypoint (type: 0=PASS, 1=STOP, speed: 0=use path default)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_set_waypoints',
            function=self._wifi_set_waypoints,
            arguments=['waypoints'],
            description='Set multiple waypoints at once (clears existing)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_get_waypoints',
            function=self._wifi_get_waypoints,
            arguments=[],
            description='Get current waypoint list'
        )

        # Path control
        self.communication.wifi.newCommand(
            identifier='position_control_start_path',
            function=self._wifi_start_path,
            arguments=[
                CommandArgument(name='allow_reverse', type=bool, optional=True, default=False),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0),
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0)
            ],
            description='Start following the waypoint path'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_load_path',
            function=self._wifi_load_path,
            arguments=[
                'path',
                CommandArgument(name='start', type=bool, optional=True, default=False),
                CommandArgument(name='clear_existing', type=bool, optional=True, default=True),
            ],
            description='Load a path from dict (with optional start)'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_pause_path',
            function=self.pause_path,
            arguments=[],
            description='Pause path execution'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_resume_path',
            function=self.resume_path,
            arguments=[],
            description='Resume paused path'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_abort_path',
            function=self.abort_path,
            arguments=[],
            description='Abort path execution'
        )

        # Simple commands
        self.communication.wifi.newCommand(
            identifier='position_control_move_to',
            function=self._wifi_move_to,
            arguments=[
                'x', 'y',
                CommandArgument(name='max_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0)
            ],
            description='Move to a single point'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_turn_to',
            function=self._wifi_turn_to,
            arguments=[
                'heading',
                CommandArgument(name='max_angular_speed', type=float, optional=True, default=0.0),
                CommandArgument(name='timeout', type=float, optional=True, default=0.0)
            ],
            description='Turn to a heading (radians)'
        )

        # Status
        self.communication.wifi.newCommand(
            identifier='position_control_get_state',
            function=self.get_sample_dict,
            arguments=[],
            description='Get current position control state'
        )

        self.communication.wifi.newCommand(
            identifier='position_control_reset',
            function=self.reset,
            arguments=[],
            description='Reset position control'
        )

    def _wifi_set_config(self, config: dict) -> bool:
        """Set config from WiFi (dict input)"""
        try:
            cfg = from_dict_auto(PositionControl_Config, config)
            return self.set_config(cfg)
        except Exception as e:
            self.logger.error(f"Failed to parse config: {e}")
            return False

    def _wifi_add_waypoint(self, x: float, y: float, type: int = 0, weight: float = 0.75, speed: float = 0.0) -> bool:
        """Add waypoint from WiFi command"""
        wp_type = WaypointType(type) if type in [0, 1] else WaypointType.PASS
        return self.add_waypoint(Waypoint(x=x, y=y, type=wp_type, weight=weight, speed=speed))

    def _wifi_set_waypoints(self, waypoints: list[dict]) -> bool:
        """Set multiple waypoints from WiFi (clears existing first)"""
        if not self.clear_waypoints():
            return False

        for wp_dict in waypoints:
            x = wp_dict.get('x', 0.0)
            y = wp_dict.get('y', 0.0)
            wp_type = WaypointType(wp_dict.get('type', 0))
            weight = wp_dict.get('weight', 0.75)
            speed = wp_dict.get('speed', 0.0)
            if not self.add_waypoint(Waypoint(x=x, y=y, type=wp_type, weight=weight, speed=speed)):
                return False
        return True

    def _wifi_get_waypoints(self) -> list[dict]:
        """Get waypoints as list of dicts for WiFi"""
        return [
            {'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'weight': wp.weight, 'speed': wp.speed}
            for wp in self._waypoint_queue
        ]

    def _wifi_start_path(self, allow_reverse: bool = False, timeout: float = 0.0, max_speed: float = 0.0) -> bool:
        """Start path from WiFi command"""
        return self.start_path(allow_reverse=allow_reverse, timeout=timeout, max_speed=max_speed)

    def _wifi_load_path(self, path: dict, start: bool = False, clear_existing: bool = True) -> bool:
        """Load path from WiFi command"""
        return self.load_path(path_data=path, start=start, clear_existing=clear_existing)

    def _wifi_move_to(self, x: float, y: float, max_speed: float = 0.0, timeout: float = 0.0) -> bool:
        """Move to point from WiFi command"""
        return self.move_to_point(x=x, y=y, max_speed=max_speed, timeout=timeout)

    def _wifi_turn_to(self, heading: float, max_angular_speed: float = 0.0, timeout: float = 0.0) -> bool:
        """Turn to heading from WiFi command"""
        return self.turn_to_heading(heading=heading, max_angular_speed=max_angular_speed, timeout=timeout)

    # =========================================================================
    # WIFI EVENT EMISSION
    # =========================================================================

    _WIFI_FLAGS = {'group': 'position_control'}

    def _common_event_data(self, **extra) -> dict:
        """Build common event data dict, optionally merged with extra fields."""
        data = dataclasses.asdict(PositionControlCommonData(
            mode=self._mode.value,
            mode_name=self._mode.name,
            path_state=self._path_state.value,
            waypoint_count=len(self._waypoint_queue),
            current_waypoint_index=self._current_waypoint_index,
        ))
        if extra:
            data.update(extra)
        return data
