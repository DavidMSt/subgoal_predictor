# stm32_control.py
#
# ctypes mirror of the STM32-side control types (BILBO / BILBO)
# Based on:
#   - bilbo_control.h
#   - bilbo_balancing_control.h
#   - bilbo_velocity_control.h
#   - bilbo_position_control.h
#   - bilbo_vic_tic.h
#
# Notes:
# - For wire stability, we use explicit-width integer fields (uint8/int8/uint32).
# - Dataclasses below are Python-friendly "DTOs" (easy to log/inspect/serialize).
# - ctypes.Structure classes are the on-wire/binary layout mirrors.
# - If your STM32 structs are packed, you may want to add `_pack_ = 1` consistently
#   to the ctypes.Structure classes that go over the wire (and ensure STM32 matches).

from __future__ import annotations

import ctypes
import enum
from dataclasses import dataclass, field
from typing import List

import numpy as np

from core.communication.serial.serial_interface import SerialMessage, SerialCommandType
from robot.lowlevel.stm32_messages import (
    BILBO_LL_MESSAGE_CONTROL_EVENT,
    BILBO_LL_MESSAGE_POSITION_CONTROL_EVENT,
)


# =============================================================================
# Enums (mirror of C++ enum class underlying types)
# =============================================================================

class bilbo_control_mode_t(enum.IntEnum):
    # enum class bilbo_control_mode_t : uint8_t
    OFF = 0
    DIRECT = 1
    BALANCING = 2
    VELOCITY = 3
    POSITION = 4


class bilbo_control_status_t(enum.IntEnum):
    # enum class bilbo_control_status_t : int8_t
    NONE = 0
    RUNNING = 1
    ERROR = -1


class bilbo_balancing_control_mode_t(enum.IntEnum):
    # enum class bilbo_balancing_control_mode_t : uint8_t
    OFF = 0
    DIRECT = 1
    ON = 2


class bilbo_balancing_control_status_t(enum.IntEnum):
    # enum class bilbo_balancing_control_status_t : int8_t
    NONE = 0
    IDLE = 1
    ERROR = -1
    RUNNING = 2


class bilbo_position_control_mode_t(enum.IntEnum):
    """Position control operating modes (enum class bilbo_position_control_mode_t : uint8_t)"""
    IDLE = 0             # No active command, outputs zero
    TURN_TO_HEADING = 1  # Rotating in place to target heading
    DRIVE_TO_POINT = 2   # Driving to a single point
    FOLLOW_PATH = 3      # Following waypoint path


class bilbo_path_state_t(enum.IntEnum):
    """Path execution state machine (enum class bilbo_path_state_t : uint8_t)"""
    IDLE = 0     # No path loaded or path completed
    RUNNING = 1  # Actively following path
    PAUSED = 2   # Execution paused, internal state preserved


class position_control_event_t(enum.IntEnum):
    """Position control events (enum class position_control_event_t : uint8_t)"""
    PATH_STARTED = 0
    # 1 reserved (was WAYPOINT_PASSED)
    WAYPOINT_REACHED = 2
    WAYPOINT_COMPLETED = 3
    PATH_PAUSED = 4
    PATH_RESUMED = 5
    PATH_FINISHED = 6
    PATH_TIMEOUT = 7
    PATH_ABORTED = 8
    MOVE_TO_POINT_STARTED = 9
    MOVE_TO_POINT_COMPLETED = 10
    MOVE_TO_POINT_TIMEOUT = 11
    TURN_TO_HEADING_STARTED = 12
    TURN_TO_HEADING_COMPLETED = 13
    TURN_TO_HEADING_TIMEOUT = 14
    MODE_CHANGED = 15
    PATH_BUFFER_FULL = 16


class control_event_t(enum.IntEnum):
    # enum class control_event_t : uint8_t
    CONTROL_EVENT_ERROR = 0
    CONTROL_MODE_CHANGED = 1
    CONTROL_CONFIG_CHANGED = 2
    VIC_CHANGED = 3
    TIC_CHANGED = 4
    PSI_CHANGED = 5


