"""
Experiment Definitions for BILBO Robot

This file defines the experiment action types and experiment definition structures.
It is designed to be kept in sync with the robot software implementation at:
  robots/bilbo/software/BILBO-Software/robot/experiment/bilbo_experiment.py

The host software uses these definitions to construct and serialize experiments,
which are then sent to the robot for execution.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any, Union, Literal

import numpy as np
import yaml

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.utils.json_utils import writeJSON, readJSON
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState, BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_CONTROL_DT, BILBO_Config, BILBO_ControlConfig


# ======================================================================================================================
# TIME PARSING
# ======================================================================================================================

def _parse_time(val) -> int:
    """Parse time value to milliseconds.

    Supports:
    - '2s' or '2.5s' -> seconds to milliseconds
    - '500ms' -> milliseconds
    - 2.0 (float) -> interpreted as seconds
    - 2000 (int) -> interpreted as milliseconds
    """
    if isinstance(val, float):
        # Floats are interpreted as seconds
        return int(val * 1000)
    if isinstance(val, int):
        # Integers are interpreted as milliseconds
        return val
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("ms"):
            return int(float(val[:-2]))
        if val.endswith("s"):
            return int(float(val[:-1]) * 1000)
        # Bare string number - try to be smart about it
        num = float(val)
        if '.' in val:
            # Has decimal point, treat as seconds
            return int(num * 1000)
        else:
            # Integer string, treat as milliseconds
            return int(num)
    raise ValueError(f"Invalid time format: {val}")


# ======================================================================================================================
# SHORTHAND EXPANSION
# ======================================================================================================================

def _expand_shorthand(d: dict | str) -> dict:
    """Expand shorthand action definitions to full format.

    Supports:
    - "beep" (string) -> type: beep
    - wait: "2s" or wait: 2000 -> type: wait_time
    - wait_ticks: 100 -> type: wait_ticks
    - mode: BALANCING -> type: set_mode
    - speak: "text" -> type: speak
    - beep or beep: 1000 -> type: beep
    - velocity: [0.5, 0.1] -> type: set_velocity
    - parallel: [...] -> type: parallel
    """
    # Handle string shorthand (e.g., "beep" as a bare string)
    if isinstance(d, str):
        if d == "beep":
            return {"type": "beep"}
        raise ValueError(f"Unknown string shorthand: {d}")

    # Already has 'type' - no expansion needed
    if "type" in d:
        return d

    expanded = dict(d)  # Copy to avoid mutation

    # wait: "2s" or wait: 2000 -> type: wait_time
    if "wait" in expanded:
        wait_val = expanded.pop("wait")
        expanded["type"] = "wait_time"
        expanded["time_ms"] = _parse_time(wait_val)
        return expanded

    # wait_ticks: 100 -> type: wait_ticks
    if "wait_ticks" in expanded:
        expanded["type"] = "wait_ticks"
        expanded["ticks"] = expanded.pop("wait_ticks")
        return expanded

    # mode: BALANCING -> type: set_mode
    if "mode" in expanded:
        expanded["type"] = "set_mode"
        return expanded

    # speak: "text" -> type: speak
    if "speak" in expanded:
        expanded["type"] = "speak"
        expanded["text"] = expanded.pop("speak")
        return expanded

    # beep or beep: 1000 -> type: beep
    if "beep" in expanded:
        expanded["type"] = "beep"
        beep_val = expanded.pop("beep")
        if beep_val is not None and beep_val is not True:
            expanded["frequency"] = beep_val
        return expanded

    # velocity: [0.5, 0.1] -> type: set_velocity
    if "velocity" in expanded:
        expanded["type"] = "set_velocity"
        vel = expanded.pop("velocity")
        if isinstance(vel, list) and len(vel) >= 2:
            expanded["forward"] = vel[0]
            expanded["turn"] = vel[1]
        return expanded

    # parallel: [...] -> type: parallel
    if "parallel" in expanded:
        expanded["type"] = "parallel"
        expanded["actions"] = expanded.pop("parallel")
        return expanded

    return expanded


# ======================================================================================================================
# TRAJECTORIES
# ======================================================================================================================

@dataclasses.dataclass
class BILBO_InputTrajectoryStep:
    step: int
    left: float
    right: float


@dataclasses.dataclass
class BILBO_InputTrajectory:
    name: str  # Name of the trajectory
    id: int  # Numeric ID of the trajectory
    inputs: list[BILBO_InputTrajectoryStep]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.inputs)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt

    def to_vector(self, single_input: bool = False) -> np.ndarray:
        from robots.bilbo.robot.experiment.experiment_helpers import trajectory_inputs_to_vector
        return trajectory_inputs_to_vector(self.inputs, single_input=single_input)

    @classmethod
    def from_vector(cls, vector: np.ndarray, name: str, id: int, dt: float = None) -> BILBO_InputTrajectory:
        from robots.bilbo.robot.experiment.experiment_helpers import generate_trajectory_inputs
        return cls(name=name, id=id, inputs=generate_trajectory_inputs(vector), dt=dt or BILBO_CONTROL_DT)


@dataclasses.dataclass
class BILBO_StateTrajectory:
    states: list[BILBO_DynamicState]
    dt: float = BILBO_CONTROL_DT  # Time step

    @property
    def length(self) -> int:
        return len(self.states)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt


@dataclasses.dataclass
class BILBO_TrajectoryData:
    input_trajectory: BILBO_InputTrajectory
    state_trajectory: BILBO_StateTrajectory

    @property
    def length(self) -> int:
        return self.input_trajectory.length

    @property
    def time_vector(self) -> np.ndarray:
        return self.input_trajectory.time_vector


@dataclasses.dataclass
class BILBO_OutputTrajectory:
    output_name: str
    output: list[float]
    dt: float = BILBO_CONTROL_DT

    @property
    def length(self) -> int:
        return len(self.output)

    @property
    def time_vector(self) -> np.ndarray:
        return np.arange(0, self.length) * self.dt


# ======================================================================================================================
# ACTION TYPES - Concrete dataclasses for each action type
# ======================================================================================================================

# Type literal for all supported action types
ActionType = Literal[
    "beep", "set_mode", "set_tic", "speak", "set_marker", "run_trajectory",
    "wait_time", "wait_ticks", "wait_until_tick", "wait_event", "set_input",
    "set_velocity", "enable_external_input", "reset", "parallel"
]

ALLOWED_ACTIONS: list[str] = [
    "beep", "set_mode", "set_tic", "speak", "set_marker", "run_trajectory",
    "wait_time", "wait_ticks", "wait_until_tick", "wait_event", "set_input",
    "set_velocity", "enable_external_input", "reset", "parallel"
]


@dataclasses.dataclass
class BeepActionParams:
    """Parameters for beep action."""
    frequency: int = 1000
    time_ms: int = 250
    repeats: int = 1


@dataclasses.dataclass
class SetModeActionParams:
    """Parameters for set_mode action."""
    mode: str | BILBO_Control_Mode = "OFF"

    def __post_init__(self):
        # Normalize mode to string for serialization
        if isinstance(self.mode, BILBO_Control_Mode):
            self.mode = self.mode.name


@dataclasses.dataclass
class SetTICActionParams:
    """Parameters for set_tic action (Torque Integral Control)."""
    enabled: bool = True


@dataclasses.dataclass
class SpeakActionParams:
    """Parameters for speak action (text-to-speech)."""
    text: str = ""


@dataclasses.dataclass
class SetMarkerActionParams:
    """Parameters for set_marker action."""
    marker_id: str = ""
    marker_value: str = ""


@dataclasses.dataclass
class EnableExternalInputActionParams:
    """Parameters for enable_external_input action."""
    enabled: bool = True


@dataclasses.dataclass
class SetVelocityActionParams:
    """Parameters for set_velocity action."""
    forward: float = 0.0
    turn: float = 0.0
    normalized: bool = False


@dataclasses.dataclass
class SetInputActionParams:
    """Parameters for set_input action."""
    input: list[float] = dataclasses.field(default_factory=lambda: [0.0, 0.0])
    normalized: bool = False


@dataclasses.dataclass
class WaitTimeActionParams:
    """Parameters for wait_time action."""
    time_ms: int = 0


@dataclasses.dataclass
class WaitTicksActionParams:
    """Parameters for wait_ticks action."""
    ticks: int = 0


@dataclasses.dataclass
class WaitUntilTickActionParams:
    """Parameters for wait_until_tick action."""
    tick: int = 0


@dataclasses.dataclass
class WaitEventActionParams:
    """Parameters for wait_event action."""
    event: str = ""
    timeout: float | None = None


@dataclasses.dataclass
class RunTrajectoryActionParams:
    """Parameters for run_trajectory action."""
    input_trajectory: BILBO_InputTrajectory | dict | str | None = None


@dataclasses.dataclass
class ResetActionParams:
    """Parameters for reset action (no parameters needed)."""
    pass


@dataclasses.dataclass
class ParallelActionParams:
    """Parameters for parallel action."""
    actions: list[dict] = dataclasses.field(default_factory=list)


# Mapping from action type string to parameter dataclass
ACTION_PARAMS_MAPPING: dict[str, type] = {
    "beep": BeepActionParams,
    "set_mode": SetModeActionParams,
    "set_tic": SetTICActionParams,
    "speak": SpeakActionParams,
    "set_marker": SetMarkerActionParams,
    "enable_external_input": EnableExternalInputActionParams,
    "set_velocity": SetVelocityActionParams,
    "set_input": SetInputActionParams,
    "wait_time": WaitTimeActionParams,
    "wait_ticks": WaitTicksActionParams,
    "wait_until_tick": WaitUntilTickActionParams,
    "wait_event": WaitEventActionParams,
    "run_trajectory": RunTrajectoryActionParams,
    "reset": ResetActionParams,
    "parallel": ParallelActionParams,
}


# ======================================================================================================================
# EXPERIMENT ACTION DEFINITION
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentActionDefinition:
    """Definition of a single experiment action.

    This class represents an action that can be executed during an experiment.
    Actions can be scheduled by tick, time, or dependency (after another action).

    Example YAML:
        - type: beep
          frequency: 1000
          time_ms: 250

        - type: set_mode
          mode: BALANCING
          after: action_0
    """
    id: str
    type: str

    # Scheduling info (exactly one of these may be set)
    tick: int | None = None  # Absolute experiment tick
    after: str | None = None  # ID of action that must finish first
    time: float | None = None  # Absolute time [s] since experiment start

    delay: float | None = None  # Relative delay in seconds from previous action

    timeout: float | None = None  # Per-action timeout (seconds, optional)

    # Action-specific parameters
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if self.type not in ALLOWED_ACTIONS:
            raise ValueError(f"Action type '{self.type}' not allowed. Allowed actions: {ALLOWED_ACTIONS}")

    @classmethod
    def from_dict(cls, d: dict, index: int = 0) -> "ExperimentActionDefinition":
        """
        Parse an action definition from a dict.

        Args:
            d: Dict containing action definition. Must have 'type' field.
               'id' is optional - auto-generated as 'action_{index}' if missing.
            index: Index for auto-generating ID when not provided.

        Returns:
            ExperimentActionDefinition instance.

        Raises:
            ValueError: If 'type' field is missing.
        """
        if "type" not in d:
            raise ValueError(f"Action at index {index} missing required field 'type': {d}")

        # id is optional - auto-generate if missing
        action_id = d.get("id", f"action_{index}")

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "delay", "timeout", "parameters"}

        # If 'parameters' is explicitly provided, use it; otherwise collect non-reserved fields
        if "parameters" in d:
            parameters = d["parameters"]
        else:
            parameters = {
                k: v for k, v in d.items()
                if k not in reserved_fields
            }

        return cls(
            id=action_id,
            type=d["type"],
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            delay=d.get("delay"),
            timeout=d.get("timeout"),
            parameters=parameters,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        dict_out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
        }
        if self.tick is not None:
            dict_out["tick"] = self.tick
        if self.after is not None:
            dict_out["after"] = self.after
        if self.time is not None:
            dict_out["time"] = self.time
        if self.delay is not None:
            dict_out["delay"] = self.delay
        if self.timeout is not None:
            dict_out["timeout"] = self.timeout
        if self.parameters:
            dict_out["parameters"] = self.parameters
        return dict_out

    def get_typed_params(self) -> Any:
        """Get parameters as a typed dataclass.

        Returns the parameters converted to the appropriate dataclass
        for this action type, providing better IDE support and type checking.

        Example:
            action = ExperimentActionDefinition(id="beep1", type="beep", parameters={"frequency": 800})
            params = action.get_typed_params()  # Returns BeepActionParams(frequency=800, ...)
        """
        if self.type not in ACTION_PARAMS_MAPPING:
            return self.parameters

        params_cls = ACTION_PARAMS_MAPPING[self.type]
        return from_dict_auto(params_cls, self.parameters)


# ======================================================================================================================
# EXPERIMENT DEFINITION
# ======================================================================================================================

@dataclasses.dataclass(kw_only=True)
class ExperimentDefinition:
    """Definition of an experiment.

    An experiment consists of:
    - id: Unique identifier
    - description: Human-readable description
    - actions: List of actions to execute
    - timeout: Optional experiment timeout in seconds

    Example YAML:
        id: balance_test
        description: Test balancing control
        timeout: 30.0
        actions:
          - speak: "Starting test"
          - wait: 1s
          - mode: BALANCING
          - wait: 10s
          - mode: OFF
    """
    id: str
    description: str
    actions: list[ExperimentActionDefinition]
    timeout: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentDefinition":
        """Parse an experiment definition from a dict.

        Supports list-based actions format with:
        - Auto-generated IDs (action_0, action_1, etc.)
        - Shorthand syntax for common actions (wait, mode, speak, beep, etc.)
        - Implicit sequential chaining (actions run after the previous one by default)
        - Delay field for relative timing
        - Parallel action groups
        """
        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]

        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        # Parse actions with shorthand expansion and auto-ID generation
        actions = [
            ExperimentActionDefinition.from_dict(_expand_shorthand(a), index=i)
            for i, a in enumerate(raw_actions)
        ]

        return cls(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ExperimentDefinition":
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_file(cls, file: str) -> "ExperimentDefinition":
        """Load from YAML or JSON file."""
        if not file_exists(file):
            raise FileNotFoundError(f"Experiment definition file not found: {file}")

        with open(file, "r") as f:
            if file.lower().endswith((".yml", ".yaml")):
                data_dict = yaml.safe_load(f)
            else:
                data_dict = json.load(f)

        return cls.from_dict(data_dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "description": self.description,
            "timeout": self.timeout,
            "actions": [a.to_dict() for a in self.actions],
        }

    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save_to_file(self, file: str) -> None:
        """Save to YAML or JSON file based on extension."""
        with open(file, "w") as f:
            if file.lower().endswith((".yml", ".yaml")):
                yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(self.to_dict(), f, indent=2)


# ======================================================================================================================
# EXPERIMENT DATA STRUCTURES
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentActionData:
    """Data collected during action execution."""
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    data: Any | None = None


@dataclasses.dataclass(frozen=True)
class ExperimentMetaData:
    """Metadata about an experiment execution."""
    description: str
    camera_timestamp: float
    date: str
    control_config: BILBO_ControlConfig
    bilbo_config: BILBO_Config


@dataclasses.dataclass(frozen=False)
class ExperimentData:
    """Complete experiment data including samples and action data."""
    id: str
    meta: ExperimentMetaData
    definition: ExperimentDefinition
    samples: list[BILBO_Sample]
    actions: dict[str, ExperimentActionData]


# ======================================================================================================================
# FILE I/O
# ======================================================================================================================

INPUT_TRAJECTORY_FILE_EXTENSION = '.bitrj'


@dataclasses.dataclass
class BILBO_InputFileData:
    id: str
    description: str
    trajectory: BILBO_InputTrajectory

    @property
    def length(self) -> int:
        return self.trajectory.length


def write_input_file(file_name, folder, data: BILBO_InputFileData):
    data_dict = dataclasses.asdict(data)
    file_path = f"{folder}/{file_name}{INPUT_TRAJECTORY_FILE_EXTENSION}"
    try:
        writeJSON(file_path, data_dict)
    except Exception as e:
        print(f"Error writing input file: {e}")


def read_input_file(file) -> BILBO_InputFileData | None:
    if not file_exists(file):
        raise FileNotFoundError(f"Input file not found: {file}")

    try:
        data_dict = readJSON(file)
        data = from_dict_auto(BILBO_InputFileData, data_dict)
        return data
    except Exception as e:
        print(f"Error reading input file: {e}")
        return None


# ======================================================================================================================
# HELPER FUNCTIONS FOR BUILDING EXPERIMENTS
# ======================================================================================================================

def beep(frequency: int = 1000, time_ms: int = 250, repeats: int = 1, **scheduling) -> ExperimentActionDefinition:
    """Create a beep action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "beep"),
        type="beep",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"frequency": frequency, "time_ms": time_ms, "repeats": repeats}
    )


