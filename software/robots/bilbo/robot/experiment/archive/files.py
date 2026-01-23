import dataclasses
import itertools
import time

import numpy as np
from dacite import Config
from matplotlib import pyplot as plt
from scipy.fft import rfft, rfftfreq
from scipy.signal import find_peaks

from core.utils.dataclass_utils import from_dict
from core.utils.json_utils import writeJSON, readJSON
from robots.bilbo.robot.experiment.definitions import BILBO_InputFileData, INPUT_TRAJECTORY_FILE_EXTENSION, \
    BILBO_InputTrajectory, BILBO_InputAnalytics, FrequencyComponent, BILBO_InputFileMeta, BILBO_InputTrajectoryStep
from robots.bilbo.robot.experiment.helpers import plotInputTrajectoryAnalytics


# ======================================================================================================================
def writeInputFile(file_name, folder, data: BILBO_InputFileData):
    data_dict = dataclasses.asdict(data)
    file_path = f"{folder}/{file_name}{INPUT_TRAJECTORY_FILE_EXTENSION}"
    try:
        writeJSON(file_path, data_dict)
    except Exception as e:
        print(f"Error writing input file: {e}")


# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------
def readInputFile(file_path) -> BILBO_InputFileData | None:
    config = Config(
        type_hooks={
            np.ndarray: lambda x: np.array(x),  # convert lists -> np.ndarray
            dict[int, BILBO_InputTrajectoryStep]: lambda d: {  # convert dicts -> dict[int, step]
                int(k): BILBO_InputTrajectoryStep(**v) for k, v in d.items()
            },
        }
    )

    try:
        data_dict = readJSON(file_path)
        data = from_dict(data_class=BILBO_InputFileData,
                         data=data_dict,
                         config=config)

        return data
    except Exception as e:
        print(f"Error reading input file: {e}")
        return None


# ----------------------------------------------------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------------------------------------------------
def generateInputTrajectoryFileData(input_trajectory: BILBO_InputTrajectory,
                                    name,
                                    description,
                                    experiment_id=None,
                                    experiment_index=None,
                                    version='1.0', ) -> BILBO_InputFileData:
    input_file_meta = BILBO_InputFileMeta(
        date=time.strftime("%Y-%m-%d-%H-%M-%S"),
        version="1.0",
        description=description,
        experiment_id=experiment_id,
        experiment_index=experiment_index,
        length=input_trajectory.length,
    )

    # analytics = generateInputTrajectoryAnalytics(input_trajectory)

    data = BILBO_InputFileData(
        name=name,
        meta=input_file_meta,
        trajectory=input_trajectory,
    )

    return data


def example():
    from robots.bilbo.robot.experiment.helpers import generateRandomTestTrajectory
    from robots.bilbo.robot.experiment.helpers import plotInputTrajectory

    trajectory = generateRandomTestTrajectory(0, 20, 2, 1)
    data = generateInputTrajectoryFileData(trajectory, "test", "test input trajectory")
    writeInputFile("test2", ".", data)

    readback = readInputFile("test2.bitrj")

    plotInputTrajectory(readback.trajectory)
    data = generateInputTrajectoryAnalytics(readback.trajectory)
    plotInputTrajectoryAnalytics(trajectory, data)
    print(data)


if __name__ == '__main__':
    example()
