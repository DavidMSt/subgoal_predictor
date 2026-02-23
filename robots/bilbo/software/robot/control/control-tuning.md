# BILBO Control Tuning Guide

This document describes the full control hierarchy of the BILBO two-wheel inverted pendulum robot, covering every tunable parameter, its physical meaning, units, default value, and what value disables it.

## Control Hierarchy Overview

The control system is a four-layer cascade. Each layer generates commands for the layer below it:

```
POSITION CONTROL  (x, y) → (v, psi_dot)
        ↓
VELOCITY CONTROL  (v, psi_dot) → pitch/yaw offsets
        ↓
BALANCING CONTROL  state feedback → (tau_left, tau_right)
        ↓
MOTOR OUTPUT
```

**Control modes** select which layers are active:

| Mode       | Value | Active Layers                   |
|------------|-------|---------------------------------|
| `OFF`      | 0     | None (motors disabled)          |
| `DIRECT`   | 1     | Raw torque passthrough          |
| `BALANCING`| 2     | Balancing only                  |
| `VELOCITY` | 3     | Velocity + Balancing            |
| `POSITION` | 4     | Position + Velocity + Balancing |

Modes must be entered in order: OFF -> BALANCING -> VELOCITY -> POSITION. You cannot jump from OFF to VELOCITY.

---

## 1. Balancing Control (LQR State Feedback)

The innermost active loop. Uses a state feedback gain matrix `K` (8 elements) to keep the robot upright.

### Control Law

```
u_left  = K[0]*v + K[1]*theta + K[2]*theta_dot + K[3]*psi_dot + u_ext_left
u_right = K[4]*v + K[5]*theta + K[6]*theta_dot + K[7]*psi_dot + u_ext_right
```

### State Variables

| Index | State       | Symbol  | Unit  | Role                                  |
|-------|-------------|---------|-------|---------------------------------------|
| 0, 4  | Velocity    | v       | m/s   | Forward velocity damping              |
| 1, 5  | Pitch angle | theta   | rad   | Primary balance term (most critical)  |
| 2, 6  | Pitch rate  | theta_dot | rad/s | Derivative damping                  |
| 3, 7  | Yaw rate    | psi_dot | rad/s | Differential steering (opposite sign) |

### Default

```yaml
K: [0.25, 0.2, 0.03, 0.025, 0.25, 0.2, 0.03, -0.025]
```

Note K[3] and K[7] have opposite signs — this creates differential torque for yaw.

### Disabling

Setting all K values to 0 disables balancing. The robot will fall.

### Tuning Notes

- K[1], K[5] are the most critical (pitch stabilization). Too low → falls, too high → oscillation.
- K[0], K[4] add velocity damping. Increase if the robot drifts when you don't want it to.
- K[2], K[6] are derivative terms. Increase to damp pitch oscillation.
- K[3], K[7] control yaw coupling. The sign difference creates steering.
- These are typically designed via LQR optimal control with the robot's physical model, not hand-tuned.

---

## 2. TIC (Theta Integral Controller)

Compensates for constant pitch offset (center of mass imbalance, sensor bias). Slowly integrates pitch error into a torque correction.

### Parameters

| Parameter     | Unit         | Default | Disable Value | Description                                |
|---------------|--------------|---------|---------------|--------------------------------------------|
| `enabled`     | bool         | true    | false         | Master switch                              |
| `ki`          | Nm/(rad*s)   | 0.4     | 0             | Integral gain                              |
| `max_torque`  | Nm           | 0.05    | 0             | Output saturation                          |
| `theta_limit` | rad          | 0.16    | -             | Auto-disable above this pitch (~9.2 deg)   |

### Algorithm

```
integral += ki * theta * Ts
tau_tic = clamp(integral, -max_torque, +max_torque)
```

Auto-resets when `|theta| > theta_limit` (prevents runaway during fall).

### Tuning

