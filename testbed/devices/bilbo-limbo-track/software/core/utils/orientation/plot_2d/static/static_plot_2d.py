import random

import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass


def getRandomColor() -> str:
    """
    Generates a random color in hexadecimal format.

    Returns:
    str: A string representing the random color in the format #RRGGBB.
    """
    return "#" + "".join(random.choices("0123456789ABCDEF", k=6))


def plot_2d(coordinate_systems=None, points=None, vectors=None, lines=None, limits=None):
    fig, ax = plt.subplots()

    # Plot coordinate systems
    if coordinate_systems is not None:
        for key, cs in coordinate_systems.items():
            origin = np.asarray(cs.origin)
            x_axis = np.asarray(cs.x_axis)
            y_axis = np.asarray(cs.y_axis)

            ax.quiver(origin[0], origin[1], x_axis[0], x_axis[1],
                      angles='xy', scale_units='xy', scale=1, color='red', alpha=0.7)
            ax.quiver(origin[0], origin[1], y_axis[0], y_axis[1],
                      angles='xy', scale_units='xy', scale=1, color='green', alpha=0.7)
            ax.text(origin[0], origin[1] - 0.1, key, fontsize=9, ha='center', verticalalignment='top', color='black')

    # Plot points
    if points is not None:
        for key, point in points.items():
            point = np.asarray(point)
            ax.scatter(point[0], point[1], color='green')
            ax.text(point[0], point[1] + 0.1, key, fontsize=9, ha='center', color='black')

    # Plot vectors
    if vectors is not None:
        for key, vector in vectors.items():
            if isinstance(vector, np.ndarray):
                vec = np.asarray(vector)
                origin = np.zeros(2)
            elif isinstance(vector, tuple):
                vec = np.asarray(vector[0])
                origin = np.asarray(vector[1])

            color = getRandomColor()
            ax.quiver(origin[0], origin[1], vec[0], vec[1],
                      angles='xy', scale_units='xy', scale=1, color=color, alpha=0.7)

            # Calculate the midpoint of the vector for text placement
            midpoint = origin + 0.5 * vec
            # Add a small offset perpendicular to the vector for better visibility
            perpendicular_offset = np.array([-vec[1], vec[0]])  # Rotate vector by 90 degrees
            perpendicular_offset = 0.1 * perpendicular_offset / np.linalg.norm(vec)  # Normalize and scale
            text_position = midpoint + perpendicular_offset

            # Calculate the angle of rotation in degrees
            angle = np.degrees(np.arctan2(vec[1], vec[0]))

            ax.text(text_position[0], text_position[1], key, fontsize=9, ha='center',
                    verticalalignment='center', color=color, rotation=angle)

    # Plot lines
    if lines is not None:
        for line in lines:
            obj1, obj2 = line
            if obj1 in points:
                start = np.asarray(points[obj1])
            elif obj1 in coordinate_systems:
                start = np.asarray(coordinate_systems[obj1].origin)
            elif obj1 in vectors:
                start = np.asarray(vectors[obj1].origin) if vectors[obj1].origin is not None else np.zeros(2)
            else:
                continue

            if obj2 in points:
                end = np.asarray(points[obj2])
            elif obj2 in coordinate_systems:
                end = np.asarray(coordinate_systems[obj2].origin)
            elif obj2 in vectors:
                end = np.asarray(vectors[obj2].origin) if vectors[obj2].origin is not None else np.zeros(2)
            else:
                continue

            ax.plot([start[0], end[0]], [start[1], end[1]], linestyle='dotted', color='gray')

    # Set grid, aspect, and limits
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_aspect('equal', adjustable='box')

    if limits:
        if 'x' in limits:
            ax.set_xlim(limits['x'])
        if 'y' in limits:
            ax.set_ylim(limits['y'])
    else:
        ax.autoscale()

    plt.show()