def set_mode(mode: str | BILBO_Control_Mode, **scheduling) -> ExperimentActionDefinition:
    """Create a set_mode action."""
    mode_str = mode.name if isinstance(mode, BILBO_Control_Mode) else mode
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_mode"),
        type="set_mode",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"mode": mode_str}
    )


def speak(text: str, **scheduling) -> ExperimentActionDefinition:
    """Create a speak action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "speak"),
        type="speak",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"text": text}
    )


def wait_time(time_ms: int = 0, time_s: float = None, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_time action. Use either time_ms or time_s."""
    if time_s is not None:
        time_ms = int(time_s * 1000)
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_time"),
        type="wait_time",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"time_ms": time_ms}
    )


def wait_ticks(ticks: int, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_ticks action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_ticks"),
        type="wait_ticks",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"ticks": ticks}
    )


def set_velocity(forward: float = 0.0, turn: float = 0.0, normalized: bool = False, **scheduling) -> ExperimentActionDefinition:
    """Create a set_velocity action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_velocity"),
        type="set_velocity",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"forward": forward, "turn": turn, "normalized": normalized}
    )


def set_input(input: list[float], normalized: bool = False, **scheduling) -> ExperimentActionDefinition:
    """Create a set_input action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_input"),
        type="set_input",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"input": input, "normalized": normalized}
    )