- Increase `ki` if the robot leans to one side when stationary.
- Decrease `ki` if you see slow oscillation building up after disturbances.
- `max_torque` limits how much correction TIC can apply. Keep small (< 0.1 Nm).
- `theta_limit` should be well below the fall angle.

---

## 3. VIC (Velocity Integral Controller)

Compensates for steady-state velocity errors near zero (friction-induced creep).

### Parameters

| Parameter     | Unit           | Default | Disable Value | Description                               |
|---------------|----------------|---------|---------------|-------------------------------------------|
| `enabled`     | bool           | true    | false         | Master switch                             |
| `ki`          | Nm/((m/s)*s)   | 0.2     | 0             | Integral gain                             |
| `max_torque`  | Nm             | 0.02    | 0             | Output saturation                         |
| `v_limit`     | m/s            | 0.05    | 0             | Only active when `|v| < v_limit`          |
| `theta_limit` | rad            | 0.16    | -             | Auto-disable above this pitch             |

### Algorithm

```
if |v| <= v_limit and |theta| <= theta_limit:
    integral += ki * v * Ts
    tau_vic = clamp(integral, -max_torque, +max_torque)
else:
    reset()
```

### Tuning

- Increase `ki` if the robot creeps when commanded to be stationary.
- `v_limit` should be small (< 0.1 m/s) so VIC doesn't interfere with intentional motion.
- If `v_limit = 0`, VIC never activates (velocity must be exactly zero).

---

## 4. Velocity Control

Controls forward velocity `v` and yaw rate `psi_dot` independently, each with **PID + Feedforward**. The velocity controller's output is a pitch angle offset that feeds into balancing control.

### 4.1 PID Controller

Standard PID with optional integrator limiting, derivative filtering, output saturation, and rate limiting.

#### Forward Velocity PID (velocity_control.v.pid)

| Parameter                   | Unit        | Default | Disable Value | Description                           |
|-----------------------------|-------------|---------|---------------|---------------------------------------|
| `Kp`                        | rad/(m/s)   | -0.00   | 0             | Proportional gain                     |
| `Ki`                        | rad/(m/s*s) | -0.02   | 0             | Integral gain                         |
| `Kd`                        | rad*s/(m/s) | -0.0    | 0             | Derivative gain                       |
| `Ts`                        | s           | 0.01    | -             | Sample time (set automatically)       |
| `enable_i_limit`            | bool        | false   | false         | Enable integral anti-windup           |
| `i_term_limit`              | float       | 0.0     | -             | Integral term saturation              |
| `enable_input_limit`        | bool        | false   | false         | Enable input saturation               |
| `input_limit`               | float       | 0.0     | -             | Input saturation value                |
| `enable_output_limit`       | bool        | false   | false         | Enable output saturation              |
| `output_limit`              | float       | 0.0     | -             | Output saturation value               |
| `enable_d_filter`           | bool        | false   | false         | Enable derivative low-pass filter     |
| `Td_filter`                 | s           | 0.0     | -             | Derivative filter time constant       |
| `enable_rate_limit`         | bool        | false   | false         | Enable output rate limiting           |
| `rate_limit`                | float       | 0.0     | -             | Output rate limit                     |
| `enable_setpoint_rate_limit`| bool        | false   | false         | Enable setpoint slew rate limiting    |
| `setpoint_rate_limit`       | float       | 0.0     | -             | Setpoint slew rate limit              |

#### Turn (psi_dot) PID (velocity_control.psidot.pid)

Same parameter structure. Defaults:

| Parameter | Default | Note                           |
|-----------|---------|--------------------------------|
| `Kp`      | 0.01    | Positive (positive yaw error → positive correction) |
| `Ki`      | 0.05    | Integral for steady turns      |
| `Kd`      | 0.0     | Usually not needed for yaw     |

#### Sign Convention

- **Forward velocity**: Positive velocity error (want faster) → need negative pitch → gains are **negative** (`Kp < 0`, `Ki < 0`).
- **Yaw rate**: Positive yaw error → positive differential torque → gains are **positive**.