# =============================================================================
# Small helpers for dataclasses (keep file übersichtlich)
# =============================================================================

def _float_list(n: int, value: float = 0.0) -> List[float]:
    return [float(value) for _ in range(n)]


def _require_len(name: str, arr: List[float], n: int) -> None:
    if len(arr) != n:
        raise ValueError(f"{name} must have length {n}, got {len(arr)}")


# =============================================================================
# Low-level helper structs (mirror of C++ structs)
# =============================================================================


@dataclass
class bilbo_control_input_ext:
    u_left: float = 0.0
    u_right: float = 0.0


class bilbo_control_input_ext_t(ctypes.Structure):
    # struct bilbo_control_input_ext_t { float u_left; float u_right; };
    _fields_ = [
        ("u_left", ctypes.c_float),
        ("u_right", ctypes.c_float),
    ]


@dataclass
class bilbo_control_output:
    u_left: float = 0.0
    u_right: float = 0.0


class bilbo_control_output_t(ctypes.Structure):
    # struct bilbo_control_output_t { float u_left; float u_right; };
    _fields_ = [
        ("u_left", ctypes.c_float),
        ("u_right", ctypes.c_float),
    ]


@dataclass
class bilbo_balancing_control_config:
    K: List[float] = field(default_factory=lambda: _float_list(8))
    pitch_offset: float = 0.0

    def __post_init__(self) -> None:
        _require_len("K", self.K, 8)


class bilbo_balancing_control_config_t(ctypes.Structure):
    # typedef struct bilbo_balancing_control_config_t { float K[8]; float pitch_offset; }
    _fields_ = [
        ("K", ctypes.c_float * 8),
        ("pitch_offset", ctypes.c_float),
    ]


@dataclass
class bilbo_balancing_control_input:
    u_1: float = 0.0
    u_2: float = 0.0


class bilbo_balancing_control_input_t(ctypes.Structure):
    # typedef struct bilbo_balancing_control_input_t { float u_1; float u_2; }
    _fields_ = [
        ("u_1", ctypes.c_float),
        ("u_2", ctypes.c_float),
    ]


@dataclass
class bilbo_balancing_control_output:
    u_1: float = 0.0
    u_2: float = 0.0


class bilbo_balancing_control_output_t(ctypes.Structure):
    # typedef struct bilbo_balancing_control_output_t { float u_1; float u_2; }
    _fields_ = [
        ("u_1", ctypes.c_float),
        ("u_2", ctypes.c_float),
    ]


# =============================================================================
# VIC / TIC (bilbo_vic_tic.h)
# =============================================================================

@dataclass
class bilbo_tic_config:
    enabled: int = 0  # uint8_t
    Ts: float = 0.0
    ki: float = 0.0
    max_torque: float = 0.0
    theta_limit: float = 0.0


class bilbo_tic_config_t(ctypes.Structure):
    # struct bilbo_tic_config_t { uint8_t enabled; float Ts; float ki; float max_torque; float theta_limit; }
    _fields_ = [
        ("enabled", ctypes.c_uint8),
        ("Ts", ctypes.c_float),
        ("ki", ctypes.c_float),
        ("max_torque", ctypes.c_float),
        ("theta_limit", ctypes.c_float),
    ]


@dataclass
class bilbo_vic_config:
    enabled: int = 0  # uint8_t
    Ts: float = 0.0
    ki: float = 0.0
    max_torque: float = 0.0
    v_limit: float = 0.0
    theta_limit: float = 0.0


class bilbo_vic_config_t(ctypes.Structure):
    # struct bilbo_vic_config_t { uint8_t enabled; float Ts; float ki; float max_torque; float v_limit; float theta_limit; }
    _fields_ = [
        ("enabled", ctypes.c_uint8),
        ("Ts", ctypes.c_float),
        ("ki", ctypes.c_float),
        ("max_torque", ctypes.c_float),
        ("v_limit", ctypes.c_float),
        ("theta_limit", ctypes.c_float),
    ]