def run_trajectory(trajectory: BILBO_InputTrajectory | dict | str, **scheduling) -> ExperimentActionDefinition:
    """Create a run_trajectory action."""
    # Convert trajectory to dict if it's a dataclass
    if isinstance(trajectory, BILBO_InputTrajectory):
        trajectory = dataclasses.asdict(trajectory)
    return ExperimentActionDefinition(
        id=scheduling.get("id", "run_trajectory"),
        type="run_trajectory",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"input_trajectory": trajectory}
    )


def set_marker(marker_id: str, marker_value: str, **scheduling) -> ExperimentActionDefinition:
    """Create a set_marker action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_marker"),
        type="set_marker",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"marker_id": marker_id, "marker_value": marker_value}
    )


def enable_external_input(enabled: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create an enable_external_input action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "enable_external_input"),
        type="enable_external_input",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"enabled": enabled}
    )


def reset(**scheduling) -> ExperimentActionDefinition:
    """Create a reset action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "reset"),
        type="reset",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={}
    )


def parallel(actions: list[ExperimentActionDefinition | dict], **scheduling) -> ExperimentActionDefinition:
    """Create a parallel action that runs multiple actions simultaneously."""
    action_dicts = []
    for a in actions:
        if isinstance(a, ExperimentActionDefinition):
            action_dicts.append(a.to_dict())
        else:
            action_dicts.append(a)
    return ExperimentActionDefinition(
        id=scheduling.get("id", "parallel"),
        type="parallel",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"actions": action_dicts}
    )