#### Disabling PID

Set `Kp = Ki = Kd = 0`. The velocity controller then runs on pure feedforward.

In the default config, the forward PID has `Kp = 0`, `Ki = -0.02` — it's mainly feedforward-driven with a small integral correction.

---

### 4.2 Feedforward Controller

Predicts the torque needed for a given velocity reference, compensating for friction and inertia without waiting for error to build up.

#### Forward Velocity Feedforward (velocity_control.v.feedforward)

| Parameter           | Unit    | Default  | Disable Value | Description                                     |
|---------------------|---------|----------|---------------|-------------------------------------------------|
| `Kv`                | rad/(m/s)| -0.25   | 0             | Viscous friction compensation (proportional to speed) |
| `Ka`                | rad/(m/s^2)| -0.02 | 0             | Inertia compensation (proportional to acceleration) |
| `Kc`                | rad     | -0.0     | 0             | Coulomb/stiction friction compensation          |
| `enable_vref_slew`  | bool    | true     | false         | Enable reference velocity slew rate limiting    |
| `vref_slew_rate`    | m/s^2   | 3.0      | 0 (holds)     | Max rate of change of velocity reference        |
| `enable_a_filter`   | bool    | false    | false         | Enable low-pass filter on acceleration estimate |
| `Ta_filter`         | s       | 0.0      | -             | Filter time constant                            |
| `enable_stiction`   | bool    | true     | false         | Enable stiction compensation                    |
| `v0_stiction`       | m/s     | 0.08     | 0 (hard sign) | Tanh transition width for stiction              |
| `v_decay_stiction`  | m/s     | 0.15     | 0 (disabled)  | Stribeck decay speed                            |
| `enable_output_limit`| bool   | false    | false         | Enable output saturation                        |
| `output_limit`      | float   | 0.0      | -             | Output saturation value                         |
| `enable_output_slew`| bool    | false    | false         | Enable output slew rate limiting                |
| `output_slew_rate`  | float   | 0.0      | -             | Output slew rate limit                          |

#### Turn (psi_dot) Feedforward (velocity_control.psidot.feedforward)

Same structure, but typically minimal:

| Parameter          | Default | Note                                       |
|--------------------|---------|---------------------------------------------|
| `Kv`               | 0.03    | Small yaw rate feedforward                  |
| `Ka`               | 0.0     | Not needed for turning                      |
| `Kc`               | 0.0     | No stiction for yaw (differential steering) |
| `enable_stiction`  | false   | Stiction compensation not needed for yaw    |

#### Feedforward Computation

```
v_limited = slew_limit(v_ref)
a_ref     = d/dt(v_limited)           # optionally filtered

tau_v = Kv * v_limited                # viscous friction
tau_a = Ka * a_ref                    # inertia compensation
tau_c = stiction_term(v_limited)      # Coulomb friction

tau_ff = tau_v + tau_a + tau_c        # then optionally limited
```

#### Stiction Model (with Stribeck Decay)

The stiction term uses a smoothed sign function with optional exponential decay:

```
tau_c = Kc * tanh(v / v0_stiction) * exp(-|v| / v_decay_stiction)
```

**Components**:

- `tanh(v / v0_stiction)`: Smooth approximation of sign(v). At `v = v0`, output is ~76% of Kc; at `v = 2*v0`, output is ~96%.
- `exp(-|v| / v_decay_stiction)`: **Stribeck decay** — fades out the stiction compensation at higher speeds where `Kv * v` already handles friction adequately.

**Special cases**:

| Condition               | Behavior                                                    |
|-------------------------|-------------------------------------------------------------|
| `v0_stiction = 0`       | Hard sign function (no smooth transition, instant step)     |
| `v_decay_stiction = 0`  | No decay — constant stiction at all speeds (original model) |
| `Kc = 0`                | No stiction compensation at all                             |
| `enable_stiction = false`| Stiction completely disabled                               |

