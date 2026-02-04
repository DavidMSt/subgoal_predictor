"""
Experiment Actions Registry for Host-Side Validation

This module provides a declarative registry of experiment actions for the host side.
It enables pre-parsing and validation of experiment definitions before sending them
to the robot for execution.

Unlike the robot-side parser, this module:
- Does not create action instances (those are created on the robot)
- Focuses on validation and dict creation
- Provides introspection of available actions, parameters, and shorthands

Usage:
    # Parse and validate an experiment file
    parser = ExperimentParser()
    definition = parser.from_file("experiment.yaml")

    # Get validated dict to send to robot
    experiment_dict = definition.to_dict()

    # Introspect available actions
    registry = get_registry()
    for name in registry.type_names:
        entry = registry.get_entry(name)
        print(f"{name}: {entry.description}")
        for param in entry.parameters:
            print(f"  - {param.name}: {param.param_type.__name__}")
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any, Callable

import yaml

from core.utils.files import file_exists
from core.utils.logging_utils import Logger


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


def parse_control_mode(val: Any) -> str:
    """Parse and validate control mode, returning normalized string."""
    valid_modes = {'OFF', 'BALANCING', 'VELOCITY', 'DIRECT', 'POSITION'}

    if isinstance(val, str):
        mode_upper = val.upper()
        if mode_upper in valid_modes:
            return mode_upper
        raise ValueError(f"Invalid control mode: {val}. Valid modes: {valid_modes}")
    if isinstance(val, int):
        mode_map = {0: 'OFF', 1: 'DIRECT', 2: 'BALANCING', 3: 'VELOCITY', 4: 'POSITION'}
        if val in mode_map:
            return mode_map[val]
        raise ValueError(f"Invalid control mode value: {val}")
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
    """Normalize waypoints to list of dicts with x, y, type, weight, speed.

    Supported formats:
        - [x, y] - simple coordinate pair
        - [x, y, "STOP"] - with type
        - [x, y, weight] - with weight (float)
        - [x, y, "STOP", weight] - with type and weight
        - [x, y, "STOP", weight, speed] - with type, weight, and speed
        - {"x": x, "y": y, "type": "PASS", "weight": 0.75, "speed": 0.0} - full dict
    """
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
                normalized["speed"] = wp[4]
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
        name: Parameter name as used in YAML/dict
        param_type: Expected Python type (int, float, str, bool, list, dict)
        default: Default value if not provided
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

    def validate(self, raw_value: Any) -> tuple[bool, Any, str | None]:
        """Validate and convert a raw value for this parameter.

        Returns:
            Tuple of (is_valid, converted_value, error_message)
        """
        if raw_value is None:
            if self.required:
                return False, None, f"Required parameter '{self.name}' is missing"
            return True, self.default, None

        try:
            if self.converter is not None:
                return True, self.converter(raw_value), None

            # Basic type validation
            if self.param_type is not Any:
                if self.param_type is bool:
                    if isinstance(raw_value, bool):
                        return True, raw_value, None
                    if isinstance(raw_value, str):
                        return True, raw_value.lower() in ('true', 'yes', '1', 'on'), None
                    return True, bool(raw_value), None
                elif self.param_type is int:
                    return True, int(raw_value), None
                elif self.param_type is float:
                    return True, float(raw_value), None
                elif self.param_type is str:
                    return True, str(raw_value), None
                elif self.param_type is list and not isinstance(raw_value, list):
                    return False, None, f"Parameter '{self.name}' must be a list"
                elif self.param_type is dict and not isinstance(raw_value, dict):
                    return False, None, f"Parameter '{self.name}' must be a dict"

            return True, raw_value, None
        except (ValueError, TypeError) as e:
            return False, None, f"Cannot convert '{raw_value}' for parameter '{self.name}': {e}"


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
        value_converter: Optional converter for the shorthand value
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

    This class holds all the metadata needed for:
    1. Parsing the action from YAML/dict
    2. Expanding shorthands
    3. Validating parameters
    4. Generating documentation

    Attributes:
        type_name: The action type identifier (e.g., "beep", "set_mode")
        parameters: List of ActionParameter definitions
        shorthands: List of ShorthandRule definitions
        description: Human-readable description of the action
    """
    type_name: str
    parameters: list[ActionParameter] = dataclasses.field(default_factory=list)
    shorthands: list[ShorthandRule] = dataclasses.field(default_factory=list)
    description: str = ""

    def validate_parameters(self, raw_params: dict) -> tuple[bool, dict, list[str]]:
        """Validate raw parameters dict.

        Args:
            raw_params: Dict of parameter names to raw values

        Returns:
            Tuple of (is_valid, validated_params, error_messages)
        """
        result = {}
        errors = []

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

            is_valid, converted, error = param.validate(value)
            if not is_valid:
                errors.append(error)
            else:
                result[param.name] = converted

        return len(errors) == 0, result, errors

    def get_parameter_names(self) -> list[str]:
        """Get all parameter names including aliases."""
        names = []
        for param in self.parameters:
            names.append(param.name)
            names.extend(param.aliases)
        return names


