"""
Simulated firmware control algorithms.

Replicates the STM32 firmware control hierarchy:
  - PID controller (with all options: D-filter, rate limiting, setpoint slew, anti-windup)
  - Feedforward controller (Kv, Ka, Kc with stiction model)
  - LQR balancing (8-gain state feedback)
  - Velocity control (PID + FF for forward v and yaw rate psi_dot)
  - TIC / VIC integral augmentation
"""
from __future__ import annotations

import dataclasses
import math


# =============================================================================
# PID Controller  (mirrors firmware pid.h)
# =============================================================================
@dataclasses.dataclass
class PIDConfig:
    Kp: float = 0.0
    Ki: float = 0.0
    Kd: float = 0.0
    Ts: float = 0.01
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


class PIDController:
    def __init__(self, config: PIDConfig | None = None):
        self.config = config or PIDConfig()
        self.reset()

    def reset(self):
        self._i_term = 0.0
        self._error_last = 0.0
        self._d_error_filt = 0.0
        self._last_output = 0.0
        self._setpoint_limited = 0.0

    def update(self, setpoint: float, measurement: float) -> float:
        c = self.config
        Ts = c.Ts

        # Setpoint rate limiting
        if c.enable_setpoint_rate_limit and c.setpoint_rate_limit > 0:
            delta = setpoint - self._setpoint_limited
            max_delta = c.setpoint_rate_limit * Ts
            delta = max(-max_delta, min(max_delta, delta))
            self._setpoint_limited += delta
        else:
            self._setpoint_limited = setpoint

        # Error
        error = self._setpoint_limited - measurement

        # Input saturation
        if c.enable_input_limit and c.input_limit > 0:
            error = max(-c.input_limit, min(c.input_limit, error))

        # P term
        p_term = c.Kp * error

        # I term
        self._i_term += c.Ki * error * Ts
        if c.enable_i_limit and c.i_term_limit > 0:
            self._i_term = max(-c.i_term_limit, min(c.i_term_limit, self._i_term))

        # D term with optional filter
        d_error = error - self._error_last
        if c.enable_d_filter and c.Td_filter > 0:
            alpha = Ts / (Ts + c.Td_filter)
            self._d_error_filt += (d_error - self._d_error_filt) * alpha
        else:
            self._d_error_filt = d_error
        d_term = c.Kd * self._d_error_filt / Ts if Ts > 0 else 0.0
        self._error_last = error

        # Combine
        output = p_term + self._i_term + d_term

        # Output saturation
        if c.enable_output_limit and c.output_limit > 0:
            output = max(-c.output_limit, min(c.output_limit, output))

        # Output rate limiting
        if c.enable_rate_limit and c.rate_limit > 0:
            max_delta = c.rate_limit * Ts
            delta = output - self._last_output
            delta = max(-max_delta, min(max_delta, delta))
            output = self._last_output + delta

        self._last_output = output
        return output

    def set_config(self, config: PIDConfig):
        self.config = config
        self.reset()


# =============================================================================
# Feedforward Controller  (mirrors firmware feedforward.h)
# =============================================================================
@dataclasses.dataclass
class FeedforwardConfig:
    Kv: float = 0.0
    Ka: float = 0.0
    Kc: float = 0.0
    Ts: float = 0.01
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


class FeedforwardController:
    def __init__(self, config: FeedforwardConfig | None = None):
        self.config = config or FeedforwardConfig()
        self.reset()

    def reset(self):
        self._vref_last = 0.0
        self._dvref_dt = 0.0
        self._last_output = 0.0

    def update(self, v_ref: float) -> float:
        c = self.config
        Ts = c.Ts

        # Reference slew limiting
        if c.enable_vref_slew and c.vref_slew_rate > 0:
            delta = v_ref - self._vref_last
            max_delta = c.vref_slew_rate * Ts
            delta = max(-max_delta, min(max_delta, delta))
            v_ref_limited = self._vref_last + delta
        else:
            v_ref_limited = v_ref

        # Acceleration estimate
        if Ts > 0:
            dv_dt = (v_ref_limited - self._vref_last) / Ts
        else:
            dv_dt = 0.0
        self._vref_last = v_ref_limited

        if c.enable_a_filter and c.Ta_filter > 0:
            alpha = Ts / (Ts + c.Ta_filter)
            self._dvref_dt += (dv_dt - self._dvref_dt) * alpha
        else:
            self._dvref_dt = dv_dt

        # Velocity term
        tau_v = c.Kv * v_ref_limited

        # Acceleration term
        tau_a = c.Ka * self._dvref_dt

        # Stiction / Coulomb term
        tau_c = 0.0
        if c.enable_stiction and c.Kc != 0 and c.v0_stiction > 0:
            smooth_sign = math.tanh(v_ref_limited / c.v0_stiction)
            if c.v_decay_stiction > 0:
                velocity_factor = 1.0 - math.exp(-abs(v_ref_limited) / c.v_decay_stiction)
            else:
                velocity_factor = 1.0
            tau_c = c.Kc * smooth_sign * velocity_factor

        output = tau_v + tau_a + tau_c

        # Output saturation
        if c.enable_output_limit and c.output_limit > 0:
            output = max(-c.output_limit, min(c.output_limit, output))

        # Output slew rate
        if c.enable_output_slew and c.output_slew_rate > 0:
            max_delta = c.output_slew_rate * Ts
            delta = output - self._last_output
            delta = max(-max_delta, min(max_delta, delta))
            output = self._last_output + delta

        self._last_output = output
        return output

    def set_config(self, config: FeedforwardConfig):
        self.config = config
        self.reset()


