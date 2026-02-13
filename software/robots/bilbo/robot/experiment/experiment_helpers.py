from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np
import yaml
from scipy.fft import rfftfreq, rfft
from scipy.signal import find_peaks

from core.utils.control.lib_control.il.ilc import BILBO_BUMPED_REFERENCE_TRAJECTORY
from core.utils.data import generate_time_vector, generate_random_input, generate_time_vector_by_length
from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import file_exists, get_absolute_path
from core.utils.json_utils import readJSON
from core.utils.plotting.map_plot import MapPlot
from core.utils.plotting.plot import quick_plot
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment import OutputTrajectory
from robots.bilbo.robot.experiment.experiment_definitions import (
    InputTrajectory, InputTrajectoryFileData, InputTrajectoryStep,
    ExperimentData, ExperimentActionData, ExperimentActionStatus,
)

if TYPE_CHECKING:
    # from robots.bilbo.robot.experiment.experiment_definitions import ExperimentData
    from core.utils.report import Report


# === TRAJECTORY =======================================================================================================
def generate_trajectory_inputs(inputs: list | np.ndarray) -> list[InputTrajectoryStep]:
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

        trajectory_inputs.append(InputTrajectoryStep(
            step=i,
            left=left,
            right=right,
        ))
    return trajectory_inputs


def trajectory_inputs_to_list(trajectory_inputs: list[InputTrajectoryStep], single_input: bool = False) -> list:
    out = []
    for inp in trajectory_inputs:
        if not single_input:
            out.append([inp.left, inp.right])
        else:
            out.append(inp.left + inp.right)

    return out


def trajectory_inputs_to_vector(trajectory_inputs: list[InputTrajectoryStep],
                                single_input: bool = False) -> np.ndarray:
    return np.array(trajectory_inputs_to_list(trajectory_inputs, single_input=single_input))


