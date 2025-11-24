import numpy as np
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from core.utils.data import generate_time_vector, generate_random_input
from core.utils.plotting import ThreadPlot, use_headless_backend, new_figure_agg, save_figure
from robots.bilbo.robot.bilbo_definitions import BILBO_CONTROL_DT, MAX_STEPS_TRAJECTORY, BILBO_Control_Mode
from robots.bilbo.robot.experiment.definitions import BILBO_InputTrajectoryStep, BILBO_InputTrajectory, \
    BILBO_InputAnalytics, BILBO_TrajectoryExperimentData, BILBO_TrajectoryExperiment


def generateTrajectoryInputsFromList(trajectory_inputs: list) -> list:
    """
    Generates a dictionary of `BILBO_InputTrajectoryStep` objects from a list of inputs.

    This function processes a list of trajectory inputs and calculates the left and
    right input values for each step. If an input is a list, its first and second
    values are used directly as left and right inputs. If an input is not a list,
    the input value is evenly split into left and right inputs. The function
    returns a dictionary where keys represent step indices, and values are
    `BILBO_InputTrajectoryStep` objects representing each step.

    Args:
        trajectory_inputs (list): A list of inputs where each element is either a
            single value or a list of two values. Single values are split equally
            into left and right inputs. Lists specify directly the left and right
            input values.

    Returns:
        dict: A dictionary where keys are step indices (int), and values are
        `BILBO_InputTrajectoryStep` objects representing the corresponding trajectory step.
    """
    trajectory_inputs_list = []

    for i, inp in enumerate(trajectory_inputs):
        if isinstance(inp, list):
            input_left = float(inp[0])
            input_right = float(inp[1])
        else:
            input_left = float(inp) / 2
            input_right = float(inp) / 2

        trajectory_inputs_list.append(BILBO_InputTrajectoryStep(
            step=i,
            left=input_left,
            right=input_right,
        ))

    return trajectory_inputs_list


def generateTrajectoryInputsFromVector(trajectory_input_vector: np.ndarray) -> list:
    """
    Generates a dictionary of `BILBO_InputTrajectoryStep` objects from a vector of inputs.
    """
    return generateTrajectoryInputsFromList(trajectory_input_vector.tolist())


# ----------------------------------------------------------------------------------------------------------------------
def trajectoryInputToList(trajectory_inputs: list[BILBO_InputTrajectoryStep], single_input: bool = False) -> list:
    out = []
    for inp in trajectory_inputs:
        if not single_input:
            out.append([inp.left, inp.right])
        else:
            out.append(inp.left + inp.right)

    return out


# ----------------------------------------------------------------------------------------------------------------------
def trajectoryInputToVector(trajectory_inputs: list[BILBO_InputTrajectoryStep],
                            single_input: bool = False) -> np.ndarray:
    return np.array(trajectoryInputToList(trajectory_inputs, single_input))


# ----------------------------------------------------------------------------------------------------------------------
def generateRandomTestTrajectory(trajectory_id, time_s, frequency, gain) -> BILBO_InputTrajectory | None:
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
    trajectory_inputs = generateTrajectoryInputsFromList(trajectory_input)

    trajectory = BILBO_InputTrajectory(
        id=trajectory_id,
        time_vector=t_vector,
        name='test',
        length=len(trajectory_inputs),
        inputs=trajectory_inputs,
        control_mode=BILBO_Control_Mode.BALANCING,
    )

    return trajectory


# ======================================================================================================================
def plotInputTrajectory(trajectory: BILBO_InputTrajectory):
    input_left = [inp.left for inp in trajectory.inputs]
    input_right = [inp.right for inp in trajectory.inputs]
    plt.plot(input_left, label='left')
    plt.plot(input_right, label='right')
    plt.grid()
    plt.legend()
    plt.show()