@dataclass
class bilbo_psi_config:
    enabled: int = 0  # uint8_t
    Ts: float = 0.0
    kp: float = 0.0
    ki: float = 0.0
    max_torque: float = 0.0


class bilbo_psi_config_t(ctypes.Structure):
    # struct bilbo_psi_config_t { uint8_t enabled; float Ts; float kp; float ki; float max_torque; }
    _fields_ = [
        ("enabled", ctypes.c_uint8),
        ("Ts", ctypes.c_float),
        ("kp", ctypes.c_float),
        ("ki", ctypes.c_float),
        ("max_torque", ctypes.c_float),
    ]


# =============================================================================
# Velocity control (bilbo_velocity_control.h)
# =============================================================================
#
# NOTE: bilbo_velocity_control_config_t contains pid_control_config_t from pid.h on STM32.
# If your STM32 pid_control_config_t differs, YOU MUST update the ctypes layout below.
#

@dataclass
class pid_control_config:
    # -------- PID gains --------
    Kp: float = 0.0
    Ki: float = 0.0
    Kd: float = 0.0

    # -------- Sampling time --------
    Ts: float = 0.0

    # -------- Integrator (I-term) limit --------
    enable_i_limit: int = 0
    i_term_limit: float = 0.0

    # -------- Input saturation --------
    enable_input_limit: int = 0
    input_limit: float = 0.0

    # -------- Output saturation --------
    enable_output_limit: int = 0
    output_limit: float = 0.0

    # -------- Derivative filter --------
    enable_d_filter: int = 0
    Td_filter: float = 0.0

    # -------- Output rate limiting --------
    enable_rate_limit: int = 0
    rate_limit: float = 0.0

    # -------- Setpoint rate limiting --------
    enable_setpoint_rate_limit: int = 0
    setpoint_rate_limit: float = 0.0


class pid_control_config_t(ctypes.Structure):
    """
    Exact mirror of the C++ pid_control_config_t struct.
    Field order and types must not be changed.
    """
    _fields_ = [
        ("Kp", ctypes.c_float),
        ("Ki", ctypes.c_float),
        ("Kd", ctypes.c_float),

        ("Ts", ctypes.c_float),

        ("enable_i_limit", ctypes.c_uint8),
        ("i_term_limit", ctypes.c_float),

        ("enable_input_limit", ctypes.c_uint8),
        ("input_limit", ctypes.c_float),

        ("enable_output_limit", ctypes.c_uint8),
        ("output_limit", ctypes.c_float),

        ("enable_d_filter", ctypes.c_uint8),
        ("Td_filter", ctypes.c_float),

        ("enable_rate_limit", ctypes.c_uint8),
        ("rate_limit", ctypes.c_float),

        ("enable_setpoint_rate_limit", ctypes.c_uint8),
        ("setpoint_rate_limit", ctypes.c_float),
    ]


@dataclass
class feedforward_config:
    # ---- gains ----
    Kv: float = 0.0
    Ka: float = 0.0
    Kc: float = 0.0

    Ts: float = 0.0

    # ---- v_ref slew rate limiting ----
    enable_vref_slew: int = 0
    vref_slew_rate: float = 0.0

    # ---- derivative filtering ----
    enable_a_filter: int = 0
    Ta_filter: float = 0.0

    # ---- stiction smoothing ----
    enable_stiction: int = 0
    v0_stiction: float = 0.0
    v_decay_stiction: float = 0.0

    # ---- output saturation ----
    enable_output_limit: int = 0
    output_limit: float = 0.0

    # ---- output slew-rate limit ----
    enable_output_slew: int = 0
    output_slew_rate: float = 0.0


