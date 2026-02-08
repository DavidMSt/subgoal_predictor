"""
BILBO Position Control (Host Side)

Host-side interface to the position control subsystem on the robot.
Receives events via WiFi and maintains a local representation of the controller state.
"""

import dataclasses
import enum
import json
import os

import yaml

from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals, wait_for_events, OR
from robots.bilbo.robot.bilbo_core import BILBO_Core


# =============================================================================
# ENUMS
# =============================================================================

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


class WaypointType(enum.IntEnum):
    """Waypoint arrival behavior"""
    PASS = 0  # Smooth transition, corner cutting allowed
    STOP = 1  # Must stop at this waypoint


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
    x: float
    y: float
    type: WaypointType = WaypointType.PASS
    weight: float = 0.75
    speed: float = 0.0


@dataclasses.dataclass
class PositionControlState:
    """Current state of the position controller"""
    mode: PositionControlMode = PositionControlMode.IDLE
    path_state: PathState = PathState.IDLE
    waypoint_count: int = 0
    current_waypoint_index: int = 0
    is_busy: bool = False


@dataclasses.dataclass
class MoveToPointCommand:
    """Data for active move_to_point command"""
    x: float = 0.0
    y: float = 0.0
    max_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


@dataclasses.dataclass
class TurnToHeadingCommand:
    """Data for active turn_to_heading command"""
    heading: float = 0.0
    heading_deg: float = 0.0
    max_angular_speed: float = 0.0
    timeout: float = 0.0
    active: bool = False


@dataclasses.dataclass
class PathData:
    """Data for loaded/active path"""
    waypoints: list[Waypoint] = dataclasses.field(default_factory=list)
    max_speed: float = 0.0
    allow_reverse: bool = False
    timeout: float = 0.0


# =============================================================================
# EVENTS AND CALLBACKS
# =============================================================================

@event_definition
class PositionControlEvents:
    """Events from the position controller"""
    # Path events - data contains PathData for visualization
    path_loaded: Event = Event(copy_data_on_set=False)
    path_started: Event = Event(copy_data_on_set=False)
    path_paused: Event
    path_resumed: Event
    path_finished: Event
    path_aborted: Event
    path_timeout: Event

    # Waypoint events - data contains waypoint info dict
    waypoint_passed: Event = Event(copy_data_on_set=False)
    waypoint_reached: Event = Event(copy_data_on_set=False)
    waypoint_completed: Event = Event(copy_data_on_set=False)

    # Buffer events
    waypoint_buffer_full: Event

    # Single-point command events - data contains command info
    move_to_point_started: Event = Event(copy_data_on_set=False)
    move_to_point_completed: Event
    move_to_point_timeout: Event
    turn_to_heading_started: Event = Event(copy_data_on_set=False)
    turn_to_heading_completed: Event
    turn_to_heading_timeout: Event

    # Mode change
    mode_changed: Event = Event(flags=EventFlag('mode', PositionControlMode))

    # State update (emitted on any event)
    state_updated: Event


@callback_definition
class PositionControlCallbacks:
    """Callbacks for position control events"""
    path_loaded: CallbackContainer
    path_started: CallbackContainer
    path_finished: CallbackContainer
    path_timeout: CallbackContainer
    path_aborted: CallbackContainer
    waypoint_completed: CallbackContainer
    move_to_point_started: CallbackContainer
    move_to_point_completed: CallbackContainer
    turn_to_heading_started: CallbackContainer
    turn_to_heading_completed: CallbackContainer
    mode_changed: CallbackContainer
    state_updated: CallbackContainer


# =============================================================================
# MAIN CLASS
# =============================================================================