def set_tic(enabled: bool = True, **scheduling) -> ExperimentActionDefinition:
    """Create a set_tic action (Torque Integral Control)."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "set_tic"),
        type="set_tic",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"enabled": enabled}
    )


def wait_event(event: str, timeout: float | None = None, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_event action."""
    params = {"event": event}
    if timeout is not None:
        params["timeout"] = timeout
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_event"),
        type="wait_event",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters=params
    )


def wait_until_tick(tick_target: int, **scheduling) -> ExperimentActionDefinition:
    """Create a wait_until_tick action."""
    return ExperimentActionDefinition(
        id=scheduling.get("id", "wait_until_tick"),
        type="wait_until_tick",
        tick=scheduling.get("tick"),
        after=scheduling.get("after"),
        time=scheduling.get("time"),
        delay=scheduling.get("delay"),
        timeout=scheduling.get("timeout"),
        parameters={"tick": tick_target}
    )


# ======================================================================================================================
# EXPERIMENT BUILDER
# ======================================================================================================================

class ExperimentBuilder:
    """Builder class for creating experiments programmatically.

    Example:
        exp = (ExperimentBuilder("my_test", "Test experiment")
               .speak("Starting test")
               .wait(time_s=1.0)
               .set_mode("BALANCING")
               .wait(time_s=10.0)
               .set_mode("OFF")
               .build())
    """

    def __init__(self, id: str, description: str, timeout: float | None = None):
        self.id = id
        self.description = description
        self.timeout = timeout
        self._actions: list[ExperimentActionDefinition] = []
        self._action_counter = 0

    def _next_id(self, prefix: str = "action") -> str:
        id = f"{prefix}_{self._action_counter}"
        self._action_counter += 1
        return id

    def add(self, action: ExperimentActionDefinition) -> "ExperimentBuilder":
        """Add a raw action definition."""
        if not action.id or action.id in ["beep", "set_mode", "speak", "wait_time", "wait_ticks",
                                           "set_velocity", "set_input", "run_trajectory", "set_marker",
                                           "enable_external_input", "reset", "parallel", "set_tic",
                                           "wait_event", "wait_until_tick"]:
            action.id = self._next_id(action.type)
        self._actions.append(action)
        return self

    def beep(self, frequency: int = 1000, time_ms: int = 250, repeats: int = 1) -> "ExperimentBuilder":
        return self.add(beep(frequency, time_ms, repeats, id=self._next_id("beep")))

    def set_mode(self, mode: str | BILBO_Control_Mode) -> "ExperimentBuilder":
        return self.add(set_mode(mode, id=self._next_id("set_mode")))

    def speak(self, text: str) -> "ExperimentBuilder":
        return self.add(speak(text, id=self._next_id("speak")))

    def wait(self, time_ms: int = 0, time_s: float = None, ticks: int = None) -> "ExperimentBuilder":
        if ticks is not None:
            return self.add(wait_ticks(ticks, id=self._next_id("wait_ticks")))
        return self.add(wait_time(time_ms, time_s, id=self._next_id("wait_time")))

    def set_velocity(self, forward: float = 0.0, turn: float = 0.0, normalized: bool = False) -> "ExperimentBuilder":
        return self.add(set_velocity(forward, turn, normalized, id=self._next_id("set_velocity")))

    def set_input(self, input: list[float], normalized: bool = False) -> "ExperimentBuilder":
        return self.add(set_input(input, normalized, id=self._next_id("set_input")))

    def run_trajectory(self, trajectory: BILBO_InputTrajectory | dict | str) -> "ExperimentBuilder":
        return self.add(run_trajectory(trajectory, id=self._next_id("run_trajectory")))

    def set_marker(self, marker_id: str, marker_value: str) -> "ExperimentBuilder":
        return self.add(set_marker(marker_id, marker_value, id=self._next_id("set_marker")))

    def enable_external_input(self, enabled: bool = True) -> "ExperimentBuilder":
        return self.add(enable_external_input(enabled, id=self._next_id("enable_external_input")))

    def reset(self) -> "ExperimentBuilder":
        return self.add(reset(id=self._next_id("reset")))

    def set_tic(self, enabled: bool = True) -> "ExperimentBuilder":
        return self.add(set_tic(enabled, id=self._next_id("set_tic")))

    def wait_event(self, event: str, timeout: float | None = None) -> "ExperimentBuilder":
        return self.add(wait_event(event, timeout, id=self._next_id("wait_event")))

    def wait_until_tick(self, tick_target: int) -> "ExperimentBuilder":
        return self.add(wait_until_tick(tick_target, id=self._next_id("wait_until_tick")))

    def parallel(self, *actions: ExperimentActionDefinition | dict) -> "ExperimentBuilder":
        return self.add(parallel(list(actions), id=self._next_id("parallel")))

    def build(self) -> ExperimentDefinition:
        """Build and return the experiment definition."""
        return ExperimentDefinition(
            id=self.id,
            description=self.description,
            actions=self._actions,
            timeout=self.timeout
        )
