import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np


def plot_points_3d(points):
    """
    Plots a dictionary of 3D points with names.

    Parameters:
        points (dict): A dictionary where keys are point names (str) and values are tuples or lists
                       representing (x, y, z) coordinates.

    Returns:
        None
    """
    if not points:
        raise ValueError("The points dictionary is empty.")

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Extract coordinates and names
    xs, ys, zs, labels = [], [], [], []
    for name, (x, y, z) in points.items():
        xs.append(x)
        ys.append(y)
        zs.append(z)
        labels.append(name)

    # Plot each point with a unique color and label
    for i, (x, y, z, label) in enumerate(zip(xs, ys, zs, labels)):
        color = plt.cm.tab10(i % 10)  # Cycle through 10 colors
        ax.scatter(x, y, z, color=color, label=label)
        ax.text(x, y, z, f"{label}", color=color, fontsize=9, ha='center', va='bottom')

    # Set axis labels
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')

    # Equalize axes scaling
    x_limits = [min(xs), max(xs)]
    y_limits = [min(ys), max(ys)]
    z_limits = [min(zs), max(zs)]
    limits = np.array([x_limits, y_limits, z_limits])

    center = np.mean(limits, axis=1)
    max_range = np.ptp(limits)

    for axis, center_val in zip([ax.set_xlim, ax.set_ylim, ax.set_zlim], center):
        axis([center_val - max_range / 2, center_val + max_range / 2])

    # Show legend and plot
    ax.legend()
    plt.show()


def plot_points_2d(points, lines=None):
    """
    Plots a dictionary of 2D points with names and optionally connects them with lines.

    Parameters:
        points (dict): A dictionary where keys are point names (str) and values are tuples, lists, or numpy arrays
                       representing (x, y) coordinates.
        lines (list): A list of tuples where each tuple contains two point names (str) to be connected with a line.

    Returns:
        None
    """
    if not points:
        raise ValueError("The points dictionary is empty.")

    fig, ax = plt.subplots()

    # Extract coordinates and names
    xs, ys, labels = [], [], []
    for name, (x, y) in points.items():
        xs.append(x)
        ys.append(y)
        labels.append(name)

    # Plot each point with a unique color and label
    for i, (x, y, label) in enumerate(zip(xs, ys, labels)):
        color = plt.cm.tab10(i % 10)  # Cycle through 10 colors
        ax.scatter(x, y, color=color, label=label)
        ax.text(x, y, f"{label}", color=color, fontsize=9, ha='center', va='bottom')

    # Plot lines connecting points if specified
    if lines:
        for line in lines:
            if len(line) != 2:
                raise ValueError("Each line tuple must contain exactly two point names.")
            point1, point2 = line
            if point1 not in points or point2 not in points:
                raise ValueError(f"Points {point1} and {point2} must both exist in the points dictionary.")
            x_coords = [points[point1][0], points[point2][0]]
            y_coords = [points[point1][1], points[point2][1]]
            ax.plot(x_coords, y_coords, color="gray", linestyle="--")

    # Set axis labels
    ax.set_xlabel('X')
    ax.set_ylabel('Y')

    # Equalize axes scaling
    x_limits = [min(xs), max(xs)]
    y_limits = [min(ys), max(ys)]
    limits = np.array([x_limits, y_limits])

    center = np.mean(limits, axis=1)
    max_range = np.ptp(limits)

    ax.set_xlim([center[0] - max_range / 2, center[0] + max_range / 2])
    ax.set_ylim([center[1] - max_range / 2, center[1] + max_range / 2])

    # Show legend and plot
    ax.legend()
    plt.show()