class feedforward_config_t(ctypes.Structure):
    _fields_ = [
        ("Kv", ctypes.c_float),
        ("Ka", ctypes.c_float),
        ("Kc", ctypes.c_float),

        ("Ts", ctypes.c_float),

        ("enable_vref_slew", ctypes.c_uint8),
        ("vref_slew_rate", ctypes.c_float),

        ("enable_a_filter", ctypes.c_uint8),
        ("Ta_filter", ctypes.c_float),

        ("enable_stiction", ctypes.c_uint8),
        ("v0_stiction", ctypes.c_float),
        ("v_decay_stiction", ctypes.c_float),

        ("enable_output_limit", ctypes.c_uint8),
        ("output_limit", ctypes.c_float),

        ("enable_output_slew", ctypes.c_uint8),
        ("output_slew_rate", ctypes.c_float),
    ]


@dataclass
class bilbo_velocity_control_config:
    pid_config_v: pid_control_config = field(default_factory=pid_control_config)
    ff_config_v: feedforward_config = field(default_factory=feedforward_config)
    pid_config_psi_dot: pid_control_config = field(default_factory=pid_control_config)
    ff_config_psi_dot: feedforward_config = field(default_factory=feedforward_config)


class bilbo_velocity_control_config_t(ctypes.Structure):
    _fields_ = [
        ("pid_config_v", pid_control_config_t),
        ("ff_config_v", feedforward_config_t),
        ("pid_config_psi_dot", pid_control_config_t),
        ("ff_config_psi_dot", feedforward_config_t),
    ]


@dataclass
class bilbo_velocity_control_command:
    v: float = 0.0
    psi_dot: float = 0.0


class bilbo_velocity_control_command_t(ctypes.Structure):
    # struct bilbo_velocity_control_command_t { float v; float psi_dot; };
    _fields_ = [
        ("v", ctypes.c_float),
        ("psi_dot", ctypes.c_float),
    ]


@dataclass
class bilbo_velocity_control_output:
    u_l: float = 0.0
    u_r: float = 0.0


class bilbo_velocity_control_output_t(ctypes.Structure):
    # struct bilbo_velocity_control_output_t { float u_l; float u_r; };
    _fields_ = [
        ("u_l", ctypes.c_float),
        ("u_r", ctypes.c_float),
    ]


@dataclass
class bilbo_velocity_control_sample:
    v_meas: float = 0.0
    psi_dot_meas: float = 0.0
    output: bilbo_velocity_control_output = field(default_factory=bilbo_velocity_control_output)
    command: bilbo_velocity_control_command = field(default_factory=bilbo_velocity_control_command)


class bilbo_velocity_control_sample_t(ctypes.Structure):
    # struct bilbo_velocity_control_sample_t { float v_meas; float psi_dot_meas; output; command; };
    _fields_ = [
        ("v_meas", ctypes.c_float),
        ("psi_dot_meas", ctypes.c_float),
        ("output", bilbo_velocity_control_output_t),
        ("command", bilbo_velocity_control_command_t),
    ]


# =============================================================================
# Position control (bilbo_position_control.h) - NEW PATH FOLLOWING IMPLEMENTATION
# =============================================================================

# --- Position state (from bilbo_estimation.h) ---

@dataclass
class bilbo_position_state:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0


class bilbo_position_state_t(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("psi", ctypes.c_float),
    ]


# --- Path point definition (dense path representation) ---

@dataclass
class path_point:
    """Single path point (x, y)"""
    x: float = 0.0   # [m] world X coordinate
    y: float = 0.0   # [m] world Y coordinate


class path_point_t(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
    ]


BATCH_SIZE = 10


class path_points_batch_t(ctypes.Structure):
    _fields_ = [
        ("start_index", ctypes.c_uint16),
        ("count", ctypes.c_uint16),
        ("points", path_point_t * BATCH_SIZE),
    ]


# --- Path start command ---

@dataclass
class bilbo_path_start_cmd:
    """Command to start path execution"""
    max_speed: float = 0.0      # [m/s] Speed override, 0 = use config default
    max_spacing: float = 0.0    # [m] Max inter-point spacing, 0 = auto-detect
    timeout: float = 0.0        # [s] Maximum time for path execution, 0 = no timeout
    allow_reverse: int = 0      # If non-zero, robot may drive backwards when more efficient


