from math import isclose
import numpy as np
from matplotlib import pyplot as plt
from scipy.signal import butter, filtfilt


def limit(value, high, low=None):
    if low is None:
        low = -high

    if value < low:
        return low
    if value > high:
        return high

    return value


def are_lists_approximately_equal(K1, K2, rel_tol=1e-6, abs_tol=1e-6):
    """
    Checks if two lists of float values are approximately equal.

    Parameters:
        K1 (list of float): First list of floating-point numbers.
        K2 (list of float): Second list of floating-point numbers.
        rel_tol (float): Relative tolerance for floating-point comparisons.
        abs_tol (float): Absolute tolerance for floating-point comparisons.

    Returns:
        bool: True if the lists are approximately equal, False otherwise.
    """
    # Check if lists have the same length
    if len(K1) != len(K2):
        return False

    # Check if all corresponding elements are approximately equal
    for a, b in zip(K1, K2):
        if not isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol):
            return False

    return True


def generate_time_vector(start, end, dt):
    """
    Generate a time vector from start to end with a given sample time interval.

    Parameters:
        start (float): The starting time.
        end (float): The ending time.
        dt (float): The time interval between consecutive samples.

    Returns:
        numpy.ndarray: Time vector from start to end (inclusive) with spacing equal to sample_time.
    """
    # Calculate the number of points needed. Adding 1 ensures the endpoint is included.
    num_points = int((end - start) / dt) + 1
    return np.linspace(start, end, num_points)


def generate_time_vector_by_length(num_samples, dt, start=0.0):
    """
    Generate a time vector given the number of samples and sample interval.

    Parameters:
        num_samples (int): Number of time samples.
        dt (float): Sampling interval.
        start (float, optional): Starting time (default = 0.0).

    Returns:
        numpy.ndarray: Time vector of length num_samples.
    """
    return start + np.arange(num_samples) * dt


def generate_random_input(t_vector, f_cutoff, sigma_I):
    """
    Generate a random input trajectory u by filtering randomly drawn values.
    The trajectory u starts at zero.

    Parameters:
        t_vector : array_like
            1D time vector starting at t[0] = 0.
        f_cutoff : float
            Cutoff frequency for the 6th order Butterworth filter.
        sigma_I : float
            Scaling (amplitude) of the signal.

    Returns:
        u : ndarray
            Random output vector corresponding to the length of t_vector.
    """
    # Ensure t_vector is a 1D array.
    t_vector = np.asarray(t_vector)
    if t_vector.ndim != 1:
        raise ValueError("Time vector must be one-dimensional (a column vector).")

    N = len(t_vector)

    # Compute sampling time and sampling frequency.
    Ts = t_vector[1] - t_vector[0]
    fs = 1.0 / Ts

    # Calculate the normalized cutoff frequency.
    # In MATLAB: Wn = 2*f_cutoff/fs, which is equivalent to f_cutoff/(fs/2) in Python.
    Wn = 2 * f_cutoff / fs

    # Design a 6th order Butterworth low-pass filter.
    b, a = butter(6, Wn, btype='low', analog=False)

    # Define a filtering function using zero-phase filtering.
    def filter_fun(u):
        return filtfilt(b, a, u)

    # Function to compute the crest factor: max(|u|) / RMS(u)
    def crest_factor(u):
        rms = np.sqrt(np.mean(u ** 2))
        return np.max(np.abs(u)) / rms if rms != 0 else np.inf

    # Generate random input sequence until the crest factor is below 3.
    current_crest = 10
    while current_crest > 3:
        # Generate random values in [-1, 1] of length 2*N.
        u = 2 * (np.random.rand(2 * N) - 0.5)
        u = filter_fun(u)
        current_crest = crest_factor(u)

    # Rescale the signal so that 2*std(u) falls within [-sigma_I, sigma_I].
    u = sigma_I * u / (2 * np.std(u))

    # Find the first index where |u| is close to zero.
    # The threshold is sigma_I * 10 / (100 * log(N/2)).
    threshold = sigma_I * 10 / (100 * np.log(N / 2))
    idx_candidates = np.where(np.abs(u) < threshold)[0]
    if len(idx_candidates) == 0 or (idx_candidates[0] + N > len(u)):
        # Fallback: if no index qualifies or there isn't enough room for a segment of length N,
        # return the first N samples.
        return u[:N]

    start_idx = idx_candidates[0]
    return u[start_idx:start_idx + N]


import numpy as np


def resample(t, x, t_new):
    """
    Resamples the data x given original time vector t to new time vector t_new using linear interpolation.

    Parameters:
    - t (np.ndarray): Original time vector (1D).
    - x (np.ndarray): Data values corresponding to t. Can be 1D or 2D (with time along axis 0).
    - t_new (np.ndarray): New time vector to resample x onto.

    Returns:
    - x_new (np.ndarray): Resampled data corresponding to t_new.
    """
    t = np.asarray(t)
    x = np.asarray(x)
    t_new = np.asarray(t_new)

    if x.ndim == 1:
        x_new = np.interp(t_new, t, x)
    else:
        x_new = np.array([np.interp(t_new, t, x[:, i]) for i in range(x.shape[1])]).T

    return x_new


# ======================================================================================================================
# ----------------------------------------------------------------------------------------------------------------------
def plot_frequency_spectrum(signal: np.ndarray, Ts: float, num_dominant: int = 5):
    steps = len(signal)
    freqs = rfftfreq(steps, Ts)
    fft_magnitude = np.abs(rfft(signal))
    fft_magnitude[0] = 0.0  # Remove DC

    # Find peaks
    peak_indices, _ = find_peaks(fft_magnitude, height=np.max(fft_magnitude) * 0.05)
    if len(peak_indices) == 0:
        print("No dominant frequencies found.")
        return

    # Sort by magnitude and get top N
    sorted_indices = peak_indices[np.argsort(fft_magnitude[peak_indices])[::-1]]
    top_indices = sorted_indices[:num_dominant]

    # Plot
    plt.figure(figsize=(10, 5))
    plt.plot(freqs, fft_magnitude, label="FFT Magnitude")
    plt.scatter(freqs[top_indices], fft_magnitude[top_indices], color='red', zorder=5, label="Dominant Frequencies")

    for idx in top_indices:
        plt.annotate(f"{freqs[idx]:.2f} Hz", (freqs[idx], fft_magnitude[idx]), textcoords="offset points",
                     xytext=(0, 10), ha='center')

    plt.xlabel("Frequency [Hz]")
    plt.ylabel("Amplitude")
    plt.title("Frequency Spectrum with Dominant Frequencies")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def clamp(value, low, high):
    return limit(value, high, low)