class BILBO_PositionControl:
    """
    Host-side interface to robot's position control subsystem.

    Receives events via WiFi and maintains local state.
    Provides methods to send commands to the robot.
    """

    def __init__(self, core: BILBO_Core):
        self.id = core.id
        self.device = core.device
        self.logger = core.logger
        self.core = core

        self.events = PositionControlEvents()
        self.callbacks = PositionControlCallbacks()

        # Local state
        self._state = PositionControlState()
        self._waypoints: list[Waypoint] = []

        # Track active commands for visualization
        self._current_move_to_point = MoveToPointCommand()
        self._current_turn_to_heading = TurnToHeadingCommand()
        self._current_path = PathData()

        # Track top-level control mode for waypoint validation
        self._top_level_control_mode = None

        # Subscribe to position_control events from robot
        self.device.events.event.on(
            callback=self._handle_event,
            predicate=pred_flag_equals('container', 'position_control'),
        )

        # Subscribe to top-level control mode changes to sync waypoint list
        self.core.events.control_mode_changed.on(
            callback=self._on_control_mode_change
        )

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def mode(self) -> PositionControlMode:
        """Current position control mode"""
        return self._state.mode

    @property
    def path_state(self) -> PathState:
        """Current path execution state"""
        return self._state.path_state

    @property
    def waypoint_count(self) -> int:
        """Number of waypoints in queue"""
        return self._state.waypoint_count

    @property
    def current_waypoint_index(self) -> int:
        """Index of current target waypoint"""
        return self._state.current_waypoint_index

    @property
    def is_busy(self) -> bool:
        """True if executing any command"""
        return self._state.mode != PositionControlMode.IDLE

    @property
    def state(self) -> PositionControlState:
        """Current state snapshot"""
        return self._state

    @property
    def current_move_to_point(self) -> MoveToPointCommand | None:
        """Active move_to_point command, or None if not active"""
        return self._current_move_to_point if self._current_move_to_point.active else None

    @property
    def current_turn_to_heading(self) -> TurnToHeadingCommand | None:
        """Active turn_to_heading command, or None if not active"""
        return self._current_turn_to_heading if self._current_turn_to_heading.active else None

    @property
    def current_path(self) -> PathData | None:
        """Current path data, or None if no path is loaded"""
        return self._current_path if self._current_path.waypoints else None

    # =========================================================================
    # WAYPOINT MANAGEMENT
    # =========================================================================

    def clear_waypoints(self) -> bool:
        """Clear all waypoints on robot"""
        result = self.device.executeFunction(
            function_name='position_control_clear_waypoints',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self._waypoints.clear()
            self.logger.debug("Waypoints cleared")
        return result or False

    def add_waypoint(self, x: float, y: float,
                     type: WaypointType = WaypointType.PASS,
                     weight: float = 0.75,
                     speed: float = 0.0) -> bool:
        """Add a waypoint to the queue

        Args:
            x: World X coordinate [m]
            y: World Y coordinate [m]
            type: PASS (smooth transition) or STOP (must stop)
            weight: Corner sharpness [0-1], 1=sharp, 0=smooth
            speed: Max speed for this waypoint [m/s], 0=use path default
        """
        from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

        # Check if in POSITION mode - waypoints can only be added in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot add waypoints when not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        if isinstance(type, int):
            type = WaypointType(type)

        result = self.device.executeFunction(
            function_name='position_control_add_waypoint',
            arguments={'x': x, 'y': y, 'type': type.value, 'weight': weight, 'speed': speed},
            return_type=bool,
            request_response=True
        )
        if result:
            self._waypoints.append(Waypoint(x=x, y=y, type=type, weight=weight, speed=speed))
            self.logger.debug(f"Added waypoint ({x:.2f}, {y:.2f})" + (f" speed={speed:.2f}" if speed > 0 else ""))
        return result or False

    def set_waypoints(self, waypoints: list[dict | Waypoint]) -> bool:
        """
        Set multiple waypoints at once (clears existing).

        Args:
            waypoints: List of waypoints as dicts {'x': float, 'y': float, 'type': int, 'weight': float, 'speed': float}
                      or Waypoint objects
        """
        wp_list = []
        for wp in waypoints:
            if isinstance(wp, Waypoint):
                wp_list.append({'x': wp.x, 'y': wp.y, 'type': wp.type.value, 'weight': wp.weight, 'speed': wp.speed})
            else:
                wp_list.append(wp)

        result = self.device.executeFunction(
            function_name='position_control_set_waypoints',
            arguments={'waypoints': wp_list},
            return_type=bool,
            request_response=True
        )
        if result:
            self._waypoints = [
                Waypoint(x=wp['x'], y=wp['y'],
                         type=WaypointType(wp.get('type', 0)),
                         weight=wp.get('weight', 0.75),
                         speed=wp.get('speed', 0.0))
                for wp in wp_list
            ]
            self.logger.info(f"Set {len(wp_list)} waypoints")
        return result or False

    def get_waypoints(self) -> list[Waypoint]:
        """Get current waypoint list from robot"""
        result = self.device.executeFunction(
            function_name='position_control_get_waypoints',
            arguments=None,
            return_type=list,
            request_response=True
        )
        if result:
            self._waypoints = [
                Waypoint(x=wp['x'], y=wp['y'],
                         type=WaypointType(wp.get('type', 0)),
                         weight=wp.get('weight', 0.75),
                         speed=wp.get('speed', 0.0))
                for wp in result
            ]
        return self._waypoints.copy()

    # =========================================================================
    # PATH FOLLOWING
    # =========================================================================

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
        result = self.device.executeFunction(
            function_name='position_control_start_path',
            arguments={
                'allow_reverse': allow_reverse,
                'timeout': timeout,
                'max_speed': max_speed
            },
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info(f"Started path with {len(self._waypoints)} waypoints")
        return result or False

    def pause_path(self) -> bool:
        """Pause path execution"""
        result = self.device.executeFunction(
            function_name='position_control_pause_path',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info("Path paused")
        return result or False

    def resume_path(self) -> bool:
        """Resume paused path"""
        result = self.device.executeFunction(
            function_name='position_control_resume_path',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info("Path resumed")
        return result or False

    def abort_path(self) -> bool:
        """Abort path execution"""
        result = self.device.executeFunction(
            function_name='position_control_abort_path',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info("Path aborted")
        return result or False

    def load_path(self, path_data: dict, start: bool = False, clear_existing: bool = True) -> bool:
        """
        Load waypoints from a path dictionary and send to robot.

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

        Returns:
            True if path was loaded (and started if requested) successfully
        """
        result = self.device.executeFunction(
            function_name='position_control_load_path',
            arguments={
                'path': path_data,
                'start': start,
                'clear_existing': clear_existing
            },
            return_type=bool,
            request_response=True
        )
        if result:
            # Update local waypoint list from path_data
            waypoints_data = path_data.get('waypoints', [])
            self._waypoints = []
            for wp_data in waypoints_data:
                type_value = wp_data.get('type', 'PASS')
                if isinstance(type_value, str):
                    wp_type = WaypointType.STOP if type_value.upper() == 'STOP' else WaypointType.PASS
                else:
                    wp_type = WaypointType(int(type_value))
                self._waypoints.append(Waypoint(
                    x=wp_data['x'],
                    y=wp_data['y'],
                    type=wp_type,
                    weight=wp_data.get('weight', 0.75),
                    speed=wp_data.get('speed', 0.0)
                ))
            self.logger.info(f"Loaded path with {len(self._waypoints)} waypoints" +
                             (" and started" if start else ""))
        return result or False

    def load_path_from_file(self, filepath: str, start: bool = False, clear_existing: bool = True) -> bool:
        """
        Load waypoints from a JSON or YAML file and send to robot.

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

        Returns:
            True if path was loaded (and started if requested) successfully
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
        return self.load_path(path_data=path_data, start=start, clear_existing=clear_existing)

    # =========================================================================
    # SIMPLE COMMANDS
    # =========================================================================

    def move_to(self, x: float,
                y: float,
                max_speed: float = 0.0,
                timeout: float = 0.0,
                blocking: bool = False) -> bool:
        """
        Move to a single point.

        Args:
            x, y: Target position in world coordinates [m]
            max_speed: Maximum speed (0 = use default)
            timeout: Command timeout (0 = no timeout)
            blocking: If True, wait for completion before returning
        """

        self.logger.info(f"Moving to ({x:.2f}, {y:.2f})...")

        result = self.device.executeFunction(
            function_name='position_control_move_to',
            arguments={'x': x,
                       'y': y,
                       'max_speed': max_speed,
                       'timeout': timeout},
            return_type=bool,
            request_response=True
        )
        if not result:
            self.logger.warning(f"Failed to move to ({x:.2f}, {y:.2f})")
            return False

        if blocking:
            wait_timeout = (timeout + 5.0) if timeout > 0 else 60.0
            _, match = wait_for_events(
                OR(self.events.move_to_point_completed, self.events.move_to_point_timeout),
                timeout=wait_timeout,
            )
            if match is None:
                return False
            return match.caused_by(self.events.move_to_point_completed)

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to(self, heading: float,
                max_angular_speed: float = 0.0,
                timeout: float = 0.0,
                blocking: bool = False) -> bool:
        """
        Turn to a heading.

        Args:
            heading: Target heading [rad]
            max_angular_speed: Maximum turn rate (0 = use default)
            timeout: Command timeout (0 = no timeout)
            blocking: If True, wait for completion before returning
        """
        self.logger.info(f"Turning to {heading:.2f} rad...")

        result = self.device.executeFunction(
            function_name='position_control_turn_to',
            arguments={
                'heading': heading,
                'max_angular_speed': max_angular_speed,
                'timeout': timeout,
            },
            return_type=bool,
            request_response=True
        )

        if not result:
            self.logger.warning(f"Failed to turn to {heading:.2f} rad")
            return False

        if blocking:
            wait_timeout = (timeout + 5.0) if timeout > 0 else 60.0
            _, match = wait_for_events(
                OR(self.events.turn_to_heading_completed, self.events.turn_to_heading_timeout),
                timeout=wait_timeout,
            )
            if match is None:
                return False
            return match.caused_by(self.events.turn_to_heading_completed)

        return True

    # =========================================================================
    # STATE & CONFIG
    # =========================================================================

    def get_state(self) -> dict | None:
        """Get current position control state from robot"""
        result = self.device.executeFunction(
            function_name='position_control_get_state',
            arguments=None,
            return_type=dict,
            request_response=True
        )
        if result:
            self._update_state_from_dict(result)
        return result

    def get_config(self) -> dict | None:
        """Get position control configuration from robot"""
        return self.device.executeFunction(
            function_name='position_control_get_config',
            arguments=None,
            return_type=dict,
            request_response=True
        )

    def set_config(self, config: dict) -> bool:
        """Set position control configuration on robot"""
        result = self.device.executeFunction(
            function_name='position_control_set_config',
            arguments={'config': config},
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info("Position control config updated")
        return result or False

    def reset(self) -> bool:
        """Reset position control to idle state"""
        result = self.device.executeFunction(
            function_name='position_control_reset',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self._state = PositionControlState()
            self._waypoints.clear()
            self.logger.info("Position control reset")
        return result or False

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================

    def _handle_event(self, event_data, **kwargs):
        """Handle position control events from robot"""
        event_name = event_data.get('event', 'unknown')
        data = event_data.get('data', {}) or {}

        self.logger.debug(f"Position control event: {event_name}")
        self.logger.debug(f"Event data: {data}")

        # Update state from event data
        self._update_state_from_dict(data)

        # Emit corresponding local event
        match event_name:
            case 'path_loaded':
                # Parse and store path data
                path_data = self._parse_path_data(data)
                self._current_path = path_data
                self._waypoints = path_data.waypoints.copy()
                self.events.path_loaded.set(data=path_data)
                self.callbacks.path_loaded.call(path_data)

            case 'path_started':
                # Parse and store path data
                path_data = self._parse_path_data(data)
                self._current_path = path_data
                if path_data.waypoints:
                    self._waypoints = path_data.waypoints.copy()
                self.events.path_started.set(data=path_data)
                self.callbacks.path_started.call(path_data)

            case 'path_paused':
                self.events.path_paused.set()

            case 'path_resumed':
                self.events.path_resumed.set()

            case 'path_finished':
                self._waypoints.clear()
                self._current_path = PathData()
                self.events.path_finished.set()
                self.callbacks.path_finished.call()

            case 'path_timeout':
                self._waypoints.clear()
                self._current_path = PathData()
                self.events.path_timeout.set()
                self.callbacks.path_timeout.call()

            case 'path_aborted':
                self._waypoints.clear()
                self._current_path = PathData()
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()

            case 'waypoint_passed':
                idx = data.get('waypoint_index', 0)
                wp = self._parse_waypoint(data.get('waypoint'))
                self.events.waypoint_passed.set(data={'index': idx, 'waypoint': wp})

            case 'waypoint_reached':
                idx = data.get('waypoint_index', 0)
                wp = self._parse_waypoint(data.get('waypoint'))
                self.events.waypoint_reached.set(data={'index': idx, 'waypoint': wp})

            case 'waypoint_completed':
                idx = data.get('waypoint_index', 0)
                wp = self._parse_waypoint(data.get('waypoint'))
                next_wp = self._parse_waypoint(data.get('next_waypoint'))
                if self._waypoints:
                    self._waypoints.pop(0)
                self.events.waypoint_completed.set(data={'index': idx, 'waypoint': wp, 'next_waypoint': next_wp})
                self.callbacks.waypoint_completed.call(idx)

            case 'waypoint_buffer_full':
                self.logger.warning("Waypoint buffer full on robot")
                self.events.waypoint_buffer_full.set()

            case 'move_to_point_started':
                # Parse and store command data
                target = data.get('target', {})
                cmd = MoveToPointCommand(
                    x=target.get('x', 0.0),
                    y=target.get('y', 0.0),
                    max_speed=data.get('max_speed', 0.0),
                    timeout=data.get('timeout', 0.0),
                    active=True
                )
                self._current_move_to_point = cmd
                self.events.move_to_point_started.set(data=cmd)
                self.callbacks.move_to_point_started.call(cmd)

            case 'move_to_point_completed':
                target = data.get('target')
                self._current_move_to_point.active = False
                self.events.move_to_point_completed.set(data=target)
                self.callbacks.move_to_point_completed.call(target)

            case 'move_to_point_timeout':
                target = data.get('target')
                self._current_move_to_point.active = False
                self.events.move_to_point_timeout.set(data=target)

            case 'turn_to_heading_started':
                # Parse and store command data
                cmd = TurnToHeadingCommand(
                    heading=data.get('heading', 0.0),
                    heading_deg=data.get('heading_deg', 0.0),
                    max_angular_speed=data.get('max_angular_speed', 0.0),
                    timeout=data.get('timeout', 0.0),
                    active=True
                )
                self._current_turn_to_heading = cmd
                self.events.turn_to_heading_started.set(data=cmd)
                self.callbacks.turn_to_heading_started.call(cmd)

            case 'turn_to_heading_completed':
                target = {'heading': data.get('heading'), 'heading_deg': data.get('heading_deg')} if data.get(
                    'heading') is not None else None
                self._current_turn_to_heading.active = False
                self.events.turn_to_heading_completed.set(data=target)
                self.callbacks.turn_to_heading_completed.call(target)

            case 'turn_to_heading_timeout':
                target = {'heading': data.get('heading'), 'heading_deg': data.get('heading_deg')} if data.get(
                    'heading') is not None else None
                self._current_turn_to_heading.active = False
                self.events.turn_to_heading_timeout.set(data=target)

            case 'mode_changed':
                new_mode = PositionControlMode(data.get('new_mode', 0))
                self.events.mode_changed.set(flags={'mode': new_mode})
                self.callbacks.mode_changed.call(new_mode)

            case _:
                self.logger.debug(f"Unknown position control event: {event_name}")

        # Always emit state_updated
        self.events.state_updated.set()
        self.callbacks.state_updated.call()

    def _parse_waypoint(self, wp_data: dict | None) -> Waypoint | None:
        """Parse waypoint from event data"""
        if wp_data is None:
            return None
        type_value = wp_data.get('type', 0)
        if isinstance(type_value, str):
            wp_type = WaypointType.STOP if type_value.upper() == 'STOP' else WaypointType.PASS
        else:
            wp_type = WaypointType(int(type_value))
        return Waypoint(
            x=wp_data.get('x', 0.0),
            y=wp_data.get('y', 0.0),
            type=wp_type,
            weight=wp_data.get('weight', 0.75),
            speed=wp_data.get('speed', 0.0)
        )

    def _parse_path_data(self, data: dict) -> PathData:
        """Parse path data from event data"""
        waypoints = []
        for wp_data in data.get('waypoints', []):
            wp = self._parse_waypoint(wp_data)
            if wp:
                waypoints.append(wp)

        settings = data.get('settings', {})
        return PathData(
            waypoints=waypoints,
            max_speed=settings.get('max_speed', 0.0),
            allow_reverse=settings.get('allow_reverse', False),
            timeout=settings.get('timeout', 0.0)
        )

    def _update_state_from_dict(self, data: dict):
        """Update local state from event/response data"""
        if 'mode' in data:
            self._state.mode = PositionControlMode(data['mode'])
        if 'path_state' in data:
            self._state.path_state = PathState(data['path_state'])
        if 'waypoint_count' in data:
            self._state.waypoint_count = data['waypoint_count']
        if 'current_waypoint_index' in data:
            self._state.current_waypoint_index = data['current_waypoint_index']
        if 'is_busy' in data:
            self._state.is_busy = data['is_busy']

    def _on_control_mode_change(self, mode, *args, **kwargs):
        """Handle top-level control mode changes to sync waypoint list"""
        from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

        # Track top-level control mode
        self._top_level_control_mode = mode

        if mode == BILBO_Control_Mode.POSITION:
            # Entering POSITION mode: clear local state to sync with firmware
            # (firmware clears waypoints when entering POSITION mode)
            if self._waypoints:
                self.logger.debug("Entering POSITION mode, clearing local waypoint list to sync with robot")
            self._waypoints.clear()
            self._state = PositionControlState()
            self._current_path = PathData()
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
        else:
            # Leaving POSITION mode: clear state
            if self._waypoints:
                self.logger.debug(f"Control mode changed to {mode.name}, clearing local waypoint list")
            self._waypoints.clear()
            self._state = PositionControlState()
            self._current_path = PathData()
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
