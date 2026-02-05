"""
Experiment Parser Module

This module provides a declarative way to define experiment actions with their
parameters, shorthands, and parsing logic. It makes adding new actions simple
by just defining an ActionEntry with the action class and its parameters.

Usage:
    # Register a new action
    register_action(ActionEntry(
        type_name="my_action",
        action_class=MyAction,
        parameters=[
            ActionParameter("param1", int, default=0),
            ActionParameter("param2", str, required=True),
        ],
        shorthands=[
            ShorthandRule("my_shorthand", {"type": "my_action", "param1": "@value"})
        ]
    ))

    # Parse an experiment
    parser = ExperimentParser()
    definition = parser.from_file("experiment.yaml")
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any, Callable, TYPE_CHECKING

import yaml

from core.utils.files import file_exists
from core.utils.logging_utils import Logger

if TYPE_CHECKING:
    from robot.experiment.experiment import ExperimentAction, ExperimentActionDefinition


# ======================================================================================================================
# Parameter Types and Converters
# ======================================================================================================================

def parse_time_ms(val: Any) -> int:
    """Parse time value to milliseconds.

    Supports:
    - '2s' or '2.5s' -> seconds to milliseconds
    - '500ms' -> milliseconds
    - 2.0 (float) -> interpreted as seconds
    - 2000 (int) -> interpreted as milliseconds
    """
    if isinstance(val, float):
        return int(val * 1000)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("ms"):
            return int(float(val[:-2]))
        if val.endswith("s"):
            return int(float(val[:-1]) * 1000)
        num = float(val)
        if '.' in val:
            return int(num * 1000)
        else:
            return int(num)
    raise ValueError(f"Invalid time format: {val}")


def parse_control_mode(val: Any) -> Any:
    """Parse control mode from string, int, or enum."""
    from robot.control.bilbo_control_definitions import BILBO_Control_Mode

    if isinstance(val, BILBO_Control_Mode):
        return val
    if isinstance(val, int):
        return BILBO_Control_Mode(val)
    if isinstance(val, str):
        mode_upper = val.upper()
        mode_map = {
            'OFF': BILBO_Control_Mode.OFF,
            'BALANCING': BILBO_Control_Mode.BALANCING,
            'VELOCITY': BILBO_Control_Mode.VELOCITY,
            'DIRECT': BILBO_Control_Mode.DIRECT,
            'POSITION': BILBO_Control_Mode.POSITION,
        }
        if mode_upper in mode_map:
            return mode_map[mode_upper]
        raise ValueError(f"Invalid control mode: {val}")
    raise ValueError(f"Invalid control mode type: {type(val)}")


def parse_heading(val: Any) -> float:
    """Parse heading, converting degrees to radians if specified."""
    if isinstance(val, dict):
        if 'deg' in val:
            return math.radians(float(val['deg']))
        if 'rad' in val:
            return float(val['rad'])
    return float(val)


def normalize_waypoints(waypoints: list) -> list[dict]:
    """Normalize waypoints to list of dicts with x, y, type, weight, speed."""
    result = []
    for wp in waypoints:
        if isinstance(wp, dict):
            normalized = {
                "x": wp.get("x", 0.0),
                "y": wp.get("y", 0.0),
                "type": wp.get("type", "PASS"),
                "weight": wp.get("weight", 0.75),
                "speed": wp.get("speed", 0.0),
            }
        elif isinstance(wp, (list, tuple)):
            if len(wp) < 2:
                raise ValueError(f"Waypoint must have at least x, y: {wp}")
            normalized = {"x": wp[0], "y": wp[1], "type": "PASS", "weight": 0.75, "speed": 0.0}
            if len(wp) >= 3:
                if isinstance(wp[2], str):
                    normalized["type"] = wp[2].upper()
                else:
                    normalized["weight"] = wp[2]
            if len(wp) >= 4:
                if isinstance(wp[2], str):
                    normalized["weight"] = wp[3]
                else:
                    normalized["type"] = wp[3].upper() if isinstance(wp[3], str) else "PASS"
            if len(wp) >= 5:
                # 5th element is speed
                normalized["speed"] = float(wp[4])
        else:
            raise ValueError(f"Invalid waypoint format: {wp}")
        result.append(normalized)
    return result


# ======================================================================================================================
# Action Parameter Definition
# ======================================================================================================================

@dataclasses.dataclass
class ActionParameter:
    """Defines a parameter for an experiment action.

    Attributes:
        name: Parameter name as used in YAML/dict and action class
        param_type: Expected Python type (int, float, str, bool, list, dict)
        default: Default value if not provided (None means required)
        required: Whether the parameter is required
        description: Human-readable description
        converter: Optional function to convert/validate the value
        aliases: Alternative names for this parameter in the input
    """
    name: str
    param_type: type = Any
    default: Any = None
    required: bool = False
    description: str = ""
    converter: Callable[[Any], Any] | None = None
    aliases: list[str] = dataclasses.field(default_factory=list)

    def parse_value(self, raw_value: Any) -> Any:
        """Parse and validate a raw value for this parameter."""
        if raw_value is None:
            if self.required:
                raise ValueError(f"Required parameter '{self.name}' is missing")
            return self.default

        if self.converter is not None:
            return self.converter(raw_value)

        # Basic type coercion
        if self.param_type is not Any:
            try:
                if self.param_type is bool:
                    if isinstance(raw_value, bool):
                        return raw_value
                    if isinstance(raw_value, str):
                        return raw_value.lower() in ('true', 'yes', '1', 'on')
                    return bool(raw_value)
                elif self.param_type is int:
                    return int(raw_value)
                elif self.param_type is float:
                    return float(raw_value)
                elif self.param_type is str:
                    return str(raw_value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Cannot convert '{raw_value}' to {self.param_type.__name__} for parameter '{self.name}'") from e

        return raw_value


# ======================================================================================================================
# Shorthand Rule Definition
# ======================================================================================================================

@dataclasses.dataclass
class ShorthandRule:
    """Defines a shorthand expansion rule.

    Shorthands allow concise YAML syntax like:
        - beep
        - wait: 2s
        - mode: BALANCING

    Attributes:
        key: The shorthand key (e.g., "wait", "mode", "beep")
        expansion: Either a dict template or a callable that returns a dict
        string_shorthand: If True, this can be used as a bare string (e.g., "beep")
        value_key: If set, the shorthand value goes into this parameter
    """
    key: str
    expansion: dict | Callable[[Any], dict] | None = None
    string_shorthand: bool = False
    value_key: str | None = None
    value_converter: Callable[[Any], Any] | None = None

    def expand(self, value: Any = None) -> dict:
        """Expand the shorthand into a full action dict."""
        if callable(self.expansion):
            return self.expansion(value)

        if self.expansion is not None:
            result = dict(self.expansion)
            if self.value_key and value is not None:
                if self.value_converter:
                    value = self.value_converter(value)
                result[self.value_key] = value
            return result

        # Default: just set the type
        return {"type": self.key}


# ======================================================================================================================
# Action Entry Definition
# ======================================================================================================================

@dataclasses.dataclass
class ActionEntry:
    """Complete definition of an experiment action type.

    This class holds all the metadata needed to:
    1. Parse the action from YAML/dict
    2. Expand shorthands
    3. Create action instances
    4. Validate parameters

    Attributes:
        type_name: The action type identifier (e.g., "beep", "set_mode")
        action_class: The ExperimentAction subclass to instantiate
        parameters: List of ActionParameter definitions
        shorthands: List of ShorthandRule definitions
        description: Human-readable description of the action
    """
    type_name: str
    action_class: type[ExperimentAction]
    parameters: list[ActionParameter] = dataclasses.field(default_factory=list)
    shorthands: list[ShorthandRule] = dataclasses.field(default_factory=list)
    description: str = ""

    def parse_parameters(self, raw_params: dict) -> dict:
        """Parse raw parameters dict into validated parameters.

        Args:
            raw_params: Dict of parameter names to raw values

        Returns:
            Dict of parameter names to parsed/validated values
        """
        result = {}

        for param in self.parameters:
            # Check for value under main name or aliases
            value = None
            found = False

            if param.name in raw_params:
                value = raw_params[param.name]
                found = True
            else:
                for alias in param.aliases:
                    if alias in raw_params:
                        value = raw_params[alias]
                        found = True
                        break

            if not found:
                value = None

            result[param.name] = param.parse_value(value)

        return result

    def create_action(self, definition: ExperimentActionDefinition) -> ExperimentAction:
        """Create an action instance from a definition.

        Args:
            definition: The ExperimentActionDefinition with parsed parameters

        Returns:
            An instance of the action class
        """
        # Parse parameters
        parsed_params = self.parse_parameters(definition.parameters)

        # Build kwargs for action constructor
        kwargs = {
            "id": definition.id,
            "tick": definition.tick,
            "after": definition.after,
            "time": definition.time,
            "timeout": definition.timeout,
        }
        kwargs.update(parsed_params)

        return self.action_class(**kwargs)


# ======================================================================================================================
# Action Registry
# ======================================================================================================================

class ActionRegistry:
    """Registry of all available action types.

    This is a singleton that holds all ActionEntry definitions and provides
    methods for parsing and creating actions.
    """

    def __init__(self):
        self._entries: dict[str, ActionEntry] = {}
        self._shorthands: dict[str, tuple[ActionEntry, ShorthandRule]] = {}
        self._string_shorthands: dict[str, tuple[ActionEntry, ShorthandRule]] = {}
        self.logger = Logger("ActionRegistry", "DEBUG")

    def register(self, entry: ActionEntry) -> None:
        """Register an action entry."""
        if entry.type_name in self._entries:
            self.logger.warning(f"Overwriting existing action entry: {entry.type_name}")

        self._entries[entry.type_name] = entry

        # Register shorthands
        for shorthand in entry.shorthands:
            self._shorthands[shorthand.key] = (entry, shorthand)
            if shorthand.string_shorthand:
                self._string_shorthands[shorthand.key] = (entry, shorthand)

    def get_entry(self, type_name: str) -> ActionEntry | None:
        """Get an action entry by type name."""
        return self._entries.get(type_name)

    def has_type(self, type_name: str) -> bool:
        """Check if a type is registered."""
        return type_name in self._entries

    def expand_shorthand(self, data: dict | str) -> dict:
        """Expand shorthand syntax to full action dict.

        Args:
            data: Either a string shorthand (e.g., "beep") or a dict

        Returns:
            Full action dict with 'type' key
        """
        # Handle string shorthand
        if isinstance(data, str):
            if data in self._string_shorthands:
                entry, rule = self._string_shorthands[data]
                result = rule.expand()
                result.setdefault("type", entry.type_name)
                return result
            raise ValueError(f"Unknown string shorthand: {data}")

        # Already has type - no expansion needed
        if "type" in data:
            return data

        # Check for shorthand keys
        expanded = dict(data)
        for key in list(expanded.keys()):
            if key in self._shorthands:
                entry, rule = self._shorthands[key]
                value = expanded.pop(key)
                expansion = rule.expand(value)
                expansion.update(expanded)  # Preserve other fields
                expansion.setdefault("type", entry.type_name)
                return expansion

        return expanded

    def create_action(self, definition: ExperimentActionDefinition) -> ExperimentAction:
        """Create an action instance from a definition."""
        entry = self._entries.get(definition.type)
        if entry is None:
            raise ValueError(f"Unknown action type: {definition.type}")

        return entry.create_action(definition)

    @property
    def type_names(self) -> list[str]:
        """Get list of all registered type names."""
        return list(self._entries.keys())


# Global registry instance
_registry = ActionRegistry()


def get_registry() -> ActionRegistry:
    """Get the global action registry."""
    return _registry


def register_action(entry: ActionEntry) -> None:
    """Register an action entry in the global registry."""
    _registry.register(entry)


# ======================================================================================================================
# Experiment Parser
# ======================================================================================================================

class ExperimentParser:
    """Parser for experiment definitions.

    This class handles parsing experiments from YAML/JSON files or dicts,
    expanding shorthands, and creating ExperimentDefinition objects.
    """

    def __init__(self, registry: ActionRegistry | None = None, debug: bool = False):
        self.registry = registry or get_registry()
        self.debug = debug
        self.logger = Logger("ExperimentParser", "DEBUG" if debug else "INFO")

    def from_file(self, filepath: str):
        """Parse an experiment definition from a YAML or JSON file.

        Args:
            filepath: Path to the experiment file

        Returns:
            Parsed ExperimentDefinition
        """
        from robot.experiment.experiment import ExperimentDefinition

        if not file_exists(filepath):
            raise FileNotFoundError(f"Experiment file not found: {filepath}")

        with open(filepath, "r") as f:
            if filepath.lower().endswith((".yml", ".yaml")):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return self.from_dict(data)

    def from_dict(self, data: dict):
        """Parse an experiment definition from a dict.

        Args:
            data: Dict containing experiment definition with 'id', 'description', 'actions'

        Returns:
            Parsed ExperimentDefinition
        """
        from robot.experiment.experiment import ExperimentDefinition, ExperimentActionDefinition

        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]
        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        actions = []
        for i, raw_action in enumerate(raw_actions):
            if self.debug:
                self.logger.debug(f"Parsing action {i}: {raw_action}")

            action_def = self.parse_action(raw_action, index=i)
            actions.append(action_def)

            if self.debug:
                self.logger.debug(f"Parsed action {i}: type={action_def.type}, params={action_def.parameters}")

        return ExperimentDefinition(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
            external_input_enabled=data.get("external_input_enabled", False),
        )

    def parse_action(self, data: dict | str, index: int = 0):
        """Parse a single action definition.

        Args:
            data: Raw action data (dict or string shorthand)
            index: Action index for auto-generating IDs

        Returns:
            Parsed ExperimentActionDefinition
        """
        from robot.experiment.experiment import ExperimentActionDefinition

        # Expand shorthands
        expanded = self.registry.expand_shorthand(data)

        if "type" not in expanded:
            raise ValueError(f"Action at index {index} missing required field 'type': {expanded}")

        # Extract scheduling and reserved fields
        action_id = expanded.get("id", f"action_{index}")
        action_type = expanded["type"]

        reserved_fields = {"id", "type", "tick", "after", "time", "delay", "timeout", "parameters"}

        # Collect parameters
        if "parameters" in expanded:
            parameters = expanded["parameters"]
        else:
            parameters = {
                k: v for k, v in expanded.items()
                if k not in reserved_fields
            }

        return ExperimentActionDefinition(
            id=action_id,
            type=action_type,
            tick=expanded.get("tick"),
            after=expanded.get("after"),
            time=expanded.get("time"),
            delay=expanded.get("delay"),
            timeout=expanded.get("timeout"),
            parameters=parameters,
        )

    def from_json(self, json_str: str):
        """Parse an experiment definition from a JSON string."""
        data = json.loads(json_str)
        return self.from_dict(data)


# ======================================================================================================================
# Register Built-in Actions
# ======================================================================================================================

def _register_builtin_actions():
    """Register all built-in action types."""
    from robot.experiment.experiment import (
        BeepAction, SetModeAction, SetTICAction, SpeakAction, SetMarkerAction,
        EnableExternalInputAction, SetVelocityAction, ResetAction, RunTrajectoryAction,
        SetInputAction, WaitTimeAction, WaitTickAction, WaitUntilTickAction,
        WaitEventAction, ParallelAction, GroupAction, FuncAction, SetFeedbackGainAction,
        ResetControlAction, MoveToAction, TurnToAction, SetWaypointsAction,
        StartPathAction, LoadPathAction, StopPathAction, WaitPositionEventAction
    )

    # === Basic Actions ===

    register_action(ActionEntry(
        type_name="beep",
        action_class=BeepAction,
        parameters=[
            ActionParameter("frequency", int, default=1000),
            ActionParameter("time_ms", int, default=250),
            ActionParameter("repeats", int, default=1),
        ],
        shorthands=[
            ShorthandRule("beep", string_shorthand=True, value_key="frequency"),
        ],
        description="Play a beep sound"
    ))

    register_action(ActionEntry(
        type_name="set_mode",
        action_class=SetModeAction,
        parameters=[
            ActionParameter("mode", converter=parse_control_mode, required=True),
        ],
        shorthands=[
            ShorthandRule("mode", value_key="mode"),
        ],
        description="Set the control mode"
    ))

    register_action(ActionEntry(
        type_name="set_tic",
        action_class=SetTICAction,
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable TIC control"
    ))

    register_action(ActionEntry(
        type_name="speak",
        action_class=SpeakAction,
        parameters=[
            ActionParameter("text", str, default=""),
        ],
        shorthands=[
            ShorthandRule("speak", value_key="text"),
        ],
        description="Speak text using TTS"
    ))

    register_action(ActionEntry(
        type_name="set_marker",
        action_class=SetMarkerAction,
        parameters=[
            ActionParameter("marker_id", str, default=""),
            ActionParameter("marker_value", str, default=""),
        ],
        description="Set an experiment marker"
    ))

    register_action(ActionEntry(
        type_name="enable_external_input",
        action_class=EnableExternalInputAction,
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable external input"
    ))

    register_action(ActionEntry(
        type_name="set_velocity",
        action_class=SetVelocityAction,
        parameters=[
            ActionParameter("forward", float, default=0.0),
            ActionParameter("turn", float, default=0.0),
            ActionParameter("normalized", bool, default=False),
        ],
        shorthands=[
            ShorthandRule("velocity", expansion=lambda v: {
                "type": "set_velocity",
                "forward": v[0] if isinstance(v, list) and len(v) >= 1 else 0.0,
                "turn": v[1] if isinstance(v, list) and len(v) >= 2 else 0.0,
            }),
        ],
        description="Set velocity command"
    ))

    register_action(ActionEntry(
        type_name="reset",
        action_class=ResetAction,
        parameters=[],
        description="Reset robot state"
    ))

    register_action(ActionEntry(
        type_name="run_trajectory",
        action_class=RunTrajectoryAction,
        parameters=[
            ActionParameter("input_trajectory", required=True),
        ],
        description="Run a trajectory"
    ))

    register_action(ActionEntry(
        type_name="set_input",
        action_class=SetInputAction,
        parameters=[
            ActionParameter("input", list, default=[0.0, 0.0]),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set raw input"
    ))

    # === Wait Actions ===

    register_action(ActionEntry(
        type_name="wait_time",
        action_class=WaitTimeAction,
        parameters=[
            ActionParameter("time_ms", int, default=0, converter=parse_time_ms),
        ],
        shorthands=[
            ShorthandRule("wait", value_key="time_ms", value_converter=parse_time_ms),
        ],
        description="Wait for a specified time"
    ))

    register_action(ActionEntry(
        type_name="wait_ticks",
        action_class=WaitTickAction,
        parameters=[
            ActionParameter("ticks", int, default=0),
        ],
        shorthands=[
            ShorthandRule("wait_ticks", value_key="ticks"),
        ],
        description="Wait for a number of ticks"
    ))

    register_action(ActionEntry(
        type_name="wait_until_tick",
        action_class=WaitUntilTickAction,
        parameters=[
            ActionParameter("tick_target", int, default=0, aliases=["tick"]),
        ],
        description="Wait until a specific tick"
    ))

    register_action(ActionEntry(
        type_name="wait_event",
        action_class=WaitEventAction,
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("timeout", float, default=None),
        ],
        description="Wait for an event"
    ))

    # === Control Actions ===

    register_action(ActionEntry(
        type_name="parallel",
        action_class=ParallelAction,
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        shorthands=[
            ShorthandRule("parallel", value_key="actions"),
        ],
        description="Execute multiple actions in parallel"
    ))

    register_action(ActionEntry(
        type_name="group",
        action_class=GroupAction,
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        shorthands=[
            ShorthandRule("group", value_key="actions"),
        ],
        description="Execute multiple actions sequentially as a named group"
    ))

    register_action(ActionEntry(
        type_name="func",
        action_class=FuncAction,
        parameters=[
            ActionParameter("function", str, default=""),
            ActionParameter("args", list, default=[]),
            ActionParameter("kwargs", dict, default={}),
        ],
        description="Execute a function on the robot"
    ))

    register_action(ActionEntry(
        type_name="set_feedback_gain",
        action_class=SetFeedbackGainAction,
        parameters=[
            ActionParameter("K", list, required=True),
        ],
        description="Set state feedback gain"
    ))

    register_action(ActionEntry(
        type_name="reset_control",
        action_class=ResetControlAction,
        parameters=[],
        description="Reset control parameters to defaults"
    ))

    # === Position Control Actions ===

    register_action(ActionEntry(
        type_name="move_to",
        action_class=MoveToAction,
        parameters=[
            ActionParameter("x", float, default=0.0),
            ActionParameter("y", float, default=0.0),
            ActionParameter("max_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("wait", bool, default=True),
        ],
        shorthands=[
            ShorthandRule("move_to", expansion=lambda v: {
                "type": "move_to",
                "x": v[0] if isinstance(v, list) and len(v) >= 1 else (v.get("x", 0.0) if isinstance(v, dict) else 0.0),
                "y": v[1] if isinstance(v, list) and len(v) >= 2 else (v.get("y", 0.0) if isinstance(v, dict) else 0.0),
            }),
        ],
        description="Move to a position"
    ))

    register_action(ActionEntry(
        type_name="turn_to",
        action_class=TurnToAction,
        parameters=[
            ActionParameter("heading", float, default=0.0),
            ActionParameter("max_angular_speed", float, default=0.0),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("wait", bool, default=True),
        ],
        shorthands=[
            ShorthandRule("turn_to", expansion=lambda v: {
                "type": "turn_to",
                "heading": v if isinstance(v, (int, float)) else (v.get("heading", 0.0) if isinstance(v, dict) else 0.0),
            }),
        ],
        description="Turn to a heading"
    ))

    register_action(ActionEntry(
        type_name="set_waypoints",
        action_class=SetWaypointsAction,
        parameters=[
            ActionParameter("waypoints", list, default=[], converter=normalize_waypoints),
            ActionParameter("clear_existing", bool, default=True),
        ],
        shorthands=[
            ShorthandRule("waypoints", value_key="waypoints", value_converter=normalize_waypoints),
        ],
        description="Set waypoints for path following"
    ))

    register_action(ActionEntry(
        type_name="start_path",
        action_class=StartPathAction,
        parameters=[
            ActionParameter("allow_reverse", bool, default=False),
            ActionParameter("timeout", float, default=0.0),
            ActionParameter("max_speed", float, default=0.0),
            ActionParameter("wait", bool, default=True),
        ],
        description="Start following the loaded path"
    ))

    register_action(ActionEntry(
        type_name="load_path",
        action_class=LoadPathAction,
        parameters=[
            ActionParameter("path"),
            ActionParameter("start", bool, default=False),
            ActionParameter("clear_existing", bool, default=True),
            ActionParameter("allow_reverse", bool, default=None),
            ActionParameter("path_timeout", float, default=None, aliases=["timeout"]),
            ActionParameter("max_speed", float, default=None),
            ActionParameter("wait", bool, default=True),
        ],
        shorthands=[
            ShorthandRule("path", value_key="path"),
        ],
        description="Load a path from file or dict"
    ))

    register_action(ActionEntry(
        type_name="stop_path",
        action_class=StopPathAction,
        parameters=[],
        shorthands=[
            ShorthandRule("stop_path", string_shorthand=True),
        ],
        description="Stop/abort the current path"
    ))

    register_action(ActionEntry(
        type_name="wait_position_event",
        action_class=WaitPositionEventAction,
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("event_timeout", float, default=None, aliases=["timeout"]),
        ],
        description="Wait for a position control event"
    ))


# Initialize builtin actions when module is imported
_register_builtin_actions()


# ======================================================================================================================
# Convenience Functions
# ======================================================================================================================

def parse_experiment_file(filepath: str, debug: bool = False) -> ExperimentDefinition:
    """Parse an experiment from a file.

    Args:
        filepath: Path to YAML or JSON experiment file
        debug: Enable debug logging

    Returns:
        Parsed ExperimentDefinition
    """
    parser = ExperimentParser(debug=debug)
    return parser.from_file(filepath)


def parse_experiment_dict(data: dict, debug: bool = False) -> ExperimentDefinition:
    """Parse an experiment from a dict.

    Args:
        data: Experiment definition dict
        debug: Enable debug logging

    Returns:
        Parsed ExperimentDefinition
    """
    parser = ExperimentParser(debug=debug)
    return parser.from_dict(data)


# Re-export for convenience
ExperimentDefinition = None  # Will be set after import

def _setup_exports():
    """Set up module exports after circular imports are resolved."""
    global ExperimentDefinition
    from robot.experiment.experiment import ExperimentDefinition as ED
    ExperimentDefinition = ED

# Defer export setup
try:
    _setup_exports()
except ImportError:
    pass  # Will be set later when experiment module is imported
