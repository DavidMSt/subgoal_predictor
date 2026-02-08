"""
Control tuning visualization utilities.

Provides plotting functions for inspecting feedforward stiction/Stribeck curves
from a BILBO_ControlConfig.
"""

import numpy as np
import matplotlib.pyplot as plt

from robot.control.bilbo_control_definitions import BILBO_ControlConfig, Feedforward_Config


def plot_stiction(config: BILBO_ControlConfig, v_range: float = 0.5):
    """Plot the stiction and Stribeck decay curves for a control config.

    Shows four subplots:
    - Top left:  Stiction term only (tau_c vs v_cmd) for forward and turn
    - Top right: Total feedforward (Kv*v + Ka*a + stiction) vs v_cmd (steady-state, a=0)
    - Bottom left:  Stiction as percentage of total feedforward (forward only)
    - Bottom right: Low-speed zoom of the stiction term

    Args:
        config: BILBO_ControlConfig with velocity_control settings.
        v_range: Symmetric velocity range to plot [m/s]. Default 0.5.
    """
    v_cmd = np.linspace(-v_range, v_range, 1000)
    v_pos = np.linspace(0.01, v_range, 500)

    ff_v = config.velocity_control.v.feedforward
    ff_psi = config.velocity_control.psidot.feedforward

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # --- Top left: stiction term only ---
    ax = axes[0, 0]
    _plot_stiction_term(ax, v_cmd, ff_v, label_prefix='v')
    _plot_stiction_term(ax, v_cmd, ff_psi, label_prefix='psi_dot')
    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction')
    ax.set_title('Stiction term only')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # --- Top right: total feedforward (steady-state, a=0) ---
    ax = axes[0, 1]
    tau_ff_v = _compute_total_ff(v_cmd, ff_v)
    tau_ff_psi = _compute_total_ff(v_cmd, ff_psi)
    tau_kv_only = ff_v.Kv * v_cmd

    ax.plot(v_cmd, tau_kv_only, 'gray', linewidth=1, label='v: Kv*v only')
    ax.plot(v_cmd, tau_ff_v, linewidth=2, label='v: total FF')
    if ff_psi.Kv != 0 or ff_psi.Kc != 0:
        ax.plot(v_cmd, tau_ff_psi, linewidth=1.5, linestyle='--', label='psi_dot: total FF')
    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_ff total')
    ax.set_title('Total feedforward (steady-state)')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # --- Bottom left: stiction as % of total FF (forward only) ---
    ax = axes[1, 0]
    if ff_v.Kv != 0 and ff_v.Kc != 0:
        stiction_abs = np.abs(_compute_stiction(v_pos, ff_v))
        total_abs = np.abs(ff_v.Kv * v_pos) + stiction_abs
        ratio = stiction_abs / total_abs * 100
        ax.plot(v_pos, ratio, linewidth=2, label='Forward velocity')
        ax.set_ylabel('Stiction contribution [%]')
    else:
        ax.text(0.5, 0.5, 'Kv or Kc is zero\n(no ratio to show)',
                transform=ax.transAxes, ha='center', va='center', fontsize=12)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_title('Stiction as % of total feedforward')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # --- Bottom right: low-speed zoom ---
    ax = axes[1, 1]
    v_zoom = np.linspace(-3 * ff_v.v0_stiction if ff_v.v0_stiction > 0 else -0.15,
                          3 * ff_v.v0_stiction if ff_v.v0_stiction > 0 else 0.15, 500)
    _plot_stiction_term(ax, v_zoom, ff_v, label_prefix='v')
    if ff_v.v0_stiction > 0:
        ax.axvline(x=ff_v.v0_stiction, color='orange', linewidth=0.8, linestyle=':',
                   label=f'v0 = {ff_v.v0_stiction} m/s')
        ax.axvline(x=-ff_v.v0_stiction, color='orange', linewidth=0.8, linestyle=':')
    ax.axhline(y=0, color='black', linewidth=0.5)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.set_xlabel('v_cmd [m/s]')
    ax.set_ylabel('tau_stiction')
    ax.set_title('Stiction term — low-speed zoom')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Build title from config values
    title = (f'Feedforward stiction  '
             f'(Kv={ff_v.Kv}, Kc={ff_v.Kc}, v0={ff_v.v0_stiction}, '
             f'v_decay={ff_v.v_decay_stiction})')
    fig.suptitle(title, fontsize=13)
    plt.tight_layout()
    plt.show()


def _compute_stiction(v: np.ndarray, ff: Feedforward_Config) -> np.ndarray:
    """Compute the stiction term: Kc * tanh(v/v0) * exp(-|v|/v_decay)."""
    if not ff.enable_stiction or ff.Kc == 0:
        return np.zeros_like(v)

    if ff.v0_stiction > 0:
        s = np.tanh(v / ff.v0_stiction)
    else:
        s = np.sign(v)

    if ff.v_decay_stiction > 0:
        decay = np.exp(-np.abs(v) / ff.v_decay_stiction)
    else:
        decay = 1.0

    return ff.Kc * s * decay


def _compute_total_ff(v: np.ndarray, ff: Feedforward_Config) -> np.ndarray:
    """Compute total feedforward at steady-state (a=0): Kv*v + stiction."""
    return ff.Kv * v + _compute_stiction(v, ff)


def _plot_stiction_term(ax, v: np.ndarray, ff: Feedforward_Config, label_prefix: str = ''):
    """Plot the stiction term on the given axis, showing with/without decay if applicable."""
    if not ff.enable_stiction or ff.Kc == 0:
        return

    prefix = f'{label_prefix}: ' if label_prefix else ''

    # Without decay (pure tanh)
    if ff.v0_stiction > 0:
        tau_no_decay = ff.Kc * np.tanh(v / ff.v0_stiction)
    else:
        tau_no_decay = ff.Kc * np.sign(v)

    # With decay
    tau_with_decay = _compute_stiction(v, ff)

    if ff.v_decay_stiction > 0:
        ax.plot(v, tau_no_decay, '--', linewidth=1, alpha=0.5,
                label=f'{prefix}Kc*tanh (no decay)')
        ax.plot(v, tau_with_decay, linewidth=2,
                label=f'{prefix}with Stribeck decay (v_decay={ff.v_decay_stiction})')
    else:
        ax.plot(v, tau_no_decay, linewidth=2,
                label=f'{prefix}Kc*tanh(v/v0)')
