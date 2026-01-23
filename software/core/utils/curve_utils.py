import math
from enum import Enum

JOYSTICK_DEADZONE = 0.05


class JoystickCurve(Enum):
    LINEAR = "linear"  # y = x
    POWER = "power"  # y = sign(x) * |x|^p           (p>1 = flatter center)
    CUBIC = "cubic"  # y = x^3                       (very flat near center)
    SMOOTHSTEP = "smoothstep"  # y = sign(x) * (3t^2 - 2t^3)   (nice S-curve)
    SIGMOID = "sigmoid"  # y = tanh(kx)/tanh(k)          (soft center, saturates smoothly)
    EXP = "exp"  # y = sign(x)*(exp(k|x|)-1)/(exp(k)-1)


# # default settings (global)
# JOYSTICK_CURVE = JoystickCurve.POWER
# JOYSTICK_CURVE_GAIN = 2.0  # meaning depends on curve (see below)
# JOYSTICK_DEADZONE = 0.01  # 5% deadzone


def _apply_deadzone(x: float, deadzone: float) -> float:
    """Apply symmetric deadzone and rescale to keep full range."""
    ax = abs(x)
    if ax <= deadzone:
        return 0.0
    # rescale remaining range back to [0,1]
    y = (ax - deadzone) / (1.0 - deadzone)
    return math.copysign(y, x)


def _shape_magnitude(t: float, curve: JoystickCurve, gain: float) -> float:
    """
    Shape |x| in [0,1] -> y in [0,1] according to selected curve.
    `t` must be >=0.
    """
    t = max(0.0, min(1.0, t))
    if curve == JoystickCurve.LINEAR:
        return t

    if curve == JoystickCurve.POWER:
        # gain = exponent (>=1). 1.0 = linear, 2.0 = quadratic, 3.0 ≈ cubic, ...
        p = max(1.0, float(gain))
        return t ** p

    if curve == JoystickCurve.CUBIC:
        return t ** 3

    if curve == JoystickCurve.SMOOTHSTEP:
        # smoothstep: 3t^2 - 2t^3
        return t * t * (3.0 - 2.0 * t)

    if curve == JoystickCurve.SIGMOID:
        # symmetric tanh; gain controls steepness; normalized so max = 1 at t=1
        k = max(0.01, float(gain))
        return math.tanh(k * t) / math.tanh(k)

    if curve == JoystickCurve.EXP:
        # exponential easing; gain controls steepness towards 1
        k = max(0.01, float(gain))
        return math.expm1(k * t) / math.expm1(k)

    # fallback
    return t


def shape_joystick(x: float,
                   curve: JoystickCurve,
                   gain: float,
                   deadzone: float = None) -> float:
    """
    Full shaping pipeline:
      1) deadzone
      2) curve on magnitude
      3) restore sign
    Uses globals when args are None.
    """
    if deadzone is None:
        deadzone = JOYSTICK_DEADZONE

    # 1) deadzone + rescale
    x_dz = _apply_deadzone(x, deadzone)
    s = math.copysign(1.0, x_dz) if x_dz != 0 else 1.0
    t = abs(float(x_dz))

    # 2) curve on magnitude
    y_mag = _shape_magnitude(t, curve, gain)

    # 3) clamp and sign
    y = s * max(0.0, min(1.0, y_mag))
    return y


def set_joystick_curve(name: str,
                       gain: float | None = None,
                       deadzone: float | None = None) -> dict:
    """
    Simple global setter you can call from anywhere (incl. CLI).
    - name: one of JoystickCurve names/values (case-insensitive)
    - gain: optional (meaning depends on curve)
    - deadzone: optional percentage [0..1]
    Returns a dict with the current config (useful for CLI echo).
    """
    global JOYSTICK_CURVE, JOYSTICK_CURVE_GAIN, JOYSTICK_DEADZONE

    # resolve curve
    normalized = str(name).strip().lower()
    mapping = {c.value: c for c in JoystickCurve}
    mapping.update({c.name.lower(): c for c in JoystickCurve})
    if normalized not in mapping:
        raise ValueError(f"Unknown joystick curve '{name}'. "
                         f"Valid: {[c.value for c in JoystickCurve]}")

    JOYSTICK_CURVE = mapping[normalized]

    if gain is not None:
        JOYSTICK_CURVE_GAIN = float(gain)
    if deadzone is not None:
        JOYSTICK_DEADZONE = max(0.0, min(0.4, float(deadzone)))  # keep sane

    return get_joystick_curve()


def get_joystick_curve() -> dict:
    """Return current curve configuration."""
    return {
        "curve": JOYSTICK_CURVE.value,
        "gain": JOYSTICK_CURVE_GAIN,
        "deadzone": JOYSTICK_DEADZONE
    }


def plot_joystick_curve(
        curve: JoystickCurve | None = None,
        gain: float | None = None,
        deadzone: float | None = None,
        num_points: int = 1001,
        show: bool = True,
        save_path: str | None = None,
        ax=None,
):
    """
    Visualize input -> output mapping for the current (or specified) joystick curve.
    - curve/gain/deadzone default to global JOYSTICK_* if None.
    - num_points: sample resolution in [-1, 1]
    - show: call plt.show() if True
    - save_path: optional file path to save the figure (PNG, SVG, etc.)
    - ax: optional matplotlib Axes to draw on

    Returns (fig, ax, data) where data is a dict with 'x', 'y', 'y_linear'.
    """
    try:
        import matplotlib.pyplot as plt  # ensure available at runtime
    except Exception as e:
        raise RuntimeError(
            "matplotlib is required for plotting. Install via `pip install matplotlib`."
        ) from e

    # Resolve defaults the same way shape_joystick does
    if curve is None:
        curve = JOYSTICK_CURVE
    if gain is None:
        gain = JOYSTICK_CURVE_GAIN
    if deadzone is None:
        deadzone = JOYSTICK_DEADZONE

    # Sample inputs
    num_points = max(101, int(num_points))
    xs = [(-1.0 + 2.0 * i / (num_points - 1)) for i in range(num_points)]
    ys = [shape_joystick(x, curve=curve, gain=gain, deadzone=deadzone) for x in xs]
    y_linear = xs[:]  # reference line y = x

    # Create axes if needed
    created_fig = False
    if ax is None:
        fig, ax = plt.subplots(figsize=(6.5, 5.0), dpi=120)
        created_fig = True
    else:
        fig = ax.figure

    # Plot mapping and reference
    ax.plot(xs, ys, label=f"shaped: {curve.value} (gain={gain:.2f})")
    ax.plot(xs, y_linear, linestyle="--", linewidth=1.0, label="linear (y = x)")

    # Shade deadzone region (input side)
    if deadzone > 0:
        ax.axvspan(-deadzone, deadzone, alpha=0.12, label=f"deadzone ±{deadzone:.2f}")

    # Cosmetics
    ax.set_title("Joystick Curve (input → output)")
    ax.set_xlabel("stick input (raw)")
    ax.set_ylabel("normalized output (to controller)")
    ax.set_xlim(-1.0, 1.0)
    ax.set_ylim(-1.05, 1.05)
    ax.grid(True, which="both", linestyle=":", linewidth=0.8)
    ax.legend(loc="best")

    # Optional save
    if save_path:
        fig.savefig(save_path, bbox_inches="tight")

    if show and created_fig:
        plt.show()

    return fig, ax, {"x": xs, "y": ys, "y_linear": y_linear}


if __name__ == '__main__':
    plot_joystick_curve(
        curve=JoystickCurve.POWER,
        gain=2,
        deadzone=0.01,
    )
