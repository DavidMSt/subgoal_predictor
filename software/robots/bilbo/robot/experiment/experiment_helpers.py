from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

import numpy as np
from scipy.fft import rfftfreq, rfft
from scipy.signal import find_peaks

from core.utils.data import generate_time_vector, generate_random_input
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory, BILBO_InputFileData, \
    BILBO_InputTrajectoryStep

if TYPE_CHECKING:
    from robots.bilbo.robot.experiment.experiment_definitions import ExperimentData
    from core.utils.report import Report


# === TRAJECTORY =======================================================================================================
def generate_trajectory_inputs(inputs: list | np.ndarray) -> list[BILBO_InputTrajectoryStep]:
    trajectory_inputs = []

    if isinstance(inputs, np.ndarray):
        inputs = inputs.tolist()

    for i, inp in enumerate(inputs):
        if isinstance(inp, list):
            left = float(inp[0])
            right = float(inp[1])
        else:
            left = float(inp) / 2
            right = float(inp) / 2

        trajectory_inputs.append(BILBO_InputTrajectoryStep(
            step=i,
            left=left,
            right=right,
        ))
    return trajectory_inputs


def trajectory_inputs_to_list(trajectory_inputs: list[BILBO_InputTrajectoryStep], single_input: bool = False) -> list:
    out = []
    for inp in trajectory_inputs:
        if not single_input:
            out.append([inp.left, inp.right])
        else:
            out.append(inp.left + inp.right)

    return out


def trajectory_inputs_to_vector(trajectory_inputs: list[BILBO_InputTrajectoryStep], single_input: bool = False) -> np.ndarray:
    return np.array(trajectory_inputs_to_list(trajectory_inputs, single_input=single_input))


def generate_random_input_trajectory(trajectory_id, time_s, frequency, gain) -> BILBO_InputTrajectory | None:
    """
    Generates a random test trajectory for simulation or testing purposes. The function creates a time
    vector based on the specified duration and generates random inputs filtered by a cutoff frequency
    and scaled by the provided gain. If the trajectory exceeds the maximum allowed steps, the function
    returns None. Otherwise, it returns a trajectory object containing the generated data.

    Args:
        trajectory_id: Identifier for the generated trajectory.
        time_s: Maximum time duration of the trajectory in seconds.
        frequency: Cutoff frequency for filtering random inputs.
        gain: Scaling factor for random input signal amplitude.

    Returns:
        BILBO_InputTrajectory | None: The trajectory object containing the generated data or None
        if the trajectory exceeds the maximum allowed steps.
    """
    t_vector = generate_time_vector(start=0, end=time_s, dt=BILBO_CONTROL_DT)

    if len(t_vector) > MAX_STEPS_TRAJECTORY:
        print(f"Trajectory too long: {len(t_vector)} > {MAX_STEPS_TRAJECTORY} steps")
        return None

    trajectory_input = generate_random_input(t_vector=t_vector, f_cutoff=frequency, sigma_I=gain)
    trajectory_inputs = generate_trajectory_inputs(trajectory_input)

    trajectory = BILBO_InputTrajectory(
        id=trajectory_id,
        name='test',
        dt=BILBO_CONTROL_DT,
        inputs=trajectory_inputs,
    )

    return trajectory


# === PLOTTING =========================================================================================================
def plot_input_trajectory(trajectory: BILBO_InputTrajectory):
    ...


# === ANALYTICS ========================================================================================================
@dataclasses.dataclass
class FrequencyComponent:
    frequency: float
    weight: float  # relative amplitude (normalized to 1)


@dataclasses.dataclass
class BILBO_InputAnalytics:
    steps: int
    Ts: float
    max_amplitude: float
    dominant_frequencies: list[FrequencyComponent]
    is_2d: bool


