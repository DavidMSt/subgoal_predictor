# stm32_control.py
#
# ctypes mirror of the STM32-side control types (BILBO / TWIPR)
# Based on:
#   - bilbo_control.h
#   - twipr_balancing_control.h
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

from core.utils.ctypes_utils import STRUCTURE


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


class twipr_balancing_control_mode_t(enum.IntEnum):
    # enum class twipr_balancing_control_mode_t : uint8_t
    OFF = 0
    DIRECT = 1
    ON = 2


class twipr_balancing_control_status_t(enum.IntEnum):
    # enum class twipr_balancing_control_status_t : int8_t
    NONE = 0
    IDLE = 1
    ERROR = -1
    RUNNING = 2


class bilbo_position_control_mode_t(enum.IntEnum):
    # enum class bilbo_position_control_mode_t : uint8_t
    STANDALONE = 0
    VELOCITY_CASCADE = 1


class control_event_t(enum.IntEnum):
    # enum class control_event_t : uint8_t
    CONTROL_EVENT_ERROR = 0
    CONTROL_MODE_CHANGED = 1
    CONTROL_CONFIG_CHANGED = 2
    VIC_CHANGED = 3
    TIC_CHANGED = 4


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
class twipr_balancing_control_config:
    K: List[float] = field(default_factory=lambda: _float_list(8))
    pitch_offset: float = 0.0

    def __post_init__(self) -> None:
        _require_len("K", self.K, 8)


class twipr_balancing_control_config_t(ctypes.Structure):
    # typedef struct twipr_balancing_control_config_t { float K[8]; float pitch_offset; }
    _fields_ = [
        ("K", ctypes.c_float * 8),
        ("pitch_offset", ctypes.c_float),
    ]


@dataclass
class twipr_balancing_control_input:
    u_1: float = 0.0
    u_2: float = 0.0


class twipr_balancing_control_input_t(ctypes.Structure):
    # typedef struct twipr_balancing_control_input_t { float u_1; float u_2; }
    _fields_ = [
        ("u_1", ctypes.c_float),
        ("u_2", ctypes.c_float),
    ]


@dataclass
class twipr_balancing_control_output:
    u_1: float = 0.0
    u_2: float = 0.0


class twipr_balancing_control_output_t(ctypes.Structure):
    # typedef struct twipr_balancing_control_output_t { float u_1; float u_2; }
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
# Position control (bilbo_position_control.h)
# =============================================================================


@dataclass
class bilbo_position_control_config:
    kp_linear: float = 0.0
    ki_linear: float = 0.0
    kp_angular: float = 0.0
    ki_angular: float = 0.0
    Ts: float = 0.0
    lookahead_distance: float = 0.3
    allow_reverse: int = 1
    backwards_switch_angle: float = np.deg2rad(100.0)
    distance_arrival_tolerance: float = 0.05
    angle_arrival_tolerance: float = np.deg2rad(5.0)
    arrival_time: float = 2.0
    max_speed_forward: float = 0.75
    max_speed_turn: float = 3


class bilbo_position_control_config_t(ctypes.Structure):
    # struct bilbo_position_control_config_t { ... }  (see header)
    _fields_ = [
        ("kp_linear", ctypes.c_float),
        ("ki_linear", ctypes.c_float),
        ("kp_angular", ctypes.c_float),
        ("ki_angular", ctypes.c_float),
        ("Ts", ctypes.c_float),
        ("lookahead_distance", ctypes.c_float),
        ("allow_reverse", ctypes.c_uint8),
        ("backwards_switch_angle", ctypes.c_float),
        ("distance_arrival_tolerance", ctypes.c_float),
        ("angle_arrival_tolerance", ctypes.c_float),
        ("arrival_time", ctypes.c_float),
        ("max_speed_forward", ctypes.c_float),
        ("max_speed_turn", ctypes.c_float),
    ]


@dataclass
class bilbo_position_control_output:
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0


class bilbo_position_control_output_t(ctypes.Structure):
    # struct bilbo_position_control_output_t { float u_l; float u_r; };
    _fields_ = [
        ("v_cmd", ctypes.c_float),
        ("psi_dot_cmd", ctypes.c_float),
    ]


@dataclass
class bilbo_position_state:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0


class bilbo_position_state_t(ctypes.Structure):
    # referenced in C++ (from twipr_estimation.h)
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("psi", ctypes.c_float),
    ]



@dataclass
class heading_reference:
    psi_cmd: float = 0.0

class heading_reference_t(ctypes.Structure):
    _fields_ = [
        ("psi_cmd", ctypes.c_float),
    ]

@dataclass
class heading_command:
    id: int = 0
    heading_ref: heading_reference = field(default_factory=heading_reference)
    max_angular_speed: float = -1.0
    timeout: float = 0


class heading_command_t(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint16),
        ("heading_ref", heading_reference_t),
        ("max_angular_speed", ctypes.c_float),
        ("timeout", ctypes.c_float),
    ]


@dataclass
class position_reference:
    x_target: float = 0.0
    y_target: float = 0.0


class position_reference_t(ctypes.Structure):
    _fields_ = [
        ("x_target", ctypes.c_float),
        ("y_target", ctypes.c_float),
    ]


