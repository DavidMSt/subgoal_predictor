import dataclasses
import enum

import numpy as np


class BILBO_Control_Mode(enum.IntEnum):
    OFF = 0
    DIRECT = 1
    BALANCING = 2
    VELOCITY = 3
    POSITION = 4


@dataclasses.dataclass
class TIC_Config:
    enabled: bool = False
    ki: float = 0.0
    max_torque: float = 0.0
    theta_limit: float = 0.0


@dataclasses.dataclass
class VIC_Config:
    enabled: bool = False
    ki: float = 0.0
    max_torque: float = 0.0
    v_limit: float = 0.0
    theta_limit: float = 0.0


@dataclasses.dataclass
class TWIPR_Balancing_Control_Config:
    K: list = dataclasses.field(default_factory=list)  # State Feedback Gain
    tic: TIC_Config = dataclasses.field(default_factory=TIC_Config)
    vic: VIC_Config = dataclasses.field(default_factory=VIC_Config)


@dataclasses.dataclass
class PID_Config:
    Kp: float = 0.0
    Kd: float = 0.0
    Ki: float = 0.0
    Ts: float = 0.0
    enable_i_limit: bool = False
    i_term_limit: float = 0.0
    enable_input_limit: bool = False
    input_limit: float = 0.0
    enable_output_limit: bool = False
    output_limit: float = 0.0
    enable_d_filter: bool = False
    Td_filter: float = 0.0
    enable_rate_limit: bool = False
    rate_limit: float = 0.0
    enable_setpoint_rate_limit: bool = False
    setpoint_rate_limit: float = 0.0


@dataclasses.dataclass
class Feedforward_Config:
    Kv: float = 0.0
    Ka: float = 0.0
    Kc: float = 0.0
    enable_vref_slew: bool = False
    vref_slew_rate: float = 0.0
    enable_a_filter: bool = False
    Ta_filter: float = 0.0
    enable_stiction: bool = False
    v0_stiction: float = 0.0
    enable_output_limit: bool = False
    output_limit: float = 0.0
    enable_output_slew: bool = False
    output_slew_rate: float = 0.0


@dataclasses.dataclass
class VelocityConfig:
    pid: PID_Config
    feedforward: Feedforward_Config


@dataclasses.dataclass
class VelocityControl_Config:
    v: VelocityConfig = dataclasses.field(default_factory=VelocityConfig)
    psidot: VelocityConfig = dataclasses.field(default_factory=VelocityConfig)


@dataclasses.dataclass
class PositionControl_Config:
    kp_linear: float = 0.0
    ki_linear: float = 0.0
    kp_angular: float = 0.0
    ki_angular: float = 0.0
    lookahead_distance: float = 0.3
    allow_reverse: int = 1
    backwards_switch_angle: float = np.deg2rad(100.0)
    distance_arrival_tolerance: float = 0.05
    angle_arrival_tolerance: float = np.deg2rad(5.0)
    arrival_time: float = 2.0
    max_speed_forward: float = 0.75
    max_speed_turn: float = 3


@dataclasses.dataclass
class General_Control_Config:
    max_wheel_speed: float = 0.0
    max_wheel_torque: float = 0.0
    enable_external_inputs: bool = False
    torque_offset: list = dataclasses.field(default_factory=lambda: [0, 0])


@dataclasses.dataclass
class InputConfig:
    max: float = 0.0


@dataclasses.dataclass
class BalancingInputsConfig:
    forward: InputConfig = dataclasses.field(default_factory=InputConfig)
    turn: InputConfig = dataclasses.field(default_factory=InputConfig)


@dataclasses.dataclass
class VelocityInputsConfig:
    forward: InputConfig = dataclasses.field(default_factory=InputConfig)
    turn: InputConfig = dataclasses.field(default_factory=InputConfig)


@dataclasses.dataclass
class ExternalInputsConfig:
    balancing: BalancingInputsConfig = dataclasses.field(default_factory=BalancingInputsConfig)
    velocity: VelocityInputsConfig = dataclasses.field(default_factory=VelocityInputsConfig)


@dataclasses.dataclass
class BILBO_ControlConfig:
    name: str = ''
    description: str = ''
    general: General_Control_Config = dataclasses.field(default_factory=General_Control_Config)
    inputs: ExternalInputsConfig = dataclasses.field(default_factory=ExternalInputsConfig)
    balancing_control: TWIPR_Balancing_Control_Config = dataclasses.field(
        default_factory=TWIPR_Balancing_Control_Config)
    velocity_control: VelocityControl_Config = dataclasses.field(default_factory=VelocityControl_Config)
    position_control: PositionControl_Config = dataclasses.field(default_factory=PositionControl_Config)


class BILBO_Control_Status(enum.IntEnum):
    ERROR = 0
    NORMAL = 1


@dataclasses.dataclass
class BILBO_ExternalInput:
    left: float = 0.0
    right: float = 0.0


@dataclasses.dataclass
class BILBO_VelocityInput:
    forward: float = 0.0
    turn: float = 0.0


@dataclasses.dataclass
class BILBO_PositionInput:
    x: float = 0.0
    y: float = 0.0


@dataclasses.dataclass
class BILBO_Control_Inputs:
    enabled: bool = True
    external: BILBO_ExternalInput = dataclasses.field(default_factory=BILBO_ExternalInput)
    velocity: BILBO_VelocityInput = dataclasses.field(default_factory=BILBO_VelocityInput)
    position: BILBO_PositionInput = dataclasses.field(default_factory=BILBO_PositionInput)

    def reset(self):
        self.enabled = True
        self.external = BILBO_ExternalInput(0, 0)
        self.velocity = BILBO_VelocityInput(0, 0)
        self.position = BILBO_PositionInput(0, 0)


@dataclasses.dataclass(frozen=True)
class BILBO_Control_Sample:
    status: BILBO_Control_Status = dataclasses.field(default=BILBO_Control_Status(BILBO_Control_Status.NORMAL))
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    input: BILBO_Control_Inputs = dataclasses.field(default_factory=BILBO_Control_Inputs)
    tic_enabled: bool = False
    vic_enabled: bool = False
    input_enabled: bool = False


class BILBO_Control_Event_Type(enum.IntEnum):
    ERROR = 0
    MODE_CHANGED = 1
    CONFIGURATION_CHANGED = 2
    VIC_CHANGED = 3
    TIC_CHANGED = 4
    POSITION_ELEMENT_FINISHED = 5
    POSITION_ELEMENT_TIMEOUT = 6