def plotTrajectoryExperimentData(
        experiment: BILBO_TrajectoryExperiment,
        show_figure: bool = True,
) -> "Figure":
    """
    Plot the input (left/right) on the top axis and each selected state in its own subplot,
    then save the figure as a vector PDF and (optionally) open it in Preview (macOS).

    States plotted: v, theta, theta_dot, psi_dot.
    A non-overlapping header row shows experiment metadata: ID, robot_id, timestamp, description, etc.
    """
    import os
    import subprocess
    import tempfile

    use_headless_backend()

    # --- Unpack experiment data ---
    data = experiment.data
    meta = experiment.meta

    # --- Extract time vectors ---
    t_in = np.asarray(data.input_trajectory.time_vector).flatten()
    t_st = np.asarray(data.state_trajectory.time_vector).flatten()

    # --- Extract input signals ---
    left = np.array([s.left for s in data.input_trajectory.inputs], dtype=float)
    right = np.array([s.right for s in data.input_trajectory.inputs], dtype=float)

    # --- Extract states ---
    v = np.array([s.v for s in data.state_trajectory.states], dtype=float)
    theta = np.array([s.theta for s in data.state_trajectory.states], dtype=float)
    theta_dot = np.array([s.theta_dot for s in data.state_trajectory.states], dtype=float)
    psi_dot = np.array([s.psi_dot for s in data.state_trajectory.states], dtype=float)

    # --- Sanity checks and alignment ---
    n_in = min(len(t_in), len(left), len(right))
    t_in, left, right = t_in[:n_in], left[:n_in], right[:n_in]

    n_st = min(len(t_st), len(v), len(theta), len(theta_dot), len(psi_dot))
    t_st = t_st[:n_st]
    v, theta, theta_dot, psi_dot = v[:n_st], theta[:n_st], theta_dot[:n_st], psi_dot[:n_st]

    # --- Compute handy timing info for header ---
    def _med_dt(t):
        if t.size < 2:
            return None
        d = np.diff(t)
        d = d[d > 0]
        return float(np.median(d)) if d.size else None

    duration_in = float(t_in[-1] - t_in[0]) if t_in.size >= 2 else None
    duration_st = float(t_st[-1] - t_st[0]) if t_st.size >= 2 else None
    Ts_in = _med_dt(t_in)
    Ts_st = _med_dt(t_st)

    # --- Build figure (dedicated header band to avoid overlap) ---
    fig, _ = new_figure_agg(figsize=(16, 12), dpi=200)
    fig.clear()
    fig.set_constrained_layout(True)

    gs = fig.add_gridspec(6, 1, height_ratios=[0.55, 1.0, 1.0, 1.0, 1.0, 1.0])

    # --- Header row ---
    header_ax = fig.add_subplot(gs[0, 0])
    header_ax.axis("off")

    meta_lines = []

    # IDs
    meta_lines.append(
        f"Experiment ID: {getattr(experiment, 'id', '—')}   •   "
        f"Robot ID: {getattr(meta, 'robot_id', '—')}"
    )

    # Timestamp (if available from input trajectory meta)
    timestamp = getattr(getattr(data, "input_trajectory", None), "meta", None)
    if timestamp and hasattr(timestamp, "date"):
        meta_lines.append(f"Timestamp: {timestamp.date}")

    # Timing info
    time_bits = []
    if duration_in is not None:
        time_bits.append(f"Input duration: {duration_in:.3f} s")
    if duration_st is not None and (duration_in is None or abs(duration_st - duration_in) > 1e-6):
        time_bits.append(f"State duration: {duration_st:.3f} s")
    if Ts_in is not None:
        time_bits.append(f"Input Ts≈{Ts_in:.2f} s")
    if Ts_st is not None and (Ts_in is None or abs(Ts_st - Ts_in) > 1e-9):
        time_bits.append(f"State Ts≈{Ts_st:.4f} s")
    if time_bits:
        meta_lines.append("  •  ".join(time_bits))

    # Description
    desc = getattr(meta, "description", None)
    if desc:
        meta_lines.append(f"Description: {desc}")

    # Software revision
    rev = getattr(meta, "software_revision", None)
    if rev:
        meta_lines.append(f"Software Revision: {rev}")

    header_ax.text(
        0.0, 0.98,
        "\n".join(meta_lines),
        transform=header_ax.transAxes,
        va="top",
        ha="left",
        fontsize=12
    )

    # --- Top: Inputs
    ax_in = fig.add_subplot(gs[1, 0])
    ax_in.plot(t_in, left, label="Left input")
    ax_in.plot(t_in, right, label="Right input")
    ax_in.set_title("Inputs")
    ax_in.set_xlabel("Time [s]")
    ax_in.set_ylabel("Amplitude")
    ax_in.grid(True, alpha=0.3)
    ax_in.legend(loc="best")

    # --- State subplots
    states = [
        (v, "v", "m/s", -2.0, 2.0, 1.0),
        (theta, "theta", "deg", "auto", "auto", 180.0 / np.pi),
        (theta_dot, "theta_dot", "deg/s", -360, 360, 180.0 / np.pi),
        (psi_dot, "psi_dot", "deg/s", -600, 600, 180.0 / np.pi),
    ]
    for i, (vals, name, units, ylim_min, ylim_max, scale) in enumerate(states, start=2):
        ax = fig.add_subplot(gs[i, 0])
        ax.plot(t_st, vals * scale, label=name)
        ax.set_title(name)
        ax.set_xlabel("Time [s]")
        ax.set_ylabel(f"{name} [{units}]")
        if ylim_min != "auto" and ylim_max != "auto":
            ax.set_ylim(ylim_min, ylim_max)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")

    # --- Save as vector PDF ---
    pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = pdf_file.name
    pdf_file.close()

    save_figure(fig, pdf_path, fmt="pdf", transparent=False, bbox_inches="tight", pad_inches=0.1)

    if show_figure:
        try:
            subprocess.Popen(["open", "-a", "Preview", pdf_path])
        except Exception:
            try:
                subprocess.Popen(["open", pdf_path])
            except Exception:
                pass

    return fig