# =============================================================================
# TIC - Theta Integral Control
# =============================================================================
@dataclasses.dataclass
class TICConfig:
    enabled: bool = False
    Ts: float = 0.01
    ki: float = 0.0
    max_torque: float = 0.0
    theta_limit: float = 0.0


class TICController:
    def __init__(self, config: TICConfig | None = None):
        self.config = config or TICConfig()
        self._integral = 0.0
        self.active = False

    def reset(self):
        self._integral = 0.0

    def update(self, theta: float) -> float:
        c = self.config
        if not c.enabled:
            self.active = False
            return 0.0

        # Safety: disable if pitch exceeds limit
        if c.theta_limit > 0 and abs(theta) > c.theta_limit:
            self.reset()
            self.active = False
            return 0.0

        self.active = True
        self._integral += c.ki * theta * c.Ts

        if c.max_torque > 0:
            self._integral = max(-c.max_torque, min(c.max_torque, self._integral))

        return self._integral


# =============================================================================
# VIC - Velocity Integral Control
# =============================================================================
@dataclasses.dataclass
class VICConfig:
    enabled: bool = False
    Ts: float = 0.01
    ki: float = 0.0
    max_torque: float = 0.0
    v_limit: float = 0.0
    theta_limit: float = 0.0


class VICController:
    def __init__(self, config: VICConfig | None = None):
        self.config = config or VICConfig()
        self._integral = 0.0
        self.active = False

    def reset(self):
        self._integral = 0.0

    def update(self, velocity: float, theta: float) -> float:
        c = self.config
        if not c.enabled:
            self.active = False
            return 0.0

        if c.v_limit > 0 and abs(velocity) > c.v_limit:
            self.reset()
            self.active = False
            return 0.0

        if c.theta_limit > 0 and abs(theta) > c.theta_limit:
            self.reset()
            self.active = False
            return 0.0

        self.active = True
        self._integral += c.ki * velocity * c.Ts

        if c.max_torque > 0:
            self._integral = max(-c.max_torque, min(c.max_torque, self._integral))

        return self._integral


# =============================================================================
# Balancing Control (LQR state feedback)
# =============================================================================
class BalancingController:
    """LQR balancing: u = K * [v, theta, theta_dot, psi_dot] + external_input.

    K is 8 elements: K[0:4] for left motor, K[4:8] for right motor.
    State order: [v, theta, theta_dot, psi_dot].
    """

    def __init__(self):
        self.K = [0.0] * 8

    def set_K(self, K: list[float]):
        assert len(K) == 8
        self.K = list(K)

    def update(self, v: float, theta: float, theta_dot: float, psi_dot: float,
               ext_left: float = 0.0, ext_right: float = 0.0) -> tuple[float, float]:
        state = [v, theta, theta_dot, psi_dot]
        u_left = sum(self.K[i] * state[i] for i in range(4)) + ext_left
        u_right = sum(self.K[i + 4] * state[i] for i in range(4)) + ext_right
        return u_left, u_right


# =============================================================================
# Velocity Control (PID + FF for v and psi_dot)
# =============================================================================
@dataclasses.dataclass
class VelocityControlOutput:
    u_left: float = 0.0
    u_right: float = 0.0
    v_meas: float = 0.0
    psi_dot_meas: float = 0.0
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0


class VelocityController:
    """Two-channel velocity controller: forward v and yaw rate psi_dot.

    Each channel has PID + feedforward. Outputs are mixed to left/right torques.
    """

    def __init__(self, Ts: float = 0.01):
        self.Ts = Ts
        self.pid_v = PIDController(PIDConfig(Ts=Ts))
        self.ff_v = FeedforwardController(FeedforwardConfig(Ts=Ts))
        self.pid_psidot = PIDController(PIDConfig(Ts=Ts))
        self.ff_psidot = FeedforwardController(FeedforwardConfig(Ts=Ts))

    def reset(self):
        self.pid_v.reset()
        self.ff_v.reset()
        self.pid_psidot.reset()
        self.ff_psidot.reset()

    def update(self, v_cmd: float, psi_dot_cmd: float,
               v_meas: float, psi_dot_meas: float) -> VelocityControlOutput:
        # Forward velocity channel
        u_forward = self.pid_v.update(v_cmd, v_meas) + self.ff_v.update(v_cmd)

        # Yaw rate channel
        u_turn = self.pid_psidot.update(psi_dot_cmd, psi_dot_meas) + self.ff_psidot.update(psi_dot_cmd)

        # Mix to left/right (left = forward - turn, right = forward + turn)
        u_left = u_forward - u_turn
        u_right = u_forward + u_turn

        return VelocityControlOutput(
            u_left=u_left,
            u_right=u_right,
            v_meas=v_meas,
            psi_dot_meas=psi_dot_meas,
            v_cmd=v_cmd,
            psi_dot_cmd=psi_dot_cmd,
        )