def generateInputTrajectoryAnalytics(input_trajectory: BILBO_InputTrajectory,
                                     num_dominant: int = 5) -> BILBO_InputAnalytics:
    steps = input_trajectory.length
    time_vector = input_trajectory.time_vector
    Ts = float(time_vector[1] - time_vector[0])  # Sampling time

    # Extract signal vectors
    left_signal = np.array([input_trajectory.inputs[i].left for i in sorted(input_trajectory.inputs)])
    right_signal = np.array([input_trajectory.inputs[i].right for i in sorted(input_trajectory.inputs)])
    is_2d = not np.allclose(left_signal, right_signal)

    # Use average of both channels for analysis
    combined_signal = 0.5 * (left_signal + right_signal)

    # FFT analysis
    freqs = rfftfreq(steps, Ts)
    fft_magnitude = np.abs(rfft(combined_signal))

    # Remove DC component
    fft_magnitude[0] = 0.0

    # Find all peaks above a threshold (e.g., 5% of max)
    peak_indices, _ = find_peaks(fft_magnitude, height=np.max(fft_magnitude) * 0.05)

    if len(peak_indices) == 0:
        dominant_components = []
    else:
        # Sort by amplitude
        sorted_indices = peak_indices[np.argsort(fft_magnitude[peak_indices])[::-1]]

        # Pick top N
        top_indices = sorted_indices[:num_dominant]
        top_freqs = freqs[top_indices]
        top_amps = fft_magnitude[top_indices]

        # Normalize weights
        total_amp = np.sum(top_amps)
        weights = top_amps / total_amp if total_amp > 0 else np.zeros_like(top_amps)

        dominant_components = [
            FrequencyComponent(frequency=freq, weight=float(weight))
            for freq, weight in zip(top_freqs, weights)
        ]

    # Max signal amplitude (could be RMS, but sticking to peak for now)
    max_amplitude = np.max(np.abs(combined_signal))

    return BILBO_InputAnalytics(
        steps=steps,
        Ts=Ts,
        max_amplitude=max_amplitude,
        dominant_frequencies=dominant_components,
        is_2d=is_2d,
    )


# === REPORT GENERATION ================================================================================================
# Color palette for phase bars (distinguishable colors)
PHASE_COLORS = [
    '#3498db',  # Blue
    '#e74c3c',  # Red
    '#2ecc71',  # Green
    '#9b59b6',  # Purple
    '#f39c12',  # Orange
    '#1abc9c',  # Teal
    '#e91e63',  # Pink
    '#00bcd4',  # Cyan
    '#ff5722',  # Deep Orange
    '#8bc34a',  # Light Green
    '#673ab7',  # Deep Purple
    '#ffc107',  # Amber
]


