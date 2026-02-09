import dataclasses
import enum

import numpy as np

BILBO_HOST_NAMES = ['bilbo1', 'bilbo2', 'bilbo3', 'bilbo4', 'bilbo5']

PATH_TO_MAIN = '/home/admin/robot/software/main.py'
PYENV_SHIM_PATH = '/home/admin/.pyenv/shims/python3'
BILBO_USER_NAME = 'admin'
BILBO_PASSWORD = 'beutlin'

BILBO_CONTROL_DT = 0.01
MAX_STEPS_TRAJECTORY = 3000


# === CONFIG ==========================================================================================================
@dataclasses.dataclass
class BILBO_PhysicalModel:
    type: str
    wheel_diameter: float
    vertical_offset: float
    mass: float
    height: float
    width: float
    depth: float
    distance_wheels: float
    l_cg: float
    theta_offset: float


@dataclasses.dataclass
class BILBO_OptiTrack_Definition:
    points: list[int]
    point_x_axis_start: int
    point_x_axis_end: int
    point_y_axis_start: int
    point_y_axis_end: int
    marker_size: float


@dataclasses.dataclass
class BILBO_General_Information:
    id: str
    short_id: str
    type: str
    version: str
    color: list | None


@dataclasses.dataclass
class BILBO_Network_Information:
    address: str
    data_stream_port: int
    gui_port: int
    ssid: str
    username: str
    password: str


# === HARDWARE DEFINITIONS =============================================================================================
@dataclasses.dataclass
class DisplaySettings:
    active: bool
    resolution: list | None


@dataclasses.dataclass
class SoundSettings:
    active: bool
    gain: float | None


@dataclasses.dataclass
class ButtonSettings:
    type: str | None  # Can be 'internal', 'sx1508', 'sx1509' or None
    pin: int | None


@dataclasses.dataclass
class Buttons:
    primary: ButtonSettings
    secondary: ButtonSettings


class BILBO_Shields(enum.StrEnum):
    BILBO_SHIELD_REV2 = 'bilbo_shield_rev2'
    NONE = 'none'


@dataclasses.dataclass
class BILBO_Hardware_Electronics:
    board_revision: str
    compute_module: str
    shield: BILBO_Shields
    display: DisplaySettings
    sound: SoundSettings
    battery_cells: int
    buttons: Buttons


@dataclasses.dataclass
class Model:
    type: str
    theta_offset: float = 0.0


# ======================================================================================================================
@dataclasses.dataclass
class BILBO_Config:
    general: BILBO_General_Information
    network: BILBO_Network_Information
    optitrack: BILBO_OptiTrack_Definition
    model: BILBO_PhysicalModel
    electronics: BILBO_Hardware_Electronics


# ======================================================================================================================
# === CONTROL ==========================================================================================================
# ======================================================================================================================
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
    v_decay_stiction: float = 0.0
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
    """Configuration for the position controller (carrot-chase path following).
    Mirrors the on-robot bilbo_control_definitions.PositionControl_Config."""
    Ts: float = 0.01                        # [s] Update period
    kp_angular: float = 10.0                # [rad/s per rad] Proportional gain for angular control
    ki_angular: float = 0.3                 # [rad/s per rad*s] Integral gain for angular control
    kp_linear: float = 2.0                  # [1/s] Proportional gain (fallback when decel_limit=0)
    ki_linear: float = 0.0                  # [1/s^2] Integral gain for linear control
    kd_linear: float = 0.5                  # [-] Velocity damping: subtracts kd_linear * |current_v| from speed command
    max_speed: float = 0.4                  # [m/s] Maximum forward velocity
    max_turn_rate: float = 5.0              # [rad/s] Maximum yaw rate
    speed_transition_time: float = 0.5      # [s] Time to smoothly transition between waypoint speeds
    lookahead_base: float = 0.15            # [m] Minimum lookahead distance
    lookahead_gain: float = 0.3             # [s] Lookahead = base + gain * |velocity|
    lookahead_max: float = 0.5              # [m] Maximum lookahead distance
    arrival_tolerance: float = 0.05         # [m] Distance to consider "arrived"
    arrival_dwell_time: float = 0.5         # [s] Hold time at STOP waypoint
    reverse_enter_angle: float = 2.1        # [rad] ~120 deg - enter reverse mode
    reverse_exit_angle: float = 1.05        # [rad] ~60 deg - exit reverse mode
    corner_slowdown_distance: float = 0.5   # [m] Distance from corner to start slowing down
    decel_limit: float = 0.0                # [m/s²] sqrt deceleration profile. 0 = disabled


@dataclasses.dataclass
class FloorRoughness_Config:
    """Tuning parameters for floor roughness compensation.

    These scale factors are applied at roughness=1.0 (linear interpolation from 1.0).
    """
    enabled: bool = True                    # Enable/disable roughness compensation
    kc_max: float = -0.011              # Max Kc value at roughness=1.0 (Coulomb friction compensation)
    v_decay_stiction_max: float = 0.15   # Stribeck decay speed at roughness=1.0 (linearly interpolated)
    v_kv_scale: float = 1.1             # Forward velocity feedforward Kv scale at roughness=1.0
    v_kp_scale: float = 1.6             # Forward velocity PID Kp scale at roughness=1.0
    v_ki_scale: float = 1.3             # Forward velocity PID Ki scale at roughness=1.0
    psidot_kp_scale: float = 1.25       # Turn velocity PID Kp scale at roughness=1.0
    psidot_ki_scale: float = 1.15       # Turn velocity PID Ki scale at roughness=1.0
    pos_kp_scale: float = 1.6           # Position control kp_linear scale at roughness=1.0
    pos_ki_scale: float = 1.2           # Position control ki_linear scale at roughness=1.0
    pos_decel_scale: float = 2.0        # Position control decel_limit scale at roughness=1.0


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


# ======================================================================================================================
# === OPTITRACK ========================================================================================================
# ======================================================================================================================
@dataclasses.dataclass
class BILBO_OriginConfig:
    id: str
    points: list
    origin: int
    x_axis_end: int
    y_axis_end: int
    marker_size: float
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0


@dataclasses.dataclass(kw_only=True)
class BILBO_LimboMarkerConfig:
    id: str = 'limbo-marker'
    points: list
    x_start: int
    x_end: int
    y_start: int
    y_end: int
    limbo_direction: float = -np.pi / 2