def generate_random_input_trajectory(trajectory_id, time_s, frequency, gain, bias=0.0) -> InputTrajectory | None:
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
        bias: Constant offset added to the signal. Positive values bias the robot forward.

    Returns:
        InputTrajectory | None: The trajectory object containing the generated data or None
        if the trajectory exceeds the maximum allowed steps.
    """
    t_vector = generate_time_vector(start=0, end=time_s, dt=BILBO_CONTROL_DT)

    if len(t_vector) > MAX_STEPS_TRAJECTORY:
        print(f"Trajectory too long: {len(t_vector)} > {MAX_STEPS_TRAJECTORY} steps")
        return None

    trajectory_input = generate_random_input(t_vector=t_vector, f_cutoff=frequency, sigma_I=gain, bias=bias)
    trajectory_inputs = generate_trajectory_inputs(trajectory_input)

    trajectory = InputTrajectory(
        id=trajectory_id,
        name='test',
        dt=BILBO_CONTROL_DT,
        inputs=trajectory_inputs,
    )

    return trajectory


# === PLOTTING =========================================================================================================
def plot_input_trajectory(trajectory: InputTrajectory):
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


def generateInputTrajectoryAnalytics(input_trajectory: InputTrajectory,
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
        experiment: str | dict | ExperimentData,
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
    from robots.bilbo.robot.experiment.experiment_definitions import ExperimentData
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

    # Extract experiment status information
    exp_status = exp_dict.get('status', 'finished')
    error_action_id = exp_dict.get('error_action_id')
    error_message = exp_dict.get('error_message')

    # Determine if experiment was successful
    is_success = exp_status in ('finished', 'FINISHED')
    is_error = exp_status in ('error', 'ERROR')
    is_timeout = exp_status in ('timeout', 'TIMEOUT')
    is_aborted = exp_status in ('aborted', 'ABORTED')

    # Create status display info
    status_info = {
        'status': exp_status,
        'is_success': is_success,
        'is_error': is_error,
        'is_timeout': is_timeout,
        'is_aborted': is_aborted,
        'error_action_id': error_action_id,
        'error_message': error_message,
        'status_label': 'Success' if is_success else exp_status.upper() if isinstance(exp_status, str) else str(
            exp_status),
        'status_class': 'success' if is_success else 'error' if is_error else 'warning' if (
                    is_timeout or is_aborted) else 'unknown',
    }

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

    # First pass: identify group IDs to detect nested actions
    group_ids = set()
    for action_def in action_defs:
        if action_def is None:
            continue
        if action_def.get('type') == 'group':
            group_ids.add(action_def.get('id', ''))

    # Helper to check if an action is a sub-action of a group
    def is_sub_action(action_id: str) -> bool:
        for group_id in group_ids:
            if action_id.startswith(f"{group_id}_sub_"):
                return True
        return False

    # Helper to add action info (used recursively for groups)
    def process_action(action_def, index, is_nested=False, parent_sub_actions_data=None, depth=0):
        nonlocal color_index
        if action_def is None:
            return

        action_id = action_def.get('id', f'action_{index}')
        action_type = action_def.get('type', 'unknown')

        # Loops are expanded to groups at runtime — treat as group for processing
        if action_type == 'loop':
            action_type = 'group'

        # Extract parameters - handle both formats:
        # 1. Full format: {'type': 'set_velocity', 'parameters': {'forward': 0.5}}
        # 2. Shorthand format: {'type': 'set_velocity', 'forward': 0.5}
        reserved_fields = {'id', 'type', 'tick', 'after', 'time', 'delay', 'timeout', 'label', 'meta', 'parameters', 'actions', 'wait_before', 'wait_after'}
        if 'parameters' in action_def:
            params = action_def['parameters']
        else:
            # Collect all non-reserved fields as parameters (shorthand format)
            params = {k: v for k, v in action_def.items() if k not in reserved_fields}

        # Get timing and status from actions_data or parent's sub_actions
        if parent_sub_actions_data and action_id in parent_sub_actions_data:
            # Sub-action data is in parent's sub_actions field
            action_timing = parent_sub_actions_data.get(action_id) or {}
        else:
            # Top-level action data
            action_timing = actions_data.get(action_id) or {}

        start_time = action_timing.get('start_time')
        end_time = action_timing.get('end_time')
        start_tick = action_timing.get('start_tick') or 0
        end_tick = action_timing.get('end_tick') or 0

        # Get sub-actions data for group/parallel actions (for passing to nested processing)
        sub_actions_data = action_timing.get('sub_actions') or {}

        # Use parameters from action data if available (more accurate than definition)
        if action_timing.get('parameters'):
            params = action_timing.get('parameters')

        # Get action status and label
        action_status = action_timing.get('status', 'pending')
        action_error_message = action_timing.get('error_message')
        action_label = action_timing.get('label') or action_def.get('label')  # Prefer runtime data, fallback to definition
        action_meta = action_timing.get('meta') or action_def.get('meta')  # Prefer runtime data, fallback to definition
        # Use original_type from meta for display (e.g., 'loop', 'loop_iteration')
        display_type = (action_meta or {}).get('original_type', action_type)
        is_action_error = action_status in ('error', 'ERROR')
        is_action_success = action_status in ('completed', 'COMPLETED', 'finished', 'FINISHED')
        is_action_pending = action_status in ('pending', 'PENDING')

        # Check if this is the error action
        is_error_action_flag = (error_action_id == action_id)

        # Check if action spans multiple ticks (has duration)
        has_phase = (end_tick - start_tick) > 1 if start_tick is not None and end_tick is not None else False

        # Assign color for labeled actions with duration
        color = None
        if has_phase and action_label:
            color = PHASE_COLORS[color_index % len(PHASE_COLORS)]
            color_index += 1
            phase_actions.append({
                'id': action_id,
                'label': action_label,
                'type': action_type,
                'color': color,
                'start_time': start_time,
                'end_time': end_time,
                'label_layer': (action_meta or {}).get('label_layer', 0),
            })

        # Format parameters for display (exclude nested actions from params string for groups)
        params_for_display = {k: v for k, v in params.items() if k not in ('actions', 'actions_count')}
        params_str = _format_action_params(action_type, params_for_display)
        if action_type in ('group', 'parallel'):
            # Count sub-actions from data if available, otherwise from definition
            # Check both top-level 'actions' (new format) and params (old format)
            def_actions = action_def.get('actions', []) or params.get('actions', [])
            num_sub_actions = len(sub_actions_data) if sub_actions_data else params.get('actions_count', len(def_actions))
            params_str = f"{num_sub_actions} actions"

        # Extract path points for set_path/set_waypoints actions
        waypoints = None
        if action_type in ('set_path', 'set_waypoints'):
            raw_points = params.get('points', params.get('waypoints', []))
            waypoints = []
            for pt in raw_points:
                if isinstance(pt, dict):
                    waypoints.append({
                        'x': pt.get('x', 0),
                        'y': pt.get('y', 0),
                    })
                elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    waypoints.append({
                        'x': pt[0],
                        'y': pt[1],
                    })

        actions_info.append({
            'index': index,
            'id': action_id,
            'type': display_type,
            'label': action_label,
            'params_str': params_str,
            'start_time': start_time,
            'end_time': end_time,
            'has_phase': has_phase,
            'color': color,
            'status': action_status,
            'is_error': is_action_error,
            'is_success': is_action_success,
            'is_pending': is_action_pending,
            'is_error_action': is_error_action_flag,
            'error_message': action_error_message,
            'is_nested': is_nested,
            'depth': depth,
            'is_group': action_type in ('group', 'parallel'),
            'waypoints': waypoints,
        })

        # If this is a group/parallel action, process its sub-actions
        if action_type in ('group', 'parallel') and sub_actions_data:
            # Process sub-actions using the data from parent's sub_actions field
            for sub_idx, (sub_action_id, sub_action_data) in enumerate(sub_actions_data.items()):
                sub_params = sub_action_data.get('parameters') or {}

                # Get action type from data (preferred) or infer from parameters
                sub_action_type = sub_action_data.get('action_type')
                if not sub_action_type:
                    sub_action_type = _infer_type_from_params(sub_params)

                # Create a synthetic action def for processing
                sub_action_def = {
                    'id': sub_action_id,
                    'type': sub_action_type,
                    'label': sub_action_data.get('label'),
                    'parameters': sub_params,
                }
                process_action(sub_action_def, f"{index}.{sub_idx}", is_nested=True, parent_sub_actions_data=sub_actions_data, depth=depth + 1)
        elif action_type in ('group', 'parallel'):
            # Fallback: use definition-based sub-actions (when no runtime data available)
            # Look for 'actions' at top level (new format) or in params (old format)
            sub_actions_defs = action_def.get('actions', []) or params.get('actions', [])
            for sub_idx, sub_action in enumerate(sub_actions_defs):
                sub_action_id = sub_action.get('id', f"{action_id}_sub_{sub_idx}")
                sub_action_with_id = dict(sub_action)
                sub_action_with_id['id'] = sub_action_id
                process_action(sub_action_with_id, f"{index}.{sub_idx}", is_nested=True, parent_sub_actions_data=None, depth=depth + 1)

    def _infer_type_from_params(params: dict) -> str:
        """Try to infer action type from parameters."""
        # Check for common parameter patterns
        if 'mode' in params:
            return 'set_mode'
        if 'forward' in params or 'turn' in params:
            return 'set_velocity'
        if 'time_ms' in params:
            return 'wait_time'
        if 'ticks' in params:
            return 'wait_ticks'
        if 'frequency' in params:
            return 'beep'
        if 'text' in params:
            return 'speak'
        if 'x' in params and 'y' in params:
            return 'move_to'
        if 'heading' in params or 'heading_deg' in params:
            return 'turn_to'
        if 'input' in params:
            return 'set_input'
        if 'points' in params:
            return 'set_path'
        if 'waypoints' in params:
            return 'set_waypoints'
        if 'K' in params:
            return 'set_feedback_gain'
        return 'unknown'

    for i, action_def in enumerate(action_defs):
        process_action(action_def, i, is_nested=False, parent_sub_actions_data=None)

    # Phase bar height as fraction of plot (used for ylim adjustment)
    PHASE_BAR_HEIGHT = 0.07

    # Helper to calculate ylim with padding for phase bar
    # Determine the number of phase bar layers needed
    num_phase_layers = max((p.get('label_layer', 0) for p in phase_actions), default=0) + 1 if phase_actions else 1

    def calc_ylim_with_phase_padding(*data_arrays):
        """Calculate ylim that leaves room for phase bar at bottom."""
        all_data = np.concatenate([d for d in data_arrays if len(d) > 0])
        y_min, y_max = np.min(all_data), np.max(all_data)
        y_range = y_max - y_min
        if y_range == 0:
            y_range = 1.0  # Avoid division by zero
        # Add padding: small margin at top, larger at bottom for phase bar(s)
        padding_top = 0.05 * y_range
        total_phase_height = PHASE_BAR_HEIGHT * num_phase_layers
        padding_bottom = (total_phase_height / (1 - total_phase_height)) * y_range + 0.05 * y_range
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
                        phase['label'],
                        start=phase['start_time'],
                        end=phase['end_time'],
                        color=phase['color'],
                        layer=phase.get('label_layer', 0),
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
                        phase_id=phase['label'],
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

    # Generate YAML representation of the experiment definition
    experiment_yaml_raw = ''
    experiment_yaml_highlighted = ''
    if definition:
        try:
            # Prefer the original source dict (preserves loop syntax, shorthand, etc.)
            source = definition.get('source_dict') or definition
            # Strip internal fields that shouldn't appear in the output YAML
            yaml_dict = {k: v for k, v in source.items() if not k.startswith('_') and k != 'source_dict'}
            experiment_yaml_raw = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False)
            experiment_yaml_highlighted = _highlight_yaml(experiment_yaml_raw)
        except Exception as e:
            # If YAML generation fails, just skip it
            experiment_yaml_raw = f"# Error generating YAML: {e}"
            experiment_yaml_highlighted = f'<span class="yaml-comment"># Error generating YAML: {e}</span>'

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
        status=status_info,
        actions=actions_info,
        phase_actions=phase_actions,
        plots=plots,
        control_plots=control_plots,
        trajectory_map=trajectory_map,
        logs=logs,
        experiment_yaml=bool(experiment_yaml_raw),
        experiment_yaml_raw=experiment_yaml_raw,
        experiment_yaml_highlighted=experiment_yaml_highlighted,
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


def read_experiment_data(file: str) -> ExperimentData:
    if not file_exists(file):
        raise FileNotFoundError(f"Experiment data file not found: {file}")

    data_dict = readJSON(file)

    data = from_dict_auto(ExperimentData, data_dict)

    return data


# === EXPERIMENT DATA EXTRACTION =======================================================================================

@dataclasses.dataclass
class ActionSamplesResult:
    """Result of extracting samples for an action."""
    action_id: str
    action_data: ExperimentActionData
    samples: list
    start_tick: int
    end_tick: int
    start_time: float
    end_time: float
    duration: float


@dataclasses.dataclass
class GroupSamplesResult:
    """Result of extracting samples for a group action."""
    group_id: str
    group_data: ExperimentActionData
    samples: list
    start_tick: int
    end_tick: int
    start_time: float
    end_time: float
    duration: float
    sub_actions: dict[str, ActionSamplesResult]  # Sub-action ID -> ActionSamplesResult


@dataclasses.dataclass
class ExperimentSummary:
    """Summary of an experiment."""
    id: str
    status: str
    description: str
    duration: float
    num_samples: int
    num_actions: int
    num_completed_actions: int
    num_failed_actions: int
    num_skipped_actions: int
    error_action_id: str | None
    error_message: str | None


def get_action_data(data: ExperimentData, action_id: str) -> ExperimentActionData | None:
    """Get the ExperimentActionData for a specific action.

    Args:
        data: The experiment data
        action_id: The action ID to look up

    Returns:
        ExperimentActionData or None if not found
    """
    return data.actions.get(action_id)


def get_action_samples(data: ExperimentData, action_id: str) -> ActionSamplesResult | None:
    """Get samples and data for a specific action by ID.

    Args:
        data: The experiment data
        action_id: The action ID to extract samples for

    Returns:
        ActionSamplesResult containing the action data and filtered samples,
        or None if the action is not found

    Example:
        result = get_action_samples(experiment_data, 'forward_velocity')
        print(f"Action ran for {result.duration:.2f}s with {len(result.samples)} samples")
        for sample in result.samples:
            print(f"  tick={sample.tick}, v={sample.estimation.state.v}")
    """
    action_data = data.actions.get(action_id)
    if action_data is None:
        return None

    start_tick = action_data.start_tick
    end_tick = action_data.end_tick

    # Filter samples within the action's tick range
    samples = [s for s in data.samples if start_tick <= s.tick <= end_tick]

    return ActionSamplesResult(
        action_id=action_id,
        action_data=action_data,
        samples=samples,
        start_tick=start_tick,
        end_tick=end_tick,
        start_time=action_data.start_time,
        end_time=action_data.end_time,
        duration=action_data.end_time - action_data.start_time,
    )


def get_group_samples(data: ExperimentData, group_id: str) -> GroupSamplesResult | None:
    """Get samples and data for a group action, including sub-action data.

    This function extracts the samples for a group action and also provides
    data for each sub-action within the group.

    Args:
        data: The experiment data
        group_id: The group action ID

    Returns:
        GroupSamplesResult containing the group data, samples, and sub-action data,
        or None if the group is not found

    Example:
        result = get_group_samples(experiment_data, 'velocity_test')
        print(f"Group ran for {result.duration:.2f}s")
        for sub_id, sub_result in result.sub_actions.items():
            print(f"  {sub_id}: {sub_result.duration:.2f}s, {len(sub_result.samples)} samples")
    """
    group_data = data.actions.get(group_id)
    if group_data is None:
        return None

    start_tick = group_data.start_tick
    end_tick = group_data.end_tick

    # Filter samples within the group's tick range
    samples = [s for s in data.samples if start_tick <= s.tick <= end_tick]

    # Find sub-actions (they have IDs like "{group_id}_sub_0", "{group_id}_sub_1", etc.)
    sub_actions = {}
    sub_action_prefix = f"{group_id}_sub_"

    for action_id, action_data in data.actions.items():
        if action_id.startswith(sub_action_prefix):
            sub_start = action_data.start_tick
            sub_end = action_data.end_tick
            sub_samples = [s for s in data.samples if sub_start <= s.tick <= sub_end]

            sub_actions[action_id] = ActionSamplesResult(
                action_id=action_id,
                action_data=action_data,
                samples=sub_samples,
                start_tick=sub_start,
                end_tick=sub_end,
                start_time=action_data.start_time,
                end_time=action_data.end_time,
                duration=action_data.end_time - action_data.start_time,
            )

    return GroupSamplesResult(
        group_id=group_id,
        group_data=group_data,
        samples=samples,
        start_tick=start_tick,
        end_tick=end_tick,
        start_time=group_data.start_time,
        end_time=group_data.end_time,
        duration=group_data.end_time - group_data.start_time,
        sub_actions=sub_actions,
    )


def get_samples_by_tick_range(data: ExperimentData, start_tick: int, end_tick: int) -> list:
    """Get samples within a specific tick range.

    Args:
        data: The experiment data
        start_tick: Start tick (inclusive)
        end_tick: End tick (inclusive)

    Returns:
        List of samples within the tick range
    """
    return [s for s in data.samples if start_tick <= s.tick <= end_tick]


def get_samples_by_time_range(data: ExperimentData, start_time: float, end_time: float,
                              dt: float = 0.01) -> list:
    """Get samples within a specific time range.

    Args:
        data: The experiment data
        start_time: Start time in seconds (inclusive)
        end_time: End time in seconds (inclusive)
        dt: Sample period in seconds (default 0.01 = 100Hz)

    Returns:
        List of samples within the time range
    """
    start_tick = int(start_time / dt)
    end_tick = int(end_time / dt)
    return get_samples_by_tick_range(data, start_tick, end_tick)


def extract_state_vector(samples: list, state_name: str, source: str = 'lowlevel') -> np.ndarray:
    """Extract a state variable as a numpy array from samples.

    Args:
        samples: List of BILBO_Sample objects or dicts
        state_name: Name of the state variable (e.g., 'theta', 'v', 'x', 'y', 'psi')
        source: Data source - 'lowlevel' (100Hz, default) or 'estimation' (10Hz)

    Returns:
        Numpy array of the state values

    Example:
        result = get_action_samples(data, 'forward_velocity')
        theta = extract_state_vector(result.samples, 'theta')
        velocity = extract_state_vector(result.samples, 'v')
    """
    values = []
    for s in samples:
        if isinstance(s, dict):
            if source == 'lowlevel':
                ll = s.get('lowlevel') or {}
                ll_est = ll.get('estimation') or {}
                ll_state = ll_est.get('state') or {}
                values.append(ll_state.get(state_name, 0.0) or 0.0)
            else:
                est = s.get('estimation') or {}
                state = est.get('state') or {}
                values.append(state.get(state_name, 0.0) or 0.0)
        else:
            # Assume it's a BILBO_Sample dataclass
            if source == 'lowlevel':
                values.append(getattr(s.lowlevel.estimation.state, state_name, 0.0) or 0.0)
            else:
                values.append(getattr(s.estimation.state, state_name, 0.0) or 0.0)
    return np.array(values)


def extract_control_vector(samples: list, path: list[str]) -> np.ndarray:
    """Extract a control variable as a numpy array from samples.

    Args:
        samples: List of BILBO_Sample objects or dicts
        path: Path to the control variable, e.g., ['velocity_command', 'v']

    Returns:
        Numpy array of the control values

    Example:
        velocity_cmd = extract_control_vector(samples, ['velocity_command', 'v'])
        torque_left = extract_control_vector(samples, ['output', 'u_left'])
    """
    values = []
    for s in samples:
        if isinstance(s, dict):
            ll = s.get('lowlevel') or {}
            ctrl = ll.get('control') or {}
            val = ctrl
            for key in path:
                val = (val.get(key) if isinstance(val, dict) else None) or {}
            values.append(val if isinstance(val, (int, float)) else 0.0)
        else:
            # Assume it's a BILBO_Sample dataclass
            val = s.lowlevel.control
            for key in path:
                val = getattr(val, key, None)
                if val is None:
                    val = 0.0
                    break
            values.append(val if isinstance(val, (int, float)) else 0.0)
    return np.array(values)


def get_time_vector(samples: list, dt: float = 0.01) -> np.ndarray:
    """Generate a time vector for a list of samples.

    Args:
        samples: List of samples
        dt: Sample period in seconds (default 0.01 = 100Hz)

    Returns:
        Numpy array of time values starting from 0
    """
    return np.arange(len(samples)) * dt


def get_experiment_summary(data: ExperimentData) -> ExperimentSummary:
    """Get a summary of the experiment.

    Args:
        data: The experiment data

    Returns:
        ExperimentSummary with key statistics

    Example:
        summary = get_experiment_summary(experiment_data)
        print(f"Experiment {summary.id}: {summary.status}")
        print(f"  Duration: {summary.duration:.2f}s, {summary.num_samples} samples")
        print(f"  Actions: {summary.num_completed_actions}/{summary.num_actions} completed")
    """
    num_completed = 0
    num_failed = 0
    num_skipped = 0

    for action_data in data.actions.values():
        status = action_data.status
        if isinstance(status, str):
            status_str = status
        else:
            status_str = status.value if hasattr(status, 'value') else str(status)

        if status_str == 'finished':
            num_completed += 1
        elif status_str in ('error', 'timeout'):
            num_failed += 1
        elif status_str == 'skipped':
            num_skipped += 1

    # Calculate duration from samples
    duration = len(data.samples) * 0.01 if data.samples else 0.0

    # Get description
    description = ''
    if data.definition:
        description = data.definition.description
    elif data.meta:
        description = data.meta.description

    # Get status as string
    status_str = data.status.value if hasattr(data.status, 'value') else str(data.status)

    return ExperimentSummary(
        id=data.id,
        status=status_str,
        description=description,
        duration=duration,
        num_samples=len(data.samples),
        num_actions=len(data.actions),
        num_completed_actions=num_completed,
        num_failed_actions=num_failed,
        num_skipped_actions=num_skipped,
        error_action_id=data.error_action_id,
        error_message=data.error_message,
    )


def get_failed_actions(data: ExperimentData) -> list[tuple[str, ExperimentActionData]]:
    """Get a list of actions that failed (error or timeout).

    Args:
        data: The experiment data

    Returns:
        List of tuples (action_id, action_data) for failed actions

    Example:
        failed = get_failed_actions(experiment_data)
        for action_id, action_data in failed:
            print(f"Action {action_id} failed: {action_data.error_message}")
    """
    failed = []
    for action_id, action_data in data.actions.items():
        status = action_data.status
        if isinstance(status, str):
            status_str = status
        else:
            status_str = status.value if hasattr(status, 'value') else str(status)

        if status_str in ('error', 'timeout'):
            failed.append((action_id, action_data))
    return failed


def get_action_duration(data: ExperimentData, action_id: str) -> float | None:
    """Get the duration of an action in seconds.

    Args:
        data: The experiment data
        action_id: The action ID

    Returns:
        Duration in seconds, or None if action not found
    """
    action_data = data.actions.get(action_id)
    if action_data is None:
        return None
    return action_data.end_time - action_data.start_time


def get_actions_by_type(data: ExperimentData, action_type: str) -> list[tuple[str, ExperimentActionData]]:
    """Get all actions of a specific type.

    Args:
        data: The experiment data
        action_type: The action type (e.g., 'set_velocity', 'group', 'wait_time')

    Returns:
        List of tuples (action_id, action_data) for matching actions

    Example:
        velocity_actions = get_actions_by_type(data, 'set_velocity')
        for action_id, action_data in velocity_actions:
            print(f"{action_id}: forward={action_data.parameters.get('forward')}")
    """
    if data.definition is None:
        return []

    results = []
    for action_def in data.definition.actions:
        if action_def.type == action_type:
            action_data = data.actions.get(action_def.id)
            if action_data:
                results.append((action_def.id, action_data))
    return results


def get_groups(data: ExperimentData) -> list[tuple[str, ExperimentActionData]]:
    """Get all group actions in the experiment.

    Args:
        data: The experiment data

    Returns:
        List of tuples (group_id, group_data) for all groups

    Example:
        groups = get_groups(experiment_data)
        for group_id, group_data in groups:
            result = get_group_samples(experiment_data, group_id)
            print(f"Group {group_id}: {result.duration:.2f}s")
    """
    return get_actions_by_type(data, 'group')


def _highlight_yaml(yaml_str: str) -> str:
    """Apply HTML syntax highlighting to YAML string."""
    import html
    lines = yaml_str.split('\n')
    highlighted_lines = []

    for line in lines:
        # Escape HTML entities first
        escaped = html.escape(line)

        # Check if it's a comment
        stripped = escaped.strip()
        if stripped.startswith('#'):
            highlighted_lines.append(f'<span class="yaml-comment">{escaped}</span>')
            continue

        # Check for key: value pattern
        if ':' in escaped:
            colon_idx = escaped.index(':')
            # Check if there's content after the colon
            key_part = escaped[:colon_idx]
            rest = escaped[colon_idx:]

            # Highlight the key
            highlighted = f'<span class="yaml-key">{key_part}</span>'

            # Check what comes after the colon
            value_part = rest[1:].strip() if len(rest) > 1 else ''

            if value_part:
                # It's a key: value on same line
                if value_part.startswith("'") or value_part.startswith('"'):
                    # String value
                    highlighted += f':<span class="yaml-string"> {value_part}</span>'
                elif value_part in ('true', 'false', 'True', 'False'):
                    # Boolean
                    highlighted += f':<span class="yaml-boolean"> {value_part}</span>'
                elif value_part in ('null', 'None', '~'):
                    # Null
                    highlighted += f':<span class="yaml-null"> {value_part}</span>'
                elif value_part.replace('.', '').replace('-', '').replace('e', '').replace('E', '').isdigit():
                    # Number (including floats and scientific notation)
                    highlighted += f':<span class="yaml-number"> {value_part}</span>'
                else:
                    # Unquoted string or other
                    highlighted += f':<span class="yaml-string"> {value_part}</span>'
            else:
                # Just key: with nothing after (nested object or list follows)
                highlighted += ':'

            highlighted_lines.append(highlighted)
        elif stripped.startswith('-'):
            # List item
            indent = len(escaped) - len(escaped.lstrip())
            marker_idx = escaped.index('-')
            indent_part = escaped[:marker_idx]
            rest = escaped[marker_idx + 1:].strip()

            highlighted = f'{indent_part}<span class="yaml-list-marker">-</span>'
            if rest:
                # Check if it's a key: value after the list marker
                if ':' in rest:
                    highlighted += ' ' + _highlight_yaml(rest).strip()
                else:
                    highlighted += f'<span class="yaml-string"> {rest}</span>'
            highlighted_lines.append(highlighted)
        else:
            # Plain text (likely a string value continuation)
            highlighted_lines.append(f'<span class="yaml-string">{escaped}</span>' if escaped.strip() else escaped)

    return '\n'.join(highlighted_lines)


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
        return f"{ms / 1000:.2f}s"
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
    elif action_type in ('set_path', 'set_waypoints'):
        points = params.get('points', params.get('waypoints', []))
        return f"{len(points)} path points"
    elif action_type == 'start_path':
        parts = []
        if params.get('max_speed', 0) > 0:
            parts.append(f"speed={params['max_speed']}")
        if params.get('timeout', 0) > 0:
            parts.append(f"timeout={params['timeout']}s")
        if params.get('allow_reverse'):
            parts.append("reverse=yes")
        return ", ".join(parts) if parts else ""
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


if __name__ == '__main__':
    import os
    from robots.bilbo.settings import get_settings
    from robots.bilbo.robot.experiment.experiment_definitions import (
        write_output_file, OUTPUT_TRAJECTORY_FILE_EXTENSION,
    )

    settings = get_settings()
    reference_dir = (settings.get('paths') or {}).get('reference_trajectories')
    if reference_dir is None:
        raise RuntimeError("No 'paths.reference_trajectories' configured in settings.yaml")
    os.makedirs(reference_dir, exist_ok=True)

    y = BILBO_BUMPED_REFERENCE_TRAJECTORY + 0.04414553

    trajectory = OutputTrajectory(
        output_name='theta',
        output=y.tolist(),
        dt=0.01,
    )

    file_data = trajectory.to_file_data(
        id='bumped_reference',
        description='Bumped reference trajectory for DILC theta tracking',
    )

    filepath = os.path.join(reference_dir, f"bumped_reference{OUTPUT_TRAJECTORY_FILE_EXTENSION}")
    write_output_file(filepath, file_data)
    print(f"Saved reference trajectory to: {filepath}")



    # data = read_experiment_data(
    #     '/Users/lehmann/Desktop/velocity_group_test_2026-02-05_20-06-22.json'
    # )
    #
    # make_report(data)


    # x = [sample.estimation.state.x for sample in data.samples]
    # y = [sample.estimation.state.y for sample in data.samples]
    # x_ll = [sample.lowlevel.estimation.state.x for sample in data.samples]
    # y_ll = [sample.lowlevel.estimation.state.y for sample in data.samples]
    # time_vector = generate_time_vector_by_length(num_samples=len(x), dt=0.01)
    #
    # quick_plot(time_vector, x)  # in 10 Hz steps
    # quick_plot(time_vector, x_ll)  # in 100 Hz steps
    #
    # # quick map plot
    #
    # map_plot = MapPlot(size=((0,3), (0,3)))
    # map_plot.add_grid()
    # map_plot.add_coordinate_system(length=0.3)
    #
    # map_plot.add_trajectory(x, y,
    #                         width=2,
    #                         show_start=True,
    #                         show_end=True,
    #                         gradient=True,
    #                         gradient_cmap='viridis',
    #                         )
    #
    # # Extract waypoints from position control samples (avoid duplicates)
    # seen_waypoints = set()
    # wp_index = 1
    # for sample in data.samples:
    #     waypoints = sample.control.position_control.waypoints
    #     for wp in waypoints:
    #         if isinstance(wp, dict):
    #             wx = wp.get('x', 0.0)
    #             wy = wp.get('y', 0.0)
    #             key = (round(wx, 6), round(wy, 6))
    #             if key not in seen_waypoints:
    #                 seen_waypoints.add(key)
    #                 label_pos = 'bottom' if wy < 1.5 else 'top'
    #                 map_plot.add_point(
    #                     position=(wx, wy),
    #                     color='#e74c3c',
    #                     size=0.08,
    #                     marker='o',
    #                     border=True,
    #                     border_color='black',
    #                     border_width=1.5,
    #                     label=f'WP{wp_index}',
    #                     label_position=label_pos,
    #                     label_fontsize=10,
    #                 )
    #                 wp_index += 1
    #
    # map_plot.show_pdf()