class bilbo_path_start_cmd_t(ctypes.Structure):
    _fields_ = [
        ("max_speed", ctypes.c_float),
        ("max_spacing", ctypes.c_float),
        ("timeout", ctypes.c_float),
        ("allow_reverse", ctypes.c_uint8),
    ]


# --- Turn to heading command ---

@dataclass
class turn_to_heading_command:
    """Command for turn-to-heading mode"""
    id: int = 0                     # command ID for tracking
    heading_ref: float = 0.0        # [rad] target heading
    timeout: float = 0.0            # [s] command timeout (0 = no timeout)
    max_angular_speed: float = 0.0  # [rad/s] maximum angular speed (0 = use config)


class turn_to_heading_command_t(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint8),
        ("heading_ref", ctypes.c_float),
        ("timeout", ctypes.c_float),
        ("max_angular_speed", ctypes.c_float),
    ]


# --- Move to point command ---

@dataclass
class move_to_point_command:
    """Command for drive-to-point mode"""
    id: int = 0                 # command ID for tracking
    x_target: float = 0.0       # [m] target X position
    y_target: float = 0.0       # [m] target Y position
    timeout: float = 0.0        # [s] command timeout (0 = no timeout)
    max_speed: float = 0.0      # [m/s] maximum forward speed (0 = use config)


class move_to_point_command_t(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint8),
        ("x_target", ctypes.c_float),
        ("y_target", ctypes.c_float),
        ("timeout", ctypes.c_float),
        ("max_speed", ctypes.c_float),
    ]


# --- Position control output ---

@dataclass
class bilbo_position_control_output:
    v_cmd: float = 0.0          # [m/s] forward velocity command
    psi_dot_cmd: float = 0.0    # [rad/s] yaw rate command


class bilbo_position_control_output_t(ctypes.Structure):
    _fields_ = [
        ("v_cmd", ctypes.c_float),
        ("psi_dot_cmd", ctypes.c_float),
    ]


# --- Position control configuration ---

@dataclass
class bilbo_position_control_config:
    """Configuration parameters for position control (dense path following)

    Dense path tracking with adaptive speed from sample spacing:
    - Speed derived from local inter-point spacing (tight curves = slow)
    - Adaptive lookahead = v_target / kp_linear
    - Reverse mode optional per-path
    """

    # Timing
    Ts: float = 0.01                        # [s] Update period (100 Hz = 0.01s)

    # Angular control gains
    kp_angular: float = 10.0                # [rad/s per rad] Proportional gain
    ki_angular: float = 0.3                 # [rad/s per rad*s] Integral gain

    # Heading-only angular gains (turn_to_heading override)
    kp_angular_heading: float = 0.0         # [rad/s per rad] Heading-only kp (0 = use kp_angular)
    ki_angular_heading: float = 0.0         # [rad/s per rad*s] Heading-only ki (0 = use ki_angular)

    # Linear control gains (speed toward carrot)
    kp_linear: float = 2.0                  # [1/s] speed = kp_linear * carrot_distance
    ki_linear: float = 0.0                  # [1/s^2] Integral gain (usually 0)
    kd_linear: float = 0.5                  # [-] Velocity damping

    # Speed limits
    max_speed: float = 0.5                  # [m/s] Maximum forward velocity
    max_turn_rate: float = 5.0              # [rad/s] Maximum yaw rate

    # Lookahead parameters
    lookahead_base: float = 0.15            # [m] Base lookahead (used by move_to_point)
    lookahead_min: float = 0.03             # [m] Minimum lookahead for path following

    # Arrival and dwell
    arrival_tolerance: float = 0.05         # [m] Distance to consider "arrived"
    arrival_dwell_time: float = 0.5         # [s] Hold time at STOP point / path end

    # Reverse mode
    reverse_enter_angle: float = 2.1        # [rad] ~120 deg - enter reverse mode
    reverse_exit_angle: float = 1.05        # [rad] ~60 deg - exit reverse mode

    # Deceleration
    decel_limit: float = 0.0               # [m/s²] sqrt decel profile. 0 = disabled