def make_report(
        experiment: str | dict | 'ExperimentData',
        output: str | None = None,
        format: str = 'html',
        states: list[str] | None = None,
        phase_style: str = 'bar',
        show: bool = True,
) -> 'Report':
    """
    Generate an HTML report for an experiment.

    Parameters
    ----------
    experiment : str | dict | ExperimentData
        Experiment data source:
        - str: Path to a .json file containing experiment data
        - dict: Dictionary containing experiment data
        - ExperimentData: ExperimentData dataclass instance
    output : str | None
        Output file path. If None and show=True, opens in browser.
    format : str
        Output format: 'html' or 'pdf'.
    states : list[str] | None
        List of state names to plot. If None, plots all: ['theta', 'v', 'psi', 'psi_dot', 'x', 'y'].
    phase_style : str
        Style for phase visualization: 'bar' (default) or 'background'.
        - 'bar': Compact phase bar at bottom inside of plot
        - 'background': Full-height colored background regions with labels at top
    show : bool
        If True and output is None, opens the report in a viewer.

    Returns
    -------
    Report
        The Report object.

    Example
    -------
    >>> make_report("experiment_data.json")
    >>> make_report(experiment_dict, output="report.html")
    >>> make_report(experiment_data, states=['theta', 'v'], phase_style='background')
    """
    from pathlib import Path
    import json

    from core.utils.report import Report
    from core.utils.plotting.plot import Plot, Axis, AxisConfig
    from core.utils.plotting.map_plot import MapPlot
    from robots.bilbo.robot.experiment.experiment_definitions import ExperimentData, ExperimentDefinition
    from robots.bilbo.robot.bilbo_data import BILBO_STATE_DATA_DEFINITIONS

    # Load experiment data
    if isinstance(experiment, str):
        with open(experiment, 'r') as f:
            exp_dict = json.load(f)
    elif isinstance(experiment, ExperimentData):
        exp_dict = dataclasses.asdict(experiment)
    else:
        exp_dict = experiment

    # Extract key data (with None checks)
    exp_id = exp_dict.get('id', 'unknown')
    definition = exp_dict.get('definition') or {}
    meta = exp_dict.get('meta') or {}
    samples = exp_dict.get('samples') or []
    actions_data = exp_dict.get('actions') or {}
    logs_raw = exp_dict.get('logs') or []

    # Process logs: add level_name for display
    LOG_LEVEL_NAMES = {10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR', 50: 'CRITICAL'}
    logs = []
    for log in logs_raw:
        level = log.get('level', 20)
        logs.append({
            'tick': log.get('tick', 0),
            'level': level,
            'level_name': LOG_LEVEL_NAMES.get(level, 'INFO'),
            'logger': log.get('logger', ''),
            'message': log.get('message', ''),
        })

    # Get description from definition or meta
    description = definition.get('description', '') if definition else ''
    if not description:
        description = meta.get('description', '') if meta else ''

    # Default states to plot
    if states is None:
        states = ['theta', 'theta_dot', 'v', 'psi', 'psi_dot', 'x', 'y']

    # Extract time vector and state data
    if len(samples) == 0:
        raise ValueError("No samples in experiment data")

    # Generate time vector like in plot_last_experiment (dt=0.01 = 100Hz)
    from core.utils.data import generate_time_vector_by_length
    t = generate_time_vector_by_length(start=0, num_samples=len(samples), dt=0.01)
    duration = len(samples) * 0.01  # n samples at 100Hz = n * dt

    # Extract state vectors from lowlevel.estimation.state (better resolution)
    state_data = {}
    for state_name in states:
        values = []
        for s in samples:
            # Use lowlevel.estimation.state for better resolution
            ll = s.get('lowlevel') or {}
            ll_est = ll.get('estimation') or {}
            ll_state = ll_est.get('state') or {}
            values.append(ll_state.get(state_name, 0.0) or 0.0)
        state_data[state_name] = np.array(values)

    # Process actions for display
    action_defs = definition.get('actions') or []
    actions_info = []
    phase_actions = []
    color_index = 0

    # Helper to check if action ID is generic (auto-generated like "action_0", "action_1", etc.)
    def is_generic_id(action_id: str) -> bool:
        return bool(re.match(r'^action_\d+$', action_id))

    for i, action_def in enumerate(action_defs):
        if action_def is None:
            continue
        action_id = action_def.get('id', f'action_{i}')
        action_type = action_def.get('type', 'unknown')
        params = action_def.get('parameters') or {}

        # Get timing from actions_data
        action_timing = actions_data.get(action_id) or {}
        start_time = action_timing.get('start_time')
        end_time = action_timing.get('end_time')
        start_tick = action_timing.get('start_tick') or 0
        end_tick = action_timing.get('end_tick') or 0

        # Check if action spans multiple ticks (has duration)
        has_phase = (end_tick - start_tick) > 1 if start_tick is not None and end_tick is not None else False

        # Exclude wait_time actions with generic IDs from being shown as phases
        is_generic_wait = (action_type == 'wait_time' and is_generic_id(action_id))

        # Assign color for multi-tick actions (except generic waits)
        color = None
        if has_phase and not is_generic_wait:
            color = PHASE_COLORS[color_index % len(PHASE_COLORS)]
            color_index += 1
            phase_actions.append({
                'id': action_id,
                'type': action_type,
                'color': color,
                'start_time': start_time,
                'end_time': end_time,
            })

        # Format parameters for display
        params_str = _format_action_params(action_type, params)

        actions_info.append({
            'index': i,
            'id': action_id,
            'type': action_type,
            'params_str': params_str,
            'start_time': start_time,
            'end_time': end_time,
            'has_phase': has_phase,
            'color': color,
        })

    # Phase bar height as fraction of plot (used for ylim adjustment)
    PHASE_BAR_HEIGHT = 0.07

    # Helper to calculate ylim with padding for phase bar
    def calc_ylim_with_phase_padding(*data_arrays):
        """Calculate ylim that leaves room for phase bar at bottom."""
        all_data = np.concatenate([d for d in data_arrays if len(d) > 0])
        y_min, y_max = np.min(all_data), np.max(all_data)
        y_range = y_max - y_min
        if y_range == 0:
            y_range = 1.0  # Avoid division by zero
        # Add padding: small margin at top, larger at bottom for phase bar
        padding_top = 0.05 * y_range
        padding_bottom = (PHASE_BAR_HEIGHT / (1 - PHASE_BAR_HEIGHT)) * y_range + 0.05 * y_range
        return (y_min - padding_bottom, y_max + padding_top)

    # Helper to add phase visualization to an axis
    def add_phases_to_axis(axis):
        if not phase_actions:
            return
        if phase_style == 'bar':
            # Phase bar at bottom inside
            axis.configure_phase_bar(
                position="bottom_inside",
                height=PHASE_BAR_HEIGHT,
                fontsize=11,
                corner_radius=0.01,
                horizontal_padding=0.002,
            )
            for phase in phase_actions:
                if phase['start_time'] is not None and phase['end_time'] is not None:
                    axis.add_phase(
                        phase['id'],
                        start=phase['start_time'],
                        end=phase['end_time'],
                        color=phase['color'],
                    )
        else:
            # Phase background with labels at top
            axis.configure_phase_background(
                show_labels=True,
                alpha=0.2,
                label_position="top",
                fontsize=11,
                label_box=True,
                label_box_alpha=0.8,
            )
            for phase in phase_actions:
                if phase['start_time'] is not None and phase['end_time'] is not None:
                    axis.add_background_phase(
                        phase_id=phase['id'],
                        start=phase['start_time'],
                        end=phase['end_time'],
                        color=phase['color'],
                    )

    # Create plots
    plots = []
    for state_name in states:
        if state_name not in state_data:
            continue

        y = state_data[state_name]
        state_def = BILBO_STATE_DATA_DEFINITIONS.get(state_name, {})
        unit = state_def.get('unit', '')
        ylabel = f"{state_name} [{unit}]" if unit else state_name

        # Calculate ylim with padding for phase bar if needed
        ylim = calc_ylim_with_phase_padding(y) if (phase_style == 'bar' and phase_actions) else None

        # Create plot - wider aspect ratio, taller, transparent background
        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),  # No white space on left/right
            ylim=ylim,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        # Plot state data with thicker line
        axis.plot(t, y, color='#2c3e50', linewidth=1.8)

        plots.append({
            'title': ylabel,
            'image': p,
        })

    # Create trajectory map plot
    trajectory_map = None
    if 'x' in state_data and 'y' in state_data:
        x_data = state_data['x']
        y_data = state_data['y']

        # Get testbed size from meta data
        testbed_data = meta.get('testbed') or {}
        testbed_config = testbed_data.get('config') or {}
        testbed_size = testbed_config.get('size') or {}

        x_min = testbed_size.get('x_min', -2.0)
        x_max = testbed_size.get('x_max', 2.0)
        y_min = testbed_size.get('y_min', -2.0)
        y_max = testbed_size.get('y_max', 2.0)

        # Create map plot
        map_plot = MapPlot(
            size=((x_min, x_max), (y_min, y_max)),
            padding=0.15,
            border_corner_radius=0.05,
        )
        map_plot.add_grid(major=1.0, minor=0.25, major_opacity=0.4, minor_opacity=0.8)
        map_plot.add_coordinate_system(length=0.3)

        # Add trajectory with gradient
        map_plot.add_trajectory(
            x_data, y_data,
            gradient=True,
            gradient_cmap='viridis',
            width=2.5,
            show_start=True,
            show_end=True,
            start_color='green',
            end_color='red',
        )

        # Render and store
        map_plot.render()
        trajectory_map = map_plot

    # Create control plots from lowlevel.control
    control_plots = []

    # Helper to create a dual-line plot (left/right or similar)
    def create_control_plot(title: str, data1: np.ndarray, data2: np.ndarray,
                            label1: str, label2: str, ylabel: str) -> Plot:
        # Calculate ylim with padding for phase bar if needed
        ylim = calc_ylim_with_phase_padding(data1, data2) if (phase_style == 'bar' and phase_actions) else None

        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),
            ylim=ylim,
            legend=True,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        axis.plot(t, data1, color='#e74c3c', linewidth=1.8, label=label1)
        axis.plot(t, data2, color='#3498db', linewidth=1.8, label=label2)
        return p

    # Helper to create a dual y-axis plot (for velocity_command)
    def create_dual_yaxis_plot(title: str, data1: np.ndarray, data2: np.ndarray,
                               label1: str, label2: str, ylabel1: str, ylabel2: str) -> Plot:
        # Calculate ylim with padding for phase bar if needed
        ylim1 = calc_ylim_with_phase_padding(data1) if (phase_style == 'bar' and phase_actions) else None

        p = Plot(rows=1, columns=1, size=(10, 3.5), use_agg_backend=True, facealpha=0)
        axis = Axis(id="main", config=AxisConfig(
            xlabel="Time [s]",
            ylabel=ylabel1,
            grid=True,
            label_font_size=14,
            tick_font_size=12,
            facecolor='none',
            xlim=(t[0], t[-1]),
            ylim=ylim1,
        ))
        p.set_axis(1, 1, axis)

        # Add phase visualization
        add_phases_to_axis(axis)

        # Plot first data on primary axis
        axis.plot(t, data1, color='#e74c3c', linewidth=1.8, label=label1)
        line1 = axis.ax.get_lines()[-1]

        # Create secondary y-axis
        ax2 = axis.ax.twinx()
        ax2.set_ylabel(ylabel2, fontsize=14, color='#3498db')
        ax2.tick_params(axis='y', labelcolor='#3498db', labelsize=12)
        line2, = ax2.plot(t, data2, color='#3498db', linewidth=1.8, label=label2)

        # Set ylim for secondary axis with phase bar padding
        if phase_style == 'bar' and phase_actions:
            ylim2 = calc_ylim_with_phase_padding(data2)
            ax2.set_ylim(ylim2)

        # Combined legend
        axis.ax.legend([line1, line2], [label1, label2], loc='upper right', fontsize=10)

        return p

    # Extract control data from samples
    def extract_control_data(path: list[str]) -> np.ndarray:
        values = []
        for s in samples:
            ll = s.get('lowlevel') or {}
            ctrl = ll.get('control') or {}
            val = ctrl
            for key in path:
                val = (val.get(key) if isinstance(val, dict) else None) or {}
            values.append(val if isinstance(val, (int, float)) else 0.0)
        return np.array(values)

    # velocity_command: v and psi_dot (dual y-axis)
    vel_cmd_v = extract_control_data(['velocity_command', 'v'])
    vel_cmd_psi_dot = extract_control_data(['velocity_command', 'psi_dot'])
    if np.any(vel_cmd_v) or np.any(vel_cmd_psi_dot):
        control_plots.append({
            'title': 'Velocity Command',
            'image': create_dual_yaxis_plot(
                'Velocity Command', vel_cmd_v, vel_cmd_psi_dot,
                'v', 'psi_dot', 'v [m/s]', 'psi_dot [rad/s]'
            ),
        })

    # velocity_output: u_l and u_r
    vel_out_l = extract_control_data(['velocity_output', 'u_l'])
    vel_out_r = extract_control_data(['velocity_output', 'u_r'])
    if np.any(vel_out_l) or np.any(vel_out_r):
        control_plots.append({
            'title': 'Velocity Output',
            'image': create_control_plot(
                'Velocity Output', vel_out_l, vel_out_r,
                'left', 'right', 'u'
            ),
        })

    # input_ext: u_left and u_right
    inp_ext_l = extract_control_data(['input_ext', 'u_left'])
    inp_ext_r = extract_control_data(['input_ext', 'u_right'])
    if np.any(inp_ext_l) or np.any(inp_ext_r):
        control_plots.append({
            'title': 'External Input',
            'image': create_control_plot(
                'External Input', inp_ext_l, inp_ext_r,
                'left', 'right', 'u'
            ),
        })

    # balancing_output: u_1 and u_2
    bal_out_1 = extract_control_data(['balancing_output', 'u_1'])
    bal_out_2 = extract_control_data(['balancing_output', 'u_2'])
    if np.any(bal_out_1) or np.any(bal_out_2):
        control_plots.append({
            'title': 'Balancing Output',
            'image': create_control_plot(
                'Balancing Output', bal_out_1, bal_out_2,
                'left', 'right', 'u'
            ),
        })

    # output: u_left and u_right
    out_l = extract_control_data(['output', 'u_left'])
    out_r = extract_control_data(['output', 'u_right'])
    if np.any(out_l) or np.any(out_r):
        control_plots.append({
            'title': 'Control Output',
            'image': create_control_plot(
                'Control Output', out_l, out_r,
                'left', 'right', 'u'
            ),
        })

    # Load template and render
    template_path = Path(__file__).parent / "experiment_report_template.html"
    report = Report(template_path, plot_dpi=120, plot_width="100%")

    report.render(
        title=f"Experiment Report: {exp_id}",
        experiment_id=exp_id,
        description=description,
        date=meta.get('date', ''),
        num_samples=len(samples),
        duration=duration,
        actions=actions_info,
        phase_actions=phase_actions,
        plots=plots,
        control_plots=control_plots,
        trajectory_map=trajectory_map,
        logs=logs,
    )

    # Output
    if output:
        if format == 'pdf':
            report.save_pdf(output)
        else:
            report.save_html(output)
    elif show:
        if format == 'pdf':
            report.show_pdf()
        else:
            report.show_html()

    return report


