import dataclasses

# === OWN PACKAGES =====================================================================================================
from robot.control.bilbo_control_definitions import BILBO_Control_Sample
from robot.estimation.bilbo_estimation import BILBO_Estimation_Sample
from robot.drive.bilbo_drive import TWIPR_Drive_Sample
from robot.experiment.definitions import BILBO_ExperimentHandler_Sample
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from robot.sensors.bilbo_sensors import BILBO_Sensors_Sample


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Sample_General:
    status: str = ''
    time: float = 0.0
    time_global: float = 0.0
    tick: int = 0
    connection_strength: float = 0.0
    internet_connected: bool = False
    timecode: str = '00:00:00:00'
    timecode_fps: float = 0.0


# ======================================================================================================================
@dataclasses.dataclass(frozen=False)
class BILBO_Sample:
    tick: int = 0
    time: float = 0.0
    general: BILBO_Sample_General = dataclasses.field(default_factory=BILBO_Sample_General)
    control: BILBO_Control_Sample = dataclasses.field(default_factory=BILBO_Control_Sample)
    estimation: BILBO_Estimation_Sample = dataclasses.field(default_factory=BILBO_Estimation_Sample)
    drive: TWIPR_Drive_Sample = dataclasses.field(default_factory=TWIPR_Drive_Sample)
    sensors: BILBO_Sensors_Sample = dataclasses.field(default_factory=BILBO_Sensors_Sample)
    lowlevel: BILBO_LL_Sample = dataclasses.field(default_factory=BILBO_LL_Sample)
    experiment: BILBO_ExperimentHandler_Sample = dataclasses.field(default_factory=BILBO_ExperimentHandler_Sample)