# ======================================================================================================================
# Action Registry
# ======================================================================================================================

class ActionRegistry:
    """Registry of all available action types.

    This is a singleton that holds all ActionEntry definitions and provides
    methods for parsing, validation, and introspection.
    """

    def __init__(self):
        self._entries: dict[str, ActionEntry] = {}
        self._shorthands: dict[str, tuple[ActionEntry, ShorthandRule]] = {}
        self._string_shorthands: dict[str, tuple[ActionEntry, ShorthandRule]] = {}
        self.logger = Logger("ActionRegistry", "INFO")

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

    def validate_action(self, action_type: str, parameters: dict) -> tuple[bool, dict, list[str]]:
        """Validate action parameters.

        Returns:
            Tuple of (is_valid, validated_params, error_messages)
        """
        entry = self._entries.get(action_type)
        if entry is None:
            return False, {}, [f"Unknown action type: {action_type}"]

        return entry.validate_parameters(parameters)

    @property
    def type_names(self) -> list[str]:
        """Get list of all registered type names."""
        return list(self._entries.keys())

    @property
    def shorthand_keys(self) -> list[str]:
        """Get list of all registered shorthand keys."""
        return list(self._shorthands.keys())

    def get_action_info(self, type_name: str) -> dict | None:
        """Get information about an action type for documentation/introspection."""
        entry = self._entries.get(type_name)
        if entry is None:
            return None

        return {
            "type": entry.type_name,
            "description": entry.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.param_type.__name__ if hasattr(p.param_type, '__name__') else str(p.param_type),
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                    "aliases": p.aliases,
                }
                for p in entry.parameters
            ],
            "shorthands": [
                {
                    "key": s.key,
                    "string_shorthand": s.string_shorthand,
                    "value_key": s.value_key,
                }
                for s in entry.shorthands
            ],
        }


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
    expanding shorthands, validating parameters, and creating experiment dicts.
    """

    def __init__(self, registry: ActionRegistry | None = None, validate: bool = True, debug: bool = False):
        """Initialize the parser.

        Args:
            registry: Action registry to use (defaults to global registry)
            validate: If True, validate parameters during parsing
            debug: Enable debug logging
        """
        self.registry = registry or get_registry()
        self.validate = validate
        self.debug = debug
        self.logger = Logger("ExperimentParser", "DEBUG" if debug else "INFO")

    def from_file(self, filepath: str) -> dict:
        """Parse an experiment definition from a YAML or JSON file.

        Args:
            filepath: Path to the experiment file

        Returns:
            Parsed and validated experiment dict
        """
        if not file_exists(filepath):
            raise FileNotFoundError(f"Experiment file not found: {filepath}")

        with open(filepath, "r") as f:
            if filepath.lower().endswith((".yml", ".yaml")):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return self.from_dict(data)

    def from_dict(self, data: dict) -> dict:
        """Parse an experiment definition from a dict.

        Args:
            data: Dict containing experiment definition with 'id', 'description', 'actions'

        Returns:
            Parsed and validated experiment dict ready to send to robot
        """
        errors = []

        if "id" not in data:
            errors.append("Experiment definition requires an 'id'")
        if "description" not in data:
            errors.append("Experiment definition requires a 'description'")
        if "actions" not in data:
            errors.append("Experiment definition requires 'actions'")

        if errors:
            raise ValueError(f"Invalid experiment definition: {'; '.join(errors)}")

        raw_actions = data["actions"]
        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        parsed_actions = []
        all_errors = []

        for i, raw_action in enumerate(raw_actions):
            if self.debug:
                self.logger.debug(f"Parsing action {i}: {raw_action}")

            try:
                action_dict, action_errors = self.parse_action(raw_action, index=i)
                parsed_actions.append(action_dict)
                all_errors.extend(action_errors)
            except Exception as e:
                all_errors.append(f"Action {i}: {e}")

            if self.debug and action_errors:
                self.logger.debug(f"Validation errors for action {i}: {action_errors}")

        if all_errors and self.validate:
            raise ValueError(f"Experiment validation failed:\n  - " + "\n  - ".join(all_errors))

        return {
            "id": data["id"],
            "description": data["description"],
            "timeout": data.get("timeout"),
            "actions": parsed_actions,
        }

    def parse_action(self, data: dict | str, index: int = 0) -> tuple[dict, list[str]]:
        """Parse a single action definition.

        Args:
            data: Raw action data (dict or string shorthand)
            index: Action index for auto-generating IDs

        Returns:
            Tuple of (parsed_action_dict, validation_errors)
        """
        errors = []

        # Expand shorthands
        try:
            expanded = self.registry.expand_shorthand(data)
        except ValueError as e:
            return {"type": "unknown", "id": f"action_{index}"}, [str(e)]

        if "type" not in expanded:
            return expanded, [f"Action at index {index} missing required field 'type'"]

        action_type = expanded["type"]
        action_id = expanded.get("id", f"action_{index}")

        # Check if action type is known
        if not self.registry.has_type(action_type):
            errors.append(f"Unknown action type: {action_type}")

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "delay", "timeout", "parameters"}

        # Collect parameters
        if "parameters" in expanded:
            parameters = expanded["parameters"]
        else:
            parameters = {
                k: v for k, v in expanded.items()
                if k not in reserved_fields
            }

        # Validate parameters if validation is enabled and action type is known
        if self.validate and self.registry.has_type(action_type):
            is_valid, validated_params, param_errors = self.registry.validate_action(action_type, parameters)
            if not is_valid:
                errors.extend(param_errors)
            else:
                parameters = validated_params

        # Build result dict
        result = {
            "id": action_id,
            "type": action_type,
        }

        # Add scheduling fields
        for field in ["tick", "after", "time", "delay", "timeout"]:
            if field in expanded:
                result[field] = expanded[field]

        if parameters:
            result["parameters"] = parameters

        return result, errors

    def from_json(self, json_str: str) -> dict:
        """Parse an experiment definition from a JSON string."""
        data = json.loads(json_str)
        return self.from_dict(data)

    def validate_only(self, data: dict) -> tuple[bool, list[str]]:
        """Validate an experiment definition without raising exceptions.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        try:
            # Temporarily enable validation
            old_validate = self.validate
            self.validate = False  # Don't raise during parsing

            errors = []

            if "id" not in data:
                errors.append("Missing 'id'")
            if "description" not in data:
                errors.append("Missing 'description'")
            if "actions" not in data:
                errors.append("Missing 'actions'")
            elif not isinstance(data["actions"], list):
                errors.append("'actions' must be a list")
            else:
                for i, raw_action in enumerate(data["actions"]):
                    _, action_errors = self.parse_action(raw_action, index=i)
                    errors.extend(action_errors)

            self.validate = old_validate
            return len(errors) == 0, errors
        except Exception as e:
            return False, [str(e)]