def _format_action_params(action_type: str, params: dict) -> str:
    """Format action parameters for display."""
    if not params:
        return ""

    # Special formatting for common action types
    if action_type == 'set_mode':
        return f"mode={params.get('mode', '?')}"
    elif action_type == 'set_velocity':
        fwd = params.get('forward', 0)
        turn = params.get('turn', 0)
        return f"v={fwd}, turn={turn}"
    elif action_type == 'wait_time':
        ms = params.get('time_ms', 0)
        return f"{ms/1000:.2f}s"
    elif action_type == 'wait_ticks':
        return f"{params.get('ticks', 0)} ticks"
    elif action_type == 'beep':
        freq = params.get('frequency', 1000)
        ms = params.get('time_ms', 250)
        return f"{freq}Hz, {ms}ms"
    elif action_type == 'speak':
        text = params.get('text', '')
        if len(text) > 40:
            text = text[:37] + '...'
        return f'"{text}"'
    elif action_type == 'move_to':
        x = params.get('x', 0)
        y = params.get('y', 0)
        return f"({x:.2f}, {y:.2f})"
    elif action_type == 'turn_to':
        if 'heading_deg' in params:
            return f"{params['heading_deg']:.1f} deg"
        return f"{params.get('heading', 0):.2f} rad"
    elif action_type == 'run_trajectory':
        traj = params.get('input_trajectory', {})
        if isinstance(traj, dict):
            name = traj.get('name', 'unnamed')
            return f"trajectory: {name}"
        return "trajectory"
    elif action_type == 'set_input':
        inp = params.get('input', [0, 0])
        return f"[{inp[0]:.3f}, {inp[1]:.3f}]"
    elif action_type == 'set_feedback_gain':
        K = params.get('K', [])
        if len(K) > 4:
            return f"K=[{K[0]:.2f}, {K[1]:.2f}, ... ({len(K)} elements)]"
        return f"K={K}"
    else:
        # Generic formatting
        parts = []
        for k, v in params.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.3f}")
            elif isinstance(v, (list, dict)) and len(str(v)) > 30:
                parts.append(f"{k}=...")
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts[:3])  # Limit to 3 params