class bilbo_position_control_config_t(ctypes.Structure):
    _fields_ = [
        ("Ts", ctypes.c_float),
        ("kp_angular", ctypes.c_float),
        ("ki_angular", ctypes.c_float),
        ("kp_angular_heading", ctypes.c_float),
        ("ki_angular_heading", ctypes.c_float),
        ("kp_linear", ctypes.c_float),
        ("ki_linear", ctypes.c_float),
        ("kd_linear", ctypes.c_float),
        ("max_speed", ctypes.c_float),
        ("max_turn_rate", ctypes.c_float),
        ("lookahead_base", ctypes.c_float),
        ("lookahead_min", ctypes.c_float),
        ("arrival_tolerance", ctypes.c_float),
        ("arrival_dwell_time", ctypes.c_float),
        ("stop_dwell_time", ctypes.c_float),
        ("reverse_enter_angle", ctypes.c_float),
        ("reverse_exit_angle", ctypes.c_float),
        ("decel_limit", ctypes.c_float),
        ("curvature_gain", ctypes.c_float),
        ("curvature_lookahead", ctypes.c_float),
    ]


# --- Position control telemetry data ---

@dataclass
class bilbo_position_control_data:
    """Telemetry and debug data from position control"""
    mode: bilbo_position_control_mode_t = bilbo_position_control_mode_t.IDLE
    path_state: bilbo_path_state_t = bilbo_path_state_t.IDLE

    # Buffer status
    buffer_capacity: int = 0            # maximum path points the buffer can hold
    buffer_used: int = 0                # current number of path points in buffer

    # Path progress
    path_point_count: int = 0           # total path points in path
    current_index: int = 0              # current path index (floor of progress)

    # Carrot (lookahead) position
    carrot_x: float = 0.0               # [m] current carrot X
    carrot_y: float = 0.0               # [m] current carrot Y
    carrot_distance: float = 0.0        # [m] distance from robot to carrot

    # Control state
    heading_error: float = 0.0          # [rad] heading error to carrot
    speed_limit: float = 0.0            # [m/s] current speed limit

    # Output
    output: bilbo_position_control_output = field(default_factory=bilbo_position_control_output)

    # Timing
    elapsed_time: float = 0.0           # [s] time since path started
    remaining_path_length: float = 0.0  # [m] approximate remaining distance

    # Dense path progress
    progress: float = 0.0               # floating-point index [0, N-1]


class bilbo_position_control_data_t(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_uint8),
        ("path_state", ctypes.c_uint8),
        ("buffer_capacity", ctypes.c_uint16),
        ("buffer_used", ctypes.c_uint16),
        ("path_point_count", ctypes.c_uint16),
        ("current_index", ctypes.c_uint16),
        ("carrot_x", ctypes.c_float),
        ("carrot_y", ctypes.c_float),
        ("carrot_distance", ctypes.c_float),
        ("heading_error", ctypes.c_float),
        ("speed_limit", ctypes.c_float),
        ("output", bilbo_position_control_output_t),
        ("elapsed_time", ctypes.c_float),
        ("remaining_path_length", ctypes.c_float),
        ("progress", ctypes.c_float),
    ]


# --- Position control event data ---

@dataclass
class position_control_event_data:
    """Event message data from position control"""
    event: position_control_event_t = position_control_event_t.PATH_STARTED
    data: bilbo_position_control_data = field(default_factory=bilbo_position_control_data)
    tick: int = 0
    waypoint_index: int = 0     # index of waypoint for waypoint events
    command_id: int = 0         # command ID for single-point commands


class position_control_event_data_t(ctypes.Structure):
    _fields_ = [
        ("event", ctypes.c_uint8),
        ("data", bilbo_position_control_data_t),
        ("tick", ctypes.c_uint32),
        ("waypoint_index", ctypes.c_uint16),
        ("command_id", ctypes.c_uint8),
    ]


# =============================================================================
# Top-level BILBO control config/data (bilbo_control.h)
# =============================================================================

