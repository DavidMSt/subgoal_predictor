# ======================================================================================================================
import dataclasses
import numpy as np

from robots.bilbo.robot.bilbo_data import BILBO_DynamicState
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_Config, BILBO_ControlConfig

INPUT_TRAJECTORY_FILE_EXTENSION = '.bitrj'
EXPERIMENT_FILE_EXTENSION = '.biexp'


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_InputTrajectoryStep:
    step: int
    left: float
    right: float


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_InputTrajectory:
    name: str
    id: int
    length: int
    time_vector: np.ndarray
    control_mode: BILBO_Control_Mode
    inputs: list[BILBO_InputTrajectoryStep]

    def to_vector(self, single_input: bool = False) -> np.ndarray:
        from robots.bilbo.robot.experiment.helpers import trajectoryInputToVector

        return trajectoryInputToVector(self.inputs, single_input=single_input)


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_StateTrajectory:
    time_vector: np.ndarray
    states: list[BILBO_DynamicState]


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_TrajectoryExperimentData:
    input_trajectory: BILBO_InputTrajectory
    state_trajectory: BILBO_StateTrajectory


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_OutputTrajectory:
    time_vector: np.ndarray
    output_name: str
    output: list[float]


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_TrajectoryExperimentMeta:
    robot_id: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    description: str
    software_revision: str


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_TrajectoryExperiment:
    id: str
    meta: BILBO_TrajectoryExperimentMeta
    data: BILBO_TrajectoryExperimentData


@dataclasses.dataclass
class FrequencyComponent:
    frequency: float
    weight: float  # relative amplitude (normalized to 1)


@dataclasses.dataclass
class BILBO_InputAnalytics:
    steps: int
    Ts: float
    max_amplitude: float
    dominant_frequencies: list[FrequencyComponent]
    is_2d: bool


# ======================================================================================================================
# FILES
# ======================================================================================================================
@dataclasses.dataclass
class BILBO_InputFileMeta:
    date: str
    version: str
    description: str
    experiment_id: str | None
    experiment_index: int | None
    length: int


@dataclasses.dataclass
class BILBO_InputFileData:
    name: str
    meta: BILBO_InputFileMeta
    trajectory: BILBO_InputTrajectory


@dataclasses.dataclass
class BILBO_TrajectoryExperimentFile:
    data: BILBO_TrajectoryExperiment


# ======================================================================================================================

@dataclasses.dataclass
class BILBO_SystemIdentificationData:
    ...


BILBO_SYSTEM_ID_FILE_EXTENSION = '.bid'


@dataclasses.dataclass
class BILBO_SystemIdentificationFile:
    ...
