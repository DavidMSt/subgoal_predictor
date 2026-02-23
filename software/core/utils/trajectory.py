import numpy as np
from scipy.interpolate import CubicSpline

import numpy as np
from scipy.interpolate import CubicSpline
import matplotlib.pyplot as plt


def resample_spline(data, dt, bc_type='natural', debug=False):
    """
    Given (t, y) samples, return a resampled, smoothly interpolated trajectory.

    Parameters
    ----------
    data : array_like, shape (N, 2)
        Array of (t, y) values. t must be sorted and unique.
    dt : float
        Desired sampling time step for the output.
    bc_type : str or 2-tuple, optional
        Boundary condition type for CubicSpline (default: 'natural').
    debug : bool, optional
        If True, plots the original points and the interpolated curve.

    Returns
    -------
    t_new : ndarray
        New uniformly sampled time vector.
    y_new : ndarray
        Corresponding interpolated y values.
    """
    data = np.asarray(data)
    t, y = data[:, 0], data[:, 1]

    # Build cubic spline interpolator
    cs = CubicSpline(t, y, bc_type=bc_type)

    # New uniform time grid
    t_new = np.arange(t[0], t[-1] + dt, dt)
    y_new = cs(t_new)

    if debug:
        plt.figure(figsize=(6, 4))
        plt.plot(t, y, 'o', label="Original points")
        plt.plot(t_new, y_new, '-', label="Spline curve")
        plt.xlabel("t")
        plt.ylabel("y")
        plt.legend()
        plt.title("Spline interpolation")
        plt.grid(True)
        plt.show()

    return t_new, y_new

if __name__ == '__main__':
    # Example data
    points = [
        (0,0),
        (0.1, 0),
        (0.3, 30),
        (0.5, 60),
        (0.6, 70),
        (1, 70),
        (1.2, 70),
        (1.3, 70),
        (1.5, 0),
        (1.6, -30),
        (1.65, -60),
        (1.7, -60),
        (2.0, -60),
        (2.05, -60),
        (2.2, -30),
        (2.3, 0),
        (2.4, 0),
    ]

    t_new, y_new = resample_spline(points, dt=0.01, bc_type='not-a-knot', debug=True)

    print(repr(np.deg2rad(y_new)))