**Why Stribeck decay?** On thick carpet, `Kc` must be high enough to overcome stiction at low speeds, but that same constant torque causes overshoot at higher speeds where `Kv * v` already provides sufficient compensation. Setting `v_decay_stiction = 0.15` means stiction fades to ~5% by 0.45 m/s.

**Note**: In practice, `Kc` and `v_decay_stiction` are managed by the floor roughness compensation system (see Section 6). The baseline feedforward config typically has `Kc = 0`, and roughness interpolation activates stiction as needed. `v0_stiction` stays in the feedforward config as a fixed shape parameter.

#### Slew Rate Limiting on v_ref

When `enable_vref_slew = true`, the velocity reference is rate-limited before computing feedforward. This prevents sudden jumps in `v_ref` from causing large acceleration torques.

- `vref_slew_rate = 3.0 m/s^2`: Reference can change by at most 0.03 m/s per 10ms step.
- `vref_slew_rate = 0`: Reference is frozen (cannot change). This is a special case, not a disable.

To disable slew limiting entirely: `enable_vref_slew = false`.

---

## 5. Position Control (Carrot-Chase Path Following)

The position controller generates `(v, psi_dot)` commands for the velocity controller. It uses a "carrot-chase" algorithm: a lookahead point (carrot) advances along the path, and the robot steers toward it.

### Operating Modes

| Mode              | Value | Description                              |
|-------------------|-------|------------------------------------------|
| `IDLE`            | 0     | No command, outputs zero                 |
| `TURN_TO_HEADING` | 1     | Rotate in place to target heading        |
| `DRIVE_TO_POINT`  | 2     | Drive to single (x, y) position          |
| `FOLLOW_PATH`     | 3     | Follow a waypoint sequence               |

### Parameters

#### Angular Control (Steering)

| Parameter      | Unit          | Default | Disable Value | Description                        |
|----------------|---------------|---------|---------------|------------------------------------|
| `kp_angular`   | (rad/s)/rad   | 8.0     | 0             | Heading error proportional gain    |
| `ki_angular`   | (rad/s)/(rad*s)| 0.25   | 0             | Heading error integral gain        |

Heading control law:

```
heading_error = atan2(carrot_y - y, carrot_x - x) - psi
psi_dot_cmd   = kp_angular * heading_error + integral(ki_angular * heading_error)
psi_dot_cmd   = clamp(psi_dot_cmd, -max_turn_rate, +max_turn_rate)
```

#### Linear Control (Speed Toward Carrot)

Two speed computation modes:

**Mode A — Sqrt deceleration profile** (`decel_limit > 0`, used in default config):

```
v_ideal = sqrt(2 * decel_limit * carrot_distance)
v_cmd   = min(v_ideal, speed_limit) - kd_linear * |current_v|
```

**Mode B — Linear proportional** (`decel_limit = 0`, fallback):

```
v_cmd = kp_linear * carrot_distance - kd_linear * |current_v|
```

In both modes, an optional integral term is added:

```
v_cmd += integral(ki_linear * carrot_distance)
```

| Parameter       | Unit   | Default | Disable Value | Description                                 |
|-----------------|--------|---------|---------------|---------------------------------------------|
| `kp_linear`     | 1/s    | 0.0     | 0             | Proportional gain (only used if decel_limit=0) |
| `ki_linear`     | 1/s^2  | 0.012   | 0             | Integral gain for linear speed              |
| `kd_linear`     | -      | 0.5     | 0             | Velocity damping factor                     |
| `decel_limit`   | m/s^2  | 0.4     | 0 (use kp_linear) | Sqrt deceleration profile limit          |

The default config uses Mode A (`decel_limit = 0.4`, `kp_linear = 0`). Don't enable both simultaneously.

#### Speed Limits

