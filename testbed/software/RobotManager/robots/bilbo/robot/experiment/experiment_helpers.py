import dataclasses
import time

import numpy as np
from scipy.fft import rfftfreq, rfft
from scipy.signal import find_peaks

from core.utils.data import generate_time_vector, generate_random_input
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory, BILBO_InputFileData, \
    BILBO_InputTrajectoryStep


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