# ======================================================================================================================
# Register Built-in Actions
# ======================================================================================================================

def _register_builtin_actions():
    """Register all built-in action types."""

    # === Basic Actions ===

    register_action(ActionEntry(
        type_name="beep",
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
        parameters=[
            ActionParameter("mode", str, converter=parse_control_mode, required=True),
        ],
        shorthands=[
            ShorthandRule("mode", value_key="mode"),
        ],
        description="Set the control mode"
    ))

    register_action(ActionEntry(
        type_name="set_tic",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable TIC control"
    ))

    register_action(ActionEntry(
        type_name="speak",
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
        parameters=[
            ActionParameter("marker_id", str, default=""),
            ActionParameter("marker_value", str, default=""),
        ],
        description="Set an experiment marker"
    ))

    register_action(ActionEntry(
        type_name="enable_external_input",
        parameters=[
            ActionParameter("enabled", bool, default=True),
        ],
        description="Enable/disable external input"
    ))

    register_action(ActionEntry(
        type_name="set_velocity",
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
        parameters=[],
        description="Reset robot state"
    ))

    register_action(ActionEntry(
        type_name="run_trajectory",
        parameters=[
            ActionParameter("input_trajectory", required=True),
        ],
        description="Run a trajectory"
    ))

    register_action(ActionEntry(
        type_name="set_input",
        parameters=[
            ActionParameter("input", list, default=[0.0, 0.0]),
            ActionParameter("normalized", bool, default=False),
        ],
        description="Set raw input"
    ))

    # === Wait Actions ===

    register_action(ActionEntry(
        type_name="wait_time",
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
        parameters=[
            ActionParameter("tick_target", int, default=0, aliases=["tick"]),
        ],
        description="Wait until a specific tick"
    ))

    register_action(ActionEntry(
        type_name="wait_event",
        parameters=[
            ActionParameter("event", str, default=""),
            ActionParameter("timeout", float, default=None),
        ],
        description="Wait for an event"
    ))

    # === Control Actions ===

    register_action(ActionEntry(
        type_name="parallel",
        parameters=[
            ActionParameter("sub_actions", list, default=[], aliases=["actions"]),
        ],
        shorthands=[
            ShorthandRule("parallel", value_key="actions"),
        ],
        description="Execute multiple actions in parallel"
    ))

    register_action(ActionEntry(
        type_name="func",
        parameters=[
            ActionParameter("function", str, default=""),
            ActionParameter("args", list, default=[]),
            ActionParameter("kwargs", dict, default={}),
        ],
        description="Execute a function on the robot"
    ))

    register_action(ActionEntry(
        type_name="set_feedback_gain",
        parameters=[
            ActionParameter("K", list, required=True),
        ],
        description="Set state feedback gain"
    ))

    register_action(ActionEntry(
        type_name="reset_control",
        parameters=[],
        description="Reset control parameters to defaults"
    ))

    # === Position Control Actions ===

    register_action(ActionEntry(
        type_name="move_to",
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
        parameters=[],
        shorthands=[
            ShorthandRule("stop_path", string_shorthand=True),
        ],
        description="Stop/abort the current path"
    ))

    register_action(ActionEntry(
        type_name="wait_position_event",
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

def parse_experiment_file(filepath: str, validate: bool = True, debug: bool = False) -> dict:
    """Parse an experiment from a file.

    Args:
        filepath: Path to YAML or JSON experiment file
        validate: Enable parameter validation
        debug: Enable debug logging

    Returns:
        Parsed experiment dict ready to send to robot
    """
    parser = ExperimentParser(validate=validate, debug=debug)
    return parser.from_file(filepath)


def parse_experiment_dict(data: dict, validate: bool = True, debug: bool = False) -> dict:
    """Parse an experiment from a dict.

    Args:
        data: Experiment definition dict
        validate: Enable parameter validation
        debug: Enable debug logging

    Returns:
        Parsed experiment dict ready to send to robot
    """
    parser = ExperimentParser(validate=validate, debug=debug)
    return parser.from_dict(data)


def validate_experiment(data: dict) -> tuple[bool, list[str]]:
    """Validate an experiment definition without raising exceptions.

    Args:
        data: Experiment definition dict

    Returns:
        Tuple of (is_valid, error_messages)
    """
    parser = ExperimentParser(validate=True)
    return parser.validate_only(data)


def get_available_actions() -> list[dict]:
    """Get information about all available actions.

    Returns:
        List of action info dicts for documentation/introspection
    """
    registry = get_registry()
    return [registry.get_action_info(name) for name in registry.type_names]


def get_action_info(action_type: str) -> dict | None:
    """Get information about a specific action type.

    Args:
        action_type: The action type name

    Returns:
        Action info dict or None if not found
    """
    return get_registry().get_action_info(action_type)