| Parameter               | Unit  | Default | Description                                |
|-------------------------|-------|---------|--------------------------------------------|
| `max_speed`             | m/s   | 0.6     | Maximum forward velocity                   |
| `max_turn_rate`         | rad/s | 5.0     | Maximum yaw rate                           |
| `speed_transition_time` | s     | 0.5     | Smooth transition between waypoint speeds  |

#### Lookahead (Carrot Position)

```
lookahead = clamp(lookahead_base + lookahead_gain * |v|, lookahead_base, lookahead_max)
```

| Parameter        | Unit | Default | Description                                  |
|------------------|------|---------|----------------------------------------------|
| `lookahead_base` | m    | 1.0     | Minimum lookahead distance                   |
| `lookahead_gain` | s    | 0.0     | Speed-dependent lookahead scaling            |
| `lookahead_max`  | m    | 1.0     | Maximum lookahead distance                   |

Default: fixed 1 m lookahead (`gain = 0`).

Larger lookahead → smoother paths but less precise corners.

#### Arrival Detection

| Parameter            | Unit | Default | Description                         |
|----------------------|------|---------|-------------------------------------|
| `arrival_tolerance`  | m    | 0.05    | Distance to consider "arrived"      |
| `arrival_dwell_time` | s    | 0.5     | Hold time at STOP waypoints         |

#### Reverse Mode

Always enabled. Robot drives backward when the target is behind it, with hysteresis to prevent oscillation:

| Parameter            | Unit | Default | Description                        |
|----------------------|------|---------|------------------------------------|
| `reverse_enter_angle`| rad  | 2.1     | Enter reverse (~120 deg)           |
| `reverse_exit_angle` | rad  | 1.05    | Exit reverse (~60 deg)             |

#### Corner Handling

| Parameter                  | Unit | Default | Description                       |
|----------------------------|------|---------|-----------------------------------|
| `corner_slowdown_distance` | m    | 0.5     | Distance from corner to start slowing |

### Waypoint Parameters

Each waypoint has:

| Field    | Type  | Default | Description                                       |
|----------|-------|---------|---------------------------------------------------|
| `x`, `y`| float | -       | World coordinates (m)                             |
| `type`   | enum  | PASS    | `PASS` (smooth transition) or `STOP` (must stop)  |
| `weight` | float | 0.75    | Corner sharpness [0..1]. 1 = sharp, 0 = smooth    |
| `speed`  | float | 0.0     | Per-waypoint speed limit (0 = use path default)    |

Weight interacts with corner angle:

```
effective_weight = weight * (corner_angle / pi)
```

- Straight path (angle near 0): carrot advances freely regardless of weight
- Sharp corner (angle near pi): full weight effect

### Disabling Position Control

Set `kp_angular = 0`, `ki_angular = 0`, `kp_linear = 0`, `ki_linear = 0`, `decel_limit = 0` → no motion commands generated.

---

## 6. Floor Roughness Compensation

Automatically scales multiple control gains based on floor friction to handle different surfaces (smooth floor vs carpet).

### Usage

```python
bilbo.control.adjust_for_floor_roughness(roughness)
```

| Roughness | Surface             | Effect              |
|-----------|---------------------|----------------------|
| 0.0       | Smooth (vinyl, wood)| No adjustment         |
| 0.5       | Flat carpet         | Moderate boost        |
| 1.0       | Thick carpet        | Maximum adjustment    |

### Configuration (floor_roughness section)