@dataclass
class position_command:
    id: int = 0
    position_ref: position_reference = field(default_factory=position_reference)
    max_speed: float = -1.0
    timeout: float = 0


class position_command_t(ctypes.Structure):
    # struct position_command_t { uint16_t id; position_reference_t position_ref; float max_speed; };
    _fields_ = [
        ("id", ctypes.c_uint16),
        ("position_ref", position_reference_t),
        ("max_speed", ctypes.c_float),
        ("timeout", ctypes.c_float),
    ]


class position_control_mode(enum.IntEnum):
    NONE = 0
    POSITION = 1
    ANGLE = 2


@dataclass
class bilbo_position_control_data:
    current_mode: position_control_mode = position_control_mode.NONE
    current_position_command: position_command = field(default_factory=position_command)
    current_heading_command: heading_command = field(default_factory=heading_command)
    current_output: bilbo_position_control_output = field(default_factory=bilbo_position_control_output)
    is_executing_command: int = 0


class bilbo_position_control_data_t(ctypes.Structure):
    _fields_ = [
        ("current_mode", ctypes.c_uint8),
        ("current_position_command", position_command_t),
        ("current_heading_command", heading_command_t),
        ("current_output", bilbo_position_control_output_t),
        ("is_executing_command", ctypes.c_uint8),
    ]


# =============================================================================
# Top-level BILBO control config/data (bilbo_control.h)
# =============================================================================

@dataclass
class bilbo_control_config:
    state_feedback_gain: List[float] = field(default_factory=lambda: _float_list(8))
    tic_config: bilbo_tic_config = field(default_factory=bilbo_tic_config)
    vic_config: bilbo_vic_config = field(default_factory=bilbo_vic_config)
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
    #   bilbo_velocity_control_config_t velocity_control_config;
    #   bilbo_position_control_config_t position_control_config;
    #   float max_torque;
    # };
    _fields_ = [
        ("state_feedback_gain", ctypes.c_float * 8),
        ("tic_config", bilbo_tic_config_t),
        ("vic_config", bilbo_vic_config_t),
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

    position_control_data: bilbo_position_control_data = field(default_factory=bilbo_position_control_data)
    position_output: bilbo_position_control_output = field(default_factory=bilbo_position_control_output)

    velocity_command: bilbo_velocity_control_command = field(default_factory=bilbo_velocity_control_command)
    velocity_output: bilbo_velocity_control_output = field(default_factory=bilbo_velocity_control_output)

    input_ext: bilbo_control_input_ext = field(default_factory=bilbo_control_input_ext)
    balancing_output: twipr_balancing_control_output = field(default_factory=twipr_balancing_control_output)

    output: bilbo_control_output = field(default_factory=bilbo_control_output)


class bilbo_ll_control_data_t(ctypes.Structure):
    # struct bilbo_control_data_t { ... }  (see bilbo_control.h)
    _fields_ = [
        ("mode", ctypes.c_uint8),
        ("status", ctypes.c_int8),

        ("vic_enabled", ctypes.c_uint8),
        ("tic_enabled", ctypes.c_uint8),

        ("position_control_data", bilbo_position_control_data_t),
        ("position_output", bilbo_position_control_output_t),

        ("velocity_command", bilbo_velocity_control_command_t),
        ("velocity_output", bilbo_velocity_control_output_t),

        ("input_ext", bilbo_control_input_ext_t),
        ("balancing_output", twipr_balancing_control_output_t),

        ("output", bilbo_control_output_t),
    ]


@dataclass
class control_event_message_data:
    event: int = 0
    mode: int = 0
    data: bilbo_ll_control_data = field(default_factory=bilbo_ll_control_data)
    config: bilbo_control_config = field(default_factory=bilbo_control_config)
    tick: int = 0


class control_event_message_data_t(ctypes.Structure):
    # typedef struct control_event_message_data_t {
    #   control_event_t event;
    #   bilbo_control_mode_t mode;
    #   bilbo_control_data_t data;
    #   bilbo_control_config_t config;
    #   uint32_t tick;
    # } control_event_message_data_t;
    _fields_ = [
        ("event", ctypes.c_uint8),
        ("mode", ctypes.c_uint8),
        ("data", bilbo_ll_control_data_t),
        ("config", bilbo_control_config_t),
        ("tick", ctypes.c_uint32),
    ]


# =============================================================================
# Backwards-compat convenience types (optional)
# =============================================================================

BILBO_Control_Mode_LL = bilbo_control_mode_t
BILBO_Control_Status_LL = bilbo_control_status_t
BilboPositionControlMode = bilbo_position_control_mode_t


# =============================================================================
# Legacy STRUCTURE-based definitions (kept only if you rely on that decorator)
# =============================================================================

@STRUCTURE
class bilbo_control_external_input_t:
    """
    Updated external input to match bilbo_control_input_ext_t from STM32:
      struct bilbo_control_input_ext_t { float u_left; float u_right; };

    If you truly need the old multi-field external input, keep it under a different name
    and do NOT send it to the STM32 expecting the new firmware struct layout.
    """
    FIELDS = [
        ("u_left", ctypes.c_float),
        ("u_right", ctypes.c_float),
    ]
