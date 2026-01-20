from __future__ import annotations

import dataclasses
import json
from typing import Any

import numpy as np
import yaml

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists
from core.utils.json_utils import writeJSON, readJSON
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState, BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_CONTROL_DT, BILBO_Config, BILBO_ControlConfig


# === TRAJECTORIES =====================================================================================================
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


# === EXPERIMENTS ======================================================================================================
# @dataclasses.dataclass
# class BILBO_ExperimentMeta:
#     robot_id: str
#     description: str
#     date: str
#     robot_config: BILBO_Config
#     control_config: BILBO_ControlConfig
#
#
# @dataclasses.dataclass
# class BILBO_ExperimentData:
#     id: str
#     meta: BILBO_ExperimentMeta
#     data: BILBO_TrajectoryData


# EXPERIMENT_ACTION_TYPE_MAPPING = {
#     "beep": BeepAction,
#     "set_mode": SetModeAction,
#     "set_tic": SetTICAction,
#     "speak": SpeakAction,
#     "set_marker": SetMarkerAction,
#     "run_trajectory": RunTrajectoryAction,
#     "wait_time": WaitTimeAction,
#     "wait_ticks": WaitTickAction,
#     "wait_until_tick": WaitUntilTickAction,
#     "wait_event": WaitEventAction,
#     "set_input": SetInputAction,
#     "enable_external_input": EnableExternalInputAction,
#     "reset": ResetAction,
# }

ALLOWED_ACTIONS = [
    'beep', 'set_mode', 'set_tic', 'speak', 'set_marker', 'run_trajectory', 'wait_time', 'wait_ticks',
    'wait_until_tick',
    'wait_event', 'set_input', 'enable_external_input', 'reset', 'set_velocity'
]


@dataclasses.dataclass
class ExperimentActionDefinition:
    id: str
    type: str

    # scheduling info (exactly one of these may be set)
    tick: int | None = None  # absolute experiment tick
    after: str | None = None  # id of action that must finish first
    time: float | None = None  # absolute time [s] since experiment start

    timeout: float | None = None  # per-action timeout (seconds, optional)

    # action-specific stuff (parameters for the concrete action class)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if self.type not in ALLOWED_ACTIONS:
            raise ValueError(f"Action type '{self.type}' not allowed. Allowed actions: {ALLOWED_ACTIONS}")

    # ------------------------------------------------------------------
    @classmethod
    def from_key_and_dict(cls, action_id: str, d: dict) -> ExperimentActionDefinition:
        """
        For new format:
            actions:
              action1:
                type: ...
                time: ...
                mode: BALANCING
        """

        if "type" not in d:
            raise ValueError(f"Action '{action_id}' missing required field 'type'")

        # Extract scheduling fields
        tick = d.get("tick")
        after = d.get("after")
        time = d.get("time")
        timeout = d.get("timeout")

        # Everything else = parameters
        parameters = {
            k: v for k, v in d.items()
            if k not in ("type", "tick", "after", "time", "timeout")
        }

        return cls(
            id=action_id,
            type=d["type"],
            tick=tick,
            after=after,
            time=time,
            timeout=timeout,
            parameters=parameters
        )

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentActionDefinition":
        """
        OLD FORMAT compatibility: a dict that already contains 'id'
        """
        if "id" not in d or "type" not in d:
            raise ValueError(f"Action definition must contain 'id' and 'type': {d}")

        params = d.get("parameters", {})

        return cls(
            id=d["id"],
            type=d["type"],
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            timeout=d.get("timeout"),
            parameters=params,
        )

    def to_dict(self) -> dict[str, Any]:
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
        if self.timeout is not None:
            dict_out["timeout"] = self.timeout
        if self.parameters:
            dict_out["parameters"] = self.parameters
        return dict_out


@dataclasses.dataclass(kw_only=True)
class ExperimentDefinition:
    id: str
    description: str
    actions: list[ExperimentActionDefinition]
    timeout: float | None = None

    # ----------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> ExperimentDefinition:
        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]

        # --- NEW FORMAT: mapping: action_id -> dict ---
        if isinstance(raw_actions, dict):
            actions = [
                ExperimentActionDefinition.from_key_and_dict(action_id, action_dict)
                for action_id, action_dict in raw_actions.items()
            ]

        # --- OLD FORMAT: list of dicts (id included in each entry) ---
        elif isinstance(raw_actions, list):
            actions = [
                ExperimentActionDefinition.from_dict(a)
                for a in raw_actions
            ]

        else:
            raise TypeError("'actions' must be either a dict or a list")

        return cls(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
        )

    # JSON string in -> ExperimentDefinition
    @classmethod
    def from_json(cls, json_str: str) -> ExperimentDefinition:
        data = json.loads(json_str)
        return cls.from_dict(data)

    # YAML or JSON file -> ExperimentDefinition
    @classmethod
    def from_file(cls, file: str) -> ExperimentDefinition:
        if not file_exists(file):
            raise FileNotFoundError(f"Experiment definition file not found: {file}")

        with open(file, "r") as f:
            if file.lower().endswith((".yml", ".yaml")):
                data_dict = yaml.safe_load(f)
            else:
                data_dict = json.load(f)

        return cls.from_dict(data_dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "timeout": self.timeout,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclasses.dataclass
class ExperimentActionData:
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    data: Any | None = None


@dataclasses.dataclass(frozen=True)
class ExperimentMetaData:
    description: str
    camera_timestamp: float
    date: str
    control_config: BILBO_ControlConfig
    bilbo_config: BILBO_Config


@dataclasses.dataclass(frozen=False)
class ExperimentData:
    id: str
    meta: ExperimentMetaData
    definition: ExperimentDefinition
    samples: list[BILBO_Sample]
    actions: dict[str, ExperimentActionData]


# === FILES ============================================================================================================
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