| Parameter            | Default | Scaling     | Description                                    |
|----------------------|---------|-------------|------------------------------------------------|
| `enabled`            | true    | -           | Master switch                                  |
| `kc_max`             | -0.011  | interpolated| Kc target value at roughness=1.0               |
| `v_decay_stiction_max`| 0.15   | interpolated| Stribeck decay target at roughness=1.0         |
| `v_kv_scale`         | 1.1     | multiplier  | Forward Kv scale factor at roughness=1.0       |
| `v_kp_scale`         | 1.6     | multiplier  | Forward PID Kp scale at roughness=1.0          |
| `v_ki_scale`         | 1.3     | multiplier  | Forward PID Ki scale at roughness=1.0          |
| `psidot_kp_scale`    | 1.25    | multiplier  | Turn PID Kp scale at roughness=1.0             |
| `psidot_ki_scale`    | 1.15    | multiplier  | Turn PID Ki scale at roughness=1.0             |
| `pos_kp_scale`       | 1.6     | multiplier  | Position kp_linear scale at roughness=1.0      |
| `pos_ki_scale`       | 1.2     | multiplier  | Position ki_linear scale at roughness=1.0      |
| `pos_decel_scale`    | 2.0     | multiplier  | Position decel_limit scale at roughness=1.0    |

### Scaling Formulas

**Multiplier parameters** (Kv, Kp, Ki, decel, etc.) scale the baseline value:

```
factor = 1.0 + roughness * (scale - 1.0)
adjusted_param = baseline_param * factor
```

**Interpolated parameters** (Kc, v_decay_stiction) interpolate from baseline to target:

```
Kc      = Kc_baseline      + roughness * (kc_max           - Kc_baseline)
v_decay = v_decay_baseline  + roughness * (v_decay_stiction_max - v_decay_baseline)
```

`v0_stiction` is **not** part of the roughness config — it is preserved from the baseline feedforward config, since it controls the shape of the tanh transition and doesn't need to vary with floor type.

### Stiction and Roughness

Stiction magnitude (`Kc`) and decay speed (`v_decay_stiction`) are driven by roughness. The transition shape (`v0_stiction`) comes from the baseline feedforward config:

- **roughness=0**: `Kc=0` → no stiction at all (smooth floor needs none)
- **roughness=0.5**: `Kc=-0.006`, `v0=0.08` (from FF config), `v_decay=0.075` → moderate stiction with some decay
- **roughness=1.0**: `Kc=-0.011`, `v0=0.08` (from FF config), `v_decay=0.15` → full stiction with full Stribeck decay

The `enable_stiction` flag is set automatically: `true` when `|Kc| > 0`, `false` otherwise.

### What Gets Adjusted

- **Velocity control**: Forward `Kv`, `Kp`, `Ki`, `Kc`, `v_decay_stiction`; Turn `Kp`, `Ki`
- **Position control**: `kp_linear`, `ki_linear`, `decel_limit`
- **NOT adjusted**: Balancing K matrix, TIC/VIC, angular gains, feedforward Ka

### Important

- Baseline values are stored on first call. Subsequent calls interpolate from that baseline.
- To fully reset: call `bilbo.control.load_and_set_default_config()`.
- If tuning individual params on a rough floor, either disable roughness comp or account for the scaling.

### Tuning

- Robot stops short on carpet: increase `kp_scale` or `kc_max`
- Robot overshoots: decrease scale factors
- Oscillation on carpet: reduce `kp_scale`, keep `kc_max`

---

## 7. Parameter Interactions and Common Pitfalls

### Feedforward Kc vs PID Ki (velocity)

Both compensate for friction, but in different ways:
- **Kc (feedforward)**: Immediate, model-based. Applied as soon as a velocity is commanded.
- **Ki (PID)**: Error-driven, slow. Builds up over time as error accumulates.

Prefer `Kc` for known friction. Use `Ki` only for residual errors after `Kc` is tuned. Having both too high leads to overshoot.

### Position kp_linear vs decel_limit

These are two alternative speed computation methods — don't use both:
- `decel_limit > 0`: Uses `sqrt(2 * decel * d)` profile. Smooth, speed-independent deceleration. **Recommended.**
- `decel_limit = 0`: Falls back to `kp_linear * d`. Simpler but less smooth. Set `kp_linear > 0` if using this mode.

### Lookahead vs Corner Precision

- Larger lookahead → smoother trajectory, cuts corners more
- Smaller lookahead → tighter path following, may oscillate near waypoints
- Default is 1 m fixed lookahead, which works well for most paths

