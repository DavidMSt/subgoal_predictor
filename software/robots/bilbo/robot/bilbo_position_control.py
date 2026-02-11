"""
BILBO Position Control (Host Side)

Host-side interface to the position control subsystem on the robot.
Receives events via WiFi and maintains a local representation of the controller state.
"""

import base64
import dataclasses
import enum
import json
import os
import struct
import zlib

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


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclasses.dataclass
class PositionControlState:
    """Current state of the position controller"""
    mode: PositionControlMode = PositionControlMode.IDLE
    path_state: PathState = PathState.IDLE
    path_point_count: int = 0
    current_index: int = 0
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
    path_point_count: int = 0
    stop_indices: list[int] = dataclasses.field(default_factory=list)
    path_points: list[tuple[float, float]] = dataclasses.field(default_factory=list)
    waypoints: list[dict] = dataclasses.field(default_factory=list)
    max_speed: float = 0.0
    max_spacing: float = 0.0
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

    # Stop events - data contains stop index info
    stop_reached: Event = Event(copy_data_on_set=False)
    stop_completed: Event = Event(copy_data_on_set=False)

    # Buffer events
    path_buffer_full: Event

    # Single-point command events - data contains command info
    move_to_point_started: Event = Event(copy_data_on_set=False)
    move_to_point_completed: Event
    move_to_point_timeout: Event
    turn_to_heading_started: Event = Event(copy_data_on_set=False)
    turn_to_heading_completed: Event
    turn_to_heading_timeout: Event

    # Mode change
    mode_changed: Event = Event(flags=EventFlag('mode', PositionControlMode))

    # Planning events - data contains PlannedPathData for visualization
    path_planned: Event = Event(copy_data_on_set=False)
    path_cleared: Event

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
    stop_completed: CallbackContainer
    move_to_point_started: CallbackContainer
    move_to_point_completed: CallbackContainer
    turn_to_heading_started: CallbackContainer
    turn_to_heading_completed: CallbackContainer
    mode_changed: CallbackContainer
    path_planned: CallbackContainer
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

        # Track active commands for visualization
        self._current_move_to_point = MoveToPointCommand()
        self._current_turn_to_heading = TurnToHeadingCommand()
        self._current_path = PathData()

        # Track top-level control mode for validation
        self._top_level_control_mode = None

        # Subscribe to position_control events from robot
        self.device.events.event.on(
            callback=self._handle_event,
            predicate=pred_flag_equals('container', 'position_control'),
        )

        # Subscribe to top-level control mode changes to sync state
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
    def path_point_count(self) -> int:
        """Number of path points loaded"""
        return self._state.path_point_count

    @property
    def current_index(self) -> int:
        """Current path index"""
        return self._state.current_index

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
        return self._current_path if self._current_path.path_point_count > 0 else None

    # =========================================================================
    # PATH MANAGEMENT
    # =========================================================================

    def clear_path(self) -> bool:
        """Clear all path points on robot"""
        result = self.device.executeFunction(
            function_name='position_control_clear_path',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.debug("Path cleared")
        return result or False

    def add_path_point(self, x: float, y: float) -> bool:
        """Add a path point"""
        from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

        # Check if in POSITION mode
        if self._top_level_control_mode != BILBO_Control_Mode.POSITION:
            self.logger.warning(
                f"Cannot add path points when not in POSITION mode (current: "
                f"{self._top_level_control_mode.name if self._top_level_control_mode else 'None'})"
            )
            return False

        result = self.device.executeFunction(
            function_name='position_control_add_path_point',
            arguments={'x': x, 'y': y},
            return_type=bool,
            request_response=True
        )
        return result or False

    def add_stop_index(self, index: int) -> bool:
        """Mark a path point index as STOP"""
        result = self.device.executeFunction(
            function_name='position_control_add_stop_index',
            arguments={'index': int(index)},
            return_type=bool,
            request_response=True
        )
        return result or False

    def get_path_point_count(self) -> int:
        """Get current number of path points on robot"""
        result = self.device.executeFunction(
            function_name='position_control_get_path_point_count',
            arguments=None,
            return_type=int,
            request_response=True
        )
        if result is not None:
            self._state.path_point_count = result
        return self._state.path_point_count

    # =========================================================================
    # PATH FOLLOWING
    # =========================================================================

    def start_path(self, max_speed: float = 0.0,
                   max_spacing: float = 0.0,
                   timeout: float = 0.0,
                   allow_reverse: bool = False) -> bool:
        """
        Start following the loaded dense path.

        Args:
            max_speed: Speed override [m/s] (0 = use config default)
            max_spacing: Max inter-point spacing [m] (0 = auto-detect)
            timeout: Maximum time for path execution (0 = no timeout)
            allow_reverse: If True, robot may drive backwards when efficient
        """
        result = self.device.executeFunction(
            function_name='position_control_start_path',
            arguments={
                'max_speed': max_speed,
                'max_spacing': max_spacing,
                'timeout': timeout,
                'allow_reverse': allow_reverse
            },
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info(f"Started path")
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

    def stop_path(self) -> bool:
        """Stop and clear the current path (abort if running, then clear)"""
        result = self.device.executeFunction(
            function_name='position_control_stop_path',
            arguments=None,
            return_type=bool,
            request_response=True
        )
        if result:
            self.logger.info("Path stopped and cleared")
        return result or False

    def load_path(self, path_data: 'dict | list[tuple[float, float]]',
                  start: bool = False,
                  clear_existing: bool = True,
                  stop_indices: list[int] | None = None,
                  max_speed: float | None = None,
                  max_spacing: float | None = None,
                  allow_reverse: bool | None = None,
                  timeout: float | None = None) -> bool:
        """
        Load a dense path and send to robot.

        Accepts either:
        - A list of (x, y) tuples
        - A dict with path data and optional settings

        Args:
            path_data: Path as list of (x,y) tuples or dict with points and settings
            start: If True, automatically start the path after loading
            clear_existing: If True, clear existing path before loading
            stop_indices: Stop indices (used when path_data is a list; for dicts,
                can also be specified inside the dict)
            max_speed: Override for max_speed
            max_spacing: Override for max_spacing
            allow_reverse: Override for allow_reverse
            timeout: Override for timeout

        Returns:
            True if path was loaded (and started if requested) successfully
        """
        # Normalize: convert list of tuples to dict format for WiFi transmission
        if isinstance(path_data, list):
            local_points = [(float(pt[0]), float(pt[1])) for pt in path_data]
            wifi_data = {
                'points': [{'x': p[0], 'y': p[1]} for p in local_points],
            }
            if stop_indices:
                wifi_data['stop_indices'] = stop_indices
            if max_speed is not None:
                wifi_data['max_speed'] = max_speed
            if max_spacing is not None:
                wifi_data['max_spacing'] = max_spacing
            if allow_reverse is not None:
                wifi_data['allow_reverse'] = allow_reverse
            if timeout is not None:
                wifi_data['timeout'] = timeout
        elif isinstance(path_data, dict):
            wifi_data = dict(path_data)
            # Apply overrides
            if stop_indices is not None:
                wifi_data['stop_indices'] = stop_indices
            if max_speed is not None:
                wifi_data['max_speed'] = max_speed
            if max_spacing is not None:
                wifi_data['max_spacing'] = max_spacing
            if allow_reverse is not None:
                wifi_data['allow_reverse'] = allow_reverse
            if timeout is not None:
                wifi_data['timeout'] = timeout
            # Parse points for local storage
            pts = wifi_data.get('points', wifi_data.get('waypoints', []))
            local_points = []
            for pt in pts:
                if isinstance(pt, dict):
                    local_points.append((float(pt['x']), float(pt['y'])))
                else:
                    local_points.append((float(pt[0]), float(pt[1])))
        else:
            self.logger.error(f"path_data must be a list or dict, got {type(path_data).__name__}")
            return False

        result = self.device.executeFunction(
            function_name='position_control_load_path',
            arguments={
                'path': wifi_data,
                'start': start,
                'clear_existing': clear_existing
            },
            return_type=bool,
            request_response=True
        )
        if result:
            eff_stop_indices = wifi_data.get('stop_indices', [])
            self._current_path = PathData(
                path_point_count=len(local_points),
                stop_indices=[int(i) for i in eff_stop_indices],
                path_points=local_points,
                max_speed=float(wifi_data.get('max_speed', 0.0)),
                max_spacing=float(wifi_data.get('max_spacing', 0.0)),
                allow_reverse=bool(wifi_data.get('allow_reverse', False)),
                timeout=float(wifi_data.get('timeout', 0.0)),
            )
            self._state.path_point_count = len(local_points)
            self.logger.info(f"Loaded path with {len(local_points)} points" +
                             (" and started" if start else ""))
        return result or False

    def load_path_from_file(self, filepath: str, start: bool = False, clear_existing: bool = True) -> bool:
        """
        Load path from a JSON or YAML file and send to robot.

        Args:
            filepath: Path to .json or .yaml/.yml file
            start: If True, automatically start the path after loading
            clear_existing: If True, clear existing path before loading

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
    # MOTION PLANNING + PATH FOLLOWING
    # =========================================================================

    def plan_and_follow(self,
                        target: tuple[float, float],
                        waypoints: list[dict | tuple] | None = None,
                        obstacles: list[dict] | None = None,
                        bounds: dict | tuple | None = None,
                        stop_indices: list[int] | None = None,
                        max_speed: float = 0.0,
                        max_spacing: float = 0.0,
                        timeout: float = 0.0,
                        allow_reverse: bool = False,
                        seed: int | None = None,
                        blocking: bool = False) -> bool:
        """
        Plan a collision-free path from the robot's current position to target,
        load it, and start following it. The motion planner runs on the robot.

        Args:
            target: (x, y) destination in world coordinates [m]
            waypoints: Intermediate points with proximity weights.
                Each entry is either:
                - (x, y) or (x, y, weight) tuple
                - {"x": ..., "y": ..., "weight": ...} dict
            obstacles: List of obstacle dicts:
                - {"type": "circle", "cx": ..., "cy": ..., "radius": ...}
                - {"type": "box", "cx": ..., "cy": ..., "width": ..., "height": ...}
            bounds: Workspace limits as dict or (x_min, x_max, y_min, y_max) tuple.
            stop_indices: Path point indices where the robot should pause.
            max_speed: Speed limit [m/s] (0 = use config default)
            max_spacing: Max inter-point spacing [m] (0 = auto-detect)
            timeout: Path timeout [s] (0 = no timeout)
            allow_reverse: Allow reverse driving
            seed: RNG seed for motion planner reproducibility
            blocking: If True, block until path finished or timeout

        Returns:
            True if path was planned, loaded, and started successfully
        """
        # Normalize target
        if isinstance(target, (list, tuple)):
            target_arg = {'x': float(target[0]), 'y': float(target[1])}
        elif isinstance(target, dict):
            target_arg = target
        else:
            self.logger.error(f"Invalid target format: {target}")
            return False

        # Normalize bounds for transmission
        bounds_arg = None
        if bounds is not None:
            if isinstance(bounds, (list, tuple)):
                bounds_arg = {
                    'x_min': float(bounds[0]), 'x_max': float(bounds[1]),
                    'y_min': float(bounds[2]), 'y_max': float(bounds[3]),
                }
            elif isinstance(bounds, dict):
                bounds_arg = bounds

        arguments = {
            'target': target_arg,
            'waypoints': waypoints,
            'obstacles': obstacles,
            'bounds': bounds_arg,
            'stop_indices': stop_indices,
            'max_speed': max_speed,
            'max_spacing': max_spacing,
            'timeout': timeout,
            'allow_reverse': allow_reverse,
            'seed': seed,
        }

        self.logger.info(
            f"Planning and following path to ({target_arg['x']:.2f}, {target_arg['y']:.2f})"
        )

        result = self.device.executeFunction(
            function_name='position_control_plan_and_follow',
            arguments=arguments,
            return_type=bool,
            request_response=True
        )

        if not result:
            self.logger.error("plan_and_follow failed on robot")
            return False

        if not blocking:
            return True

        # Block until path finishes, times out, or is aborted
        wait_timeout = timeout + 10.0 if timeout > 0 else 120.0
        _, match = wait_for_events(
            OR(self.events.path_finished, self.events.path_timeout, self.events.path_aborted),
            timeout=wait_timeout,
        )
        if match is None:
            self.logger.warning("plan_and_follow: wait expired")
            return False
        return match.caused_by(self.events.path_finished)

    def plan_path(self,
                  target: tuple[float, float],
                  waypoints: list[dict | tuple] | None = None,
                  obstacles: list[dict] | None = None,
                  bounds: dict | tuple | None = None,
                  seed: int | None = None) -> bool:
        """
        Plan a path from the robot's current position to target (preview only).
        Does NOT load or start the path. The robot emits a path_planned WiFi event
        with compressed path points, which is caught here and emitted as a local event.

        Args:
            target: (x, y) destination in world coordinates [m]
            waypoints: Intermediate points with proximity weights.
            obstacles: Extra obstacle dicts (merged with stored obstacles on robot).
            bounds: Workspace limits as dict or (x_min, x_max, y_min, y_max) tuple.
            seed: RNG seed for motion planner reproducibility

        Returns:
            True if path was planned successfully
        """
        # Normalize target
        if isinstance(target, (list, tuple)):
            target_arg = {'x': float(target[0]), 'y': float(target[1])}
        elif isinstance(target, dict):
            target_arg = target
        else:
            self.logger.error(f"Invalid target format: {target}")
            return False

        # Normalize bounds
        bounds_arg = None
        if bounds is not None:
            if isinstance(bounds, (list, tuple)):
                bounds_arg = {
                    'x_min': float(bounds[0]), 'x_max': float(bounds[1]),
                    'y_min': float(bounds[2]), 'y_max': float(bounds[3]),
                }
            elif isinstance(bounds, dict):
                bounds_arg = bounds

        self.logger.info(
            f"Planning path to ({target_arg['x']:.2f}, {target_arg['y']:.2f}) (preview)"
        )

        result = self.device.executeFunction(
            function_name='position_control_plan_path',
            arguments={
                'target': target_arg,
                'waypoints': waypoints,
                'obstacles': obstacles,
                'bounds': bounds_arg,
                'seed': seed,
            },
            return_type=bool,
            request_response=True
        )

        if not result:
            self.logger.error("plan_path failed on robot")
            return False

        return True

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
            self._current_path = PathData()
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
                self._state.path_point_count = path_data.path_point_count
                self.events.path_loaded.set(data=path_data)
                self.callbacks.path_loaded.call(path_data)

            case 'path_started':
                # Parse and store path data
                path_data = self._parse_path_data(data)
                if path_data.path_point_count > 0:
                    self._current_path = path_data
                self.events.path_started.set(data=path_data)
                self.callbacks.path_started.call(path_data)

            case 'path_paused':
                self.events.path_paused.set()

            case 'path_resumed':
                self.events.path_resumed.set()

            case 'path_finished':
                self._current_path = PathData()
                self.events.path_finished.set()
                self.callbacks.path_finished.call()

            case 'path_timeout':
                self._current_path = PathData()
                self.events.path_timeout.set()
                self.callbacks.path_timeout.call()

            case 'path_aborted':
                self._current_path = PathData()
                self.events.path_aborted.set()
                self.callbacks.path_aborted.call()

            case 'path_planned':
                # Preview-only path from motion planner
                path_data = self._parse_path_data(data)
                self.events.path_planned.set(data=path_data)
                self.callbacks.path_planned.call(path_data)

            case 'path_cleared':
                self._current_path = PathData()
                self.events.path_cleared.set()

            case 'stop_reached':
                idx = data.get('stop_index', 0)
                self.events.stop_reached.set(data={'index': idx})

            case 'stop_completed':
                idx = data.get('stop_index', 0)
                self.events.stop_completed.set(data={'index': idx})
                self.callbacks.stop_completed.call(idx)

            case 'path_buffer_full':
                self.logger.warning("Path buffer full on robot")
                self.events.path_buffer_full.set()

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

    def _parse_path_data(self, data: dict) -> PathData:
        """Parse path data from event data, including compressed path points."""
        settings = data.get('settings', {})

        # Decompress path points if present
        path_points = []
        compressed = data.get('path_points_compressed')
        if compressed:
            try:
                path_points = self._decompress_path_points(compressed)
            except Exception as e:
                self.logger.warning(f"Failed to decompress path points: {e}")

        return PathData(
            path_point_count=data.get('path_point_count', 0),
            stop_indices=data.get('stop_indices', []),
            path_points=path_points,
            waypoints=data.get('waypoints') or [],
            max_speed=settings.get('max_speed', 0.0),
            max_spacing=settings.get('max_spacing', 0.0),
            allow_reverse=settings.get('allow_reverse', False),
            timeout=settings.get('timeout', 0.0)
        )

    @staticmethod
    def _decompress_path_points(compressed: str) -> list[tuple[float, float]]:
        """Decompress base64+zlib compressed path points back to list of (x, y) tuples."""
        raw = zlib.decompress(base64.b64decode(compressed))
        n_floats = len(raw) // 4
        values = struct.unpack(f'<{n_floats}f', raw)
        return [(values[i], values[i + 1]) for i in range(0, n_floats, 2)]

    def _update_state_from_dict(self, data: dict):
        """Update local state from event/response data"""
        if 'mode' in data:
            self._state.mode = PositionControlMode(data['mode'])
        if 'path_state' in data:
            self._state.path_state = PathState(data['path_state'])
        if 'path_point_count' in data:
            self._state.path_point_count = data['path_point_count']
        if 'current_index' in data:
            self._state.current_index = data['current_index']
        if 'is_busy' in data:
            self._state.is_busy = data['is_busy']

    def _on_control_mode_change(self, mode, *args, **kwargs):
        """Handle top-level control mode changes to sync state"""
        from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode

        # Track top-level control mode
        self._top_level_control_mode = mode

        if mode == BILBO_Control_Mode.POSITION:
            # Entering POSITION mode: clear local state to sync with firmware
            self._state = PositionControlState()
            self._current_path = PathData()
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
        else:
            # Leaving POSITION mode: clear state
            self._state = PositionControlState()
            self._current_path = PathData()
            self._current_move_to_point = MoveToPointCommand()
            self._current_turn_to_heading = TurnToHeadingCommand()