# ======================================================================================================================
def plotInputTrajectoryAnalytics(input_trajectory: BILBO_InputTrajectory,
                                 analytics: BILBO_InputAnalytics,
                                 show: bool = True,
                                 save_path: str = None):
    """
    Plot time-domain signals and FFT spectrum with dominant frequency components.

    Args:
        input_trajectory: The input trajectory (contains left/right signals & time_vector).
        analytics: The computed BILBO_InputAnalytics object from generateInputTrajectoryAnalytics.
        show: Whether to display the plot interactively.
        save_path: If provided, save the figure to this path instead of (or in addition to) showing it.
    """
    steps = input_trajectory.length
    time_vector = input_trajectory.time_vector

    left_signal = np.array([inp.left for inp in input_trajectory.inputs])
    right_signal = np.array([inp.right for inp in input_trajectory.inputs])

    combined_signal = 0.5 * (left_signal + right_signal)

    # --- Time domain plot ---
    fig, axs = plt.subplots(2, 1, figsize=(10, 8))

    axs[0].plot(time_vector, left_signal, label="Left channel", alpha=0.8)
    axs[0].plot(time_vector, right_signal, label="Right channel", alpha=0.8)
    axs[0].plot(time_vector, combined_signal, label="Combined", linestyle="--", color="black")
    axs[0].set_title("Input Trajectory - Time Domain")
    axs[0].set_xlabel("Time [s]")
    axs[0].set_ylabel("Amplitude")
    axs[0].legend()
    axs[0].grid(True, alpha=0.3)

    # --- Frequency domain plot ---
    freqs = np.fft.rfftfreq(steps, analytics.Ts)
    fft_magnitude = np.abs(np.fft.rfft(combined_signal))
    fft_magnitude[0] = 0.0  # remove DC

    axs[1].plot(freqs, fft_magnitude, label="FFT magnitude")
    axs[1].set_title("Frequency Spectrum")
    axs[1].set_xlabel("Frequency [Hz]")
    axs[1].set_ylabel("Magnitude")
    axs[1].grid(True, alpha=0.3)

    # Highlight dominant frequencies
    for comp in analytics.dominant_frequencies:
        axs[1].axvline(comp.frequency, color="red", linestyle="--", alpha=0.7)
        axs[1].text(comp.frequency, np.max(fft_magnitude) * 0.9,
                    f"{comp.frequency:.2f} Hz\n({comp.weight:.2f})",
                    rotation=90, va="top", ha="center", color="red")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close(fig)