### Balancing K vs TIC/VIC

- K matrix is the primary balance controller. It must work on its own.
- TIC/VIC compensate for slow drift that K alone can't fix.
- If K is poorly tuned, TIC/VIC may fight the main controller → oscillation.
- Always tune K first, then add TIC/VIC for refinement.

### Sign Conventions

| Controller           | Positive Error Means       | Gain Sign |
|----------------------|----------------------------|-----------|
| Forward velocity PID | Want faster                | Negative  |
| Forward velocity FF  | Forward reference          | Negative  |
| Turn PID             | Want more yaw rate         | Positive  |
| Turn FF              | Positive yaw reference     | Positive  |

The negative signs for forward velocity come from the physics: positive velocity error should produce a negative pitch angle (lean backward) to accelerate forward.

---

## 8. Quick Reference: Disabling Each Component

| Component                    | How to Disable                                         |
|------------------------------|--------------------------------------------------------|
| Balancing (K matrix)         | All K values = 0 (robot WILL fall)                     |
| TIC                          | `enabled = false` or `ki = 0`                          |
| VIC                          | `enabled = false` or `ki = 0`                          |
| Forward velocity PID         | `Kp = Ki = Kd = 0` (pure feedforward)                  |
| Turn velocity PID            | `Kp = Ki = Kd = 0` (pure feedforward)                  |
| Feedforward viscous (Kv)     | `Kv = 0`                                               |
| Feedforward inertia (Ka)     | `Ka = 0`                                               |
| Feedforward stiction (Kc)    | `Kc = 0` or `enable_stiction = false`                  |
| Stiction smooth transition   | `v0_stiction = 0` → hard sign function                 |
| Stribeck decay               | `v_decay_stiction = 0` → constant stiction at all speeds |
| Reference slew limiting      | `enable_vref_slew = false`                             |
| FF output limiting           | `enable_output_limit = false`                          |
| FF output slew               | `enable_output_slew = false`                           |
| Position angular control     | `kp_angular = ki_angular = 0`                          |
| Position linear control      | `kp_linear = ki_linear = kd_linear = decel_limit = 0`  |
| Floor roughness compensation | `enabled = false` or roughness = 0                     |

---

## 9. Default Configuration (bilbo2_default.yaml)

```yaml
balancing_control:
  K: [0.25, 0.2, 0.03, 0.025, 0.25, 0.2, 0.03, -0.025]
  tic: { enabled: true, ki: 0.4, max_torque: 0.05, theta_limit: 0.16 }
  vic: { enabled: true, ki: 0.2, max_torque: 0.02, v_limit: 0.05, theta_limit: 0.16 }

velocity_control:
  v:
    pid: { Kp: -0.00, Ki: -0.02, Kd: -0.0 }
    feedforward:
      Kv: -0.25, Ka: -0.02, Kc: -0.0
      enable_vref_slew: true, vref_slew_rate: 3.0
      enable_stiction: true, v0_stiction: 0.08, v_decay_stiction: 0.15
  psidot:
    pid: { Kp: 0.01, Ki: 0.05, Kd: 0.0 }
    feedforward: { Kv: 0.03 }  # everything else 0/disabled

position_control:
  kp_angular: 8.0, ki_angular: 0.25
  kp_linear: 0.0, ki_linear: 0.012, kd_linear: 0.5
  decel_limit: 0.4
  max_speed: 0.6, max_turn_rate: 5.0
  lookahead_base: 1.0, lookahead_gain: 0.0, lookahead_max: 1.0
```

Key takeaways from the defaults:
- Forward velocity is **feedforward-dominated** (Kp = 0, small Ki, large Kv)
- Forward stiction is enabled but Kc starts at 0 (adjusted by floor roughness)
- Position control uses **sqrt deceleration** (decel_limit = 0.4, kp_linear = 0)
- Fixed 1 m lookahead
