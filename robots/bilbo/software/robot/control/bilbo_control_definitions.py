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
    """Configuration for the position controller (carrot-chase path following)

    This config is synced to the firmware's bilbo_position_control_config_t.

    Simplified algorithm:
    - Speed = kp_linear * carrot_distance (simple and robust)
    - Weight + corner angle determines how carrot advances past waypoints
    - Per-waypoint speed limits with smooth transitions
    - Reverse mode always enabled with hysteresis
    """
    kp_angular: float = 10.0                # [rad/s per rad] Proportional gain for angular control
    ki_angular: float = 0.3                 # [rad/s per rad*s] Integral gain for angular control
    kp_linear: float = 2.0                  # [1/s] Proportional gain: speed = kp_linear * carrot_distance (fallback when decel_limit=0)
    ki_linear: float = 0.0                  # [1/s^2] Integral gain for linear control (usually 0)
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
    decel_limit: float = 0.0               # [m/s²] sqrt deceleration profile. 0 = disabled (linear kp*d)


@dataclasses.dataclass
class FloorRoughness_Config:
    """Tuning parameters for floor roughness compensation.

    These scale factors are applied at roughness=1.0 (linear interpolation from 1.0).
    """
    enabled: bool = True                # Enable/disable roughness compensation
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


@dataclasses.dataclass
class BILBO_PositionControl_Sample:
    """Sample data for position control state"""
    mode: int = 0
    mode_name: str = ''
    path_state: int = 0
    path_state_name: str = ''
    waypoint_count: int = 0
    current_waypoint_index: int = 0
    is_busy: bool = False
    data: dict = dataclasses.field(default_factory=dict)
    waypoints: list = dataclasses.field(default_factory=list)  # List of waypoint dicts


@dataclasses.dataclass
class BILBO_Control_Sample:
    status: BILBO_Control_Status = dataclasses.field(default=BILBO_Control_Status(BILBO_Control_Status.NORMAL))
    mode: BILBO_Control_Mode = dataclasses.field(default=BILBO_Control_Mode(BILBO_Control_Mode.OFF))
    input: BILBO_Control_Inputs = dataclasses.field(default_factory=BILBO_Control_Inputs)
    tic_enabled: bool = False
    vic_enabled: bool = False
    input_enabled: bool = False
    position_control: BILBO_PositionControl_Sample = dataclasses.field(default_factory=BILBO_PositionControl_Sample)


class BILBO_Control_Event_Type(enum.IntEnum):
    ERROR = 0
    MODE_CHANGED = 1
    CONFIGURATION_CHANGED = 2
    VIC_CHANGED = 3
    TIC_CHANGED = 4
    POSITION_ELEMENT_FINISHED = 5
    POSITION_ELEMENT_TIMEOUT = 6