@dataclass
class bilbo_control_config:
    state_feedback_gain: List[float] = field(default_factory=lambda: _float_list(8))
    tic_config: bilbo_tic_config = field(default_factory=bilbo_tic_config)
    vic_config: bilbo_vic_config = field(default_factory=bilbo_vic_config)
    psi_config: bilbo_psi_config = field(default_factory=bilbo_psi_config)
    velocity_control_config: bilbo_velocity_control_config = field(default_factory=bilbo_velocity_control_config)
    position_control_config: bilbo_position_control_config = field(default_factory=bilbo_position_control_config)
    max_torque: float = 0.0

    def __post_init__(self) -> None:
        _require_len("state_feedback_gain", self.state_feedback_gain, 8)


class bilbo_control_config_t(ctypes.Structure):
    # struct bilbo_control_config_t {
    #   float state_feedback_gain[8];
    #   bilbo_tic_config_t tic_config;
    #   bilbo_vic_config_t vic_config;
    #   bilbo_psi_config_t psi_config;
    #   bilbo_velocity_control_config_t velocity_control_config;
    #   bilbo_position_control_config_t position_control_config;
    #   float max_torque;
    # };
    _fields_ = [
        ("state_feedback_gain", ctypes.c_float * 8),
        ("tic_config", bilbo_tic_config_t),
        ("vic_config", bilbo_vic_config_t),
        ("psi_config", bilbo_psi_config_t),
        ("velocity_control_config", bilbo_velocity_control_config_t),
        ("position_control_config", bilbo_position_control_config_t),
        ("max_torque", ctypes.c_float),
    ]


@dataclass
class bilbo_ll_control_data:
    mode: int = 0
    status: int = 0

    vic_enabled: int = 0
    tic_enabled: int = 0
    psi_enabled: int = 0

    position_control_data: bilbo_position_control_data = field(default_factory=bilbo_position_control_data)

    velocity_command: bilbo_velocity_control_command = field(default_factory=bilbo_velocity_control_command)
    velocity_output: bilbo_velocity_control_output = field(default_factory=bilbo_velocity_control_output)

    input_ext: bilbo_control_input_ext = field(default_factory=bilbo_control_input_ext)
    balancing_output: bilbo_balancing_control_output = field(default_factory=bilbo_balancing_control_output)

    output: bilbo_control_output = field(default_factory=bilbo_control_output)


class bilbo_ll_control_data_t(ctypes.Structure):
    # struct bilbo_control_data_t { ... }  (see bilbo_control.h)
    _fields_ = [
        ("mode", ctypes.c_uint8),
        ("status", ctypes.c_int8),

        ("vic_enabled", ctypes.c_uint8),
        ("tic_enabled", ctypes.c_uint8),
        ("psi_enabled", ctypes.c_uint8),

        ("position_control_data", bilbo_position_control_data_t),

        ("velocity_command", bilbo_velocity_control_command_t),
        ("velocity_output", bilbo_velocity_control_output_t),

        ("input_ext", bilbo_control_input_ext_t),
        ("balancing_output", bilbo_balancing_control_output_t),

        ("output", bilbo_control_output_t),
    ]

# =============================================================================
# MESSAGES
# =============================================================================
class control_event_message_data_t(ctypes.Structure):
    _fields_ = [
        ("event", ctypes.c_uint8),
        ("mode", ctypes.c_uint8),
        ("data", bilbo_ll_control_data_t),
        ("tick", ctypes.c_uint32)
    ]


class BILBO_Control_Event_Message(SerialMessage):
    module = 1
    address = BILBO_LL_MESSAGE_CONTROL_EVENT
    command = SerialCommandType.UART_CMD_EVENT
    data_type = control_event_message_data_t


class BILBO_PositionControl_Event_Message(SerialMessage):
    """Message for position control events (path following, turn-to-heading, drive-to-point)"""
    module = 1
    address = BILBO_LL_MESSAGE_POSITION_CONTROL_EVENT
    command = SerialCommandType.UART_CMD_EVENT
    data_type = position_control_event_data_t



