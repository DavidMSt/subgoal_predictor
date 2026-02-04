"""
Map Plot Examples

Demonstrates the MapPlot class for creating 2D map visualizations with
points, lines, trajectories, and various decorations.
"""

import numpy as np

from core.utils.plotting.map_plot import (
    MapPlot,
    MapConfig,
    TilesConfig,
    GridConfig,
    CoordinateSystemConfig,
    PointConfig,
    LineConfig,
    TrajectoryConfig,
    RectangleConfig,
    CircleConfig,
    LabelConfig,
)


def example_basic_map():
    """
    Basic map with grid and coordinate system.

    Shows the simplest usage: a 3x3 meter map centered at origin
    with grid lines and a coordinate system indicator.
    """
    map_plot = MapPlot(size=(3, 3))
    map_plot.add_grid(
        major=1.0,
        minor=0.25,
    )
    map_plot.add_coordinate_system()
    map_plot.show()
    return map_plot


def example_tiles_and_grid():
    """
    Map with checkerboard tiles and overlaid grid.

    Demonstrates the tile background pattern commonly used
    for robotics visualization.
    """
    map_plot = MapPlot(size=(4, 4), title="Tiled Map")

    # Add checkerboard tiles
    map_plot.add_tiles(
        size=0.5,
        color_1='#f0f0f0',
        color_2='white',
    )

    # Add grid with custom styling
    map_plot.add_grid(
        major=1.0,
        minor=0.25,
        major_color='black',
        major_opacity=0.5,
        minor_color='gray',
        minor_opacity=0.2,
    )

    map_plot.add_coordinate_system(length=0.4)
    map_plot.show()
    return map_plot


def example_points_and_labels():
    """
    Map with labeled points at various positions.

    Shows how to add points with different markers, colors,
    and label positions.
    """
    map_plot = MapPlot(size=(3, 3))
    map_plot.add_grid(major=1.0, minor=None)
    map_plot.add_coordinate_system(length=0.3)

    # Add various labeled points
    map_plot.add_point(position=(0.5, 0.5), color='red', label='Robot 1', label_position='top')
    map_plot.add_point(position=(-0.5, 0.8), color='blue', label='Robot 2', label_position='right')
    map_plot.add_point(position=(0.2, -0.6), color='green', label='Target', marker='*', size=0.08)
    map_plot.add_point(position=(-0.8, -0.8), color='orange', label='Obstacle',
                       marker='s', border=True, border_color='black')

    map_plot.show()
    return map_plot


def example_lines():
    """
    Map with multiple lines forming a path.
    """
    map_plot = MapPlot(size=(3, 3))
    map_plot.add_grid()
    map_plot.add_coordinate_system(length=0.3)

    # Add a path
    path_positions = [(-1, -1), (-0.5, 0), (0, 0.5), (0.5, 0.3), (1, 1)]
    map_plot.add_line(positions=path_positions, color='blue', width=2, label='Path A')

    # Add another dashed line
    path2 = [(-1, 0.5), (0, 0), (1, -0.5)]
    map_plot.add_line(positions=path2, color='red', width=1.5, style='--', label='Path B')

    map_plot.show()
    return map_plot


def example_trajectory_simple():
    """
    Simple robot trajectory without gradient.
    """
    # Generate a circular trajectory
    t = np.linspace(0, 2 * np.pi, 100)
    x = 0.8 * np.cos(t)
    y = 0.8 * np.sin(t)

    map_plot = MapPlot(size=(3, 3))
    map_plot.add_grid()
    map_plot.add_coordinate_system(length=0.3)

    map_plot.add_trajectory(x, y,
                            color='blue',
                            width=2,
                            show_start=True,
                            show_end=True,
                            start_color='green',
                            end_color='red')

    map_plot.show()
    return map_plot


def example_trajectory_gradient():
    """
    Robot trajectory with time-based color gradient.

    The color changes from start to end, making it easy
    to visualize the direction and progression of motion.
    """
    # Generate a spiral trajectory
    t = np.linspace(0, 4 * np.pi, 200)
    r = 0.1 + 0.2 * t / (4 * np.pi)
    x = r * np.cos(t)
    y = r * np.sin(t)

    map_plot = MapPlot(size=(2, 2), title="Spiral Trajectory")
    map_plot.add_tiles(size=0.25, color_1='#fafafa', color_2='white')
    map_plot.add_grid(major=0.5, minor=None, major_opacity=0.3)
    map_plot.add_coordinate_system(length=0.2)

    # Trajectory with gradient using viridis colormap
    map_plot.add_trajectory(x, y,
                            gradient=True,
                            gradient_cmap='viridis',
                            width=3,
                            show_start=True,
                            show_end=True)

    map_plot.show()
    return map_plot


def example_trajectory_custom_gradient():
    """
    Trajectory with custom start/end colors.
    """
    # Generate figure-8 trajectory
    t = np.linspace(0, 2 * np.pi, 150)
    x = 0.8 * np.sin(t)
    y = 0.5 * np.sin(2 * t)

    map_plot = MapPlot(size=(3, 2))
    map_plot.add_grid(major=0.5, minor=None)
    map_plot.add_coordinate_system(length=0.25)

    map_plot.add_trajectory(x, y,
                            gradient=True,
                            gradient_start_color='blue',
                            gradient_end_color='red',
                            width=3,
                            show_start=True,
                            show_end=True,
                            start_marker='o',
                            end_marker='^')

    map_plot.show()
    return map_plot


def example_multiple_trajectories():
    """
    Multiple robot trajectories on the same map.
    """
    map_plot = MapPlot(size=(4, 4), title="Multi-Robot Trajectories")
    map_plot.add_tiles(size=0.5)
    map_plot.add_grid(major=1.0, minor=None)
    map_plot.add_coordinate_system(length=0.4)

    # Robot 1: circular path
    t1 = np.linspace(0, 1.5 * np.pi, 80)
    x1 = 1.0 * np.cos(t1) - 0.5
    y1 = 1.0 * np.sin(t1)
    map_plot.add_trajectory(x1, y1, color='blue', width=2,
                            show_start=True, show_end=True, label='Robot 1')

    # Robot 2: straight line with deviation
    t2 = np.linspace(0, 1, 50)
    x2 = -1.5 + 3 * t2
    y2 = -1 + 0.3 * np.sin(4 * np.pi * t2)
    map_plot.add_trajectory(x2, y2, gradient=True,
                            gradient_start_color='green',
                            gradient_end_color='orange',
                            width=2, show_start=True, show_end=True, label='Robot 2')

    # Robot 3: random walk
    np.random.seed(42)
    n_steps = 60
    x3 = np.cumsum(0.05 * np.random.randn(n_steps)) + 0.5
    y3 = np.cumsum(0.05 * np.random.randn(n_steps)) - 0.5
    map_plot.add_trajectory(x3, y3, color='purple', width=1.5,
                            show_start=True, show_end=True, label='Robot 3')

    map_plot.show()
    return map_plot


def example_shapes():
    """
    Map with rectangles and circles representing obstacles and zones.
    """
    map_plot = MapPlot(size=(4, 4), title="Environment with Obstacles")
    map_plot.add_grid(major=1.0, minor=0.5)
    map_plot.add_coordinate_system(length=0.3)

    # Add rectangular obstacles
    map_plot.add_rectangle(position=(-1.5, -1.5), width=0.8, height=0.5,
                           color='gray', opacity=0.7, border_color='black')
    map_plot.add_rectangle(position=(0.5, 0.8), width=0.6, height=0.4,
                           color='gray', opacity=0.7, border_color='black')

    # Add circular obstacle
    map_plot.add_circle(position=(1.0, -0.5), radius=0.3,
                        color='darkgray', opacity=0.8)

    # Add goal zone (green circle)
    map_plot.add_circle(position=(-0.8, 1.2), radius=0.25,
                        color='lightgreen', opacity=0.5,
                        border_color='green', border_width=2)

    # Add robot position
    map_plot.add_point(position=(0, 0), color='blue', size=0.08, label='Robot')

    # Add planned path avoiding obstacles
    path = [(0, 0), (-0.3, 0.4), (-0.5, 0.8), (-0.8, 1.2)]
    map_plot.add_line(positions=path, color='blue', width=1.5, style='--')

    map_plot.show()
    return map_plot


def example_asymmetric_bounds():
    """
    Map with asymmetric bounds (not centered at origin).

    Useful for testbed configurations where the origin
    is not at the center of the workspace.
    """
    # Define map from -1 to 5 in x, and -2 to 3 in y
    map_plot = MapPlot(size=((-1, 5), (-2, 3)), title="Asymmetric Workspace")
    map_plot.add_tiles(size=0.5)
    map_plot.add_grid(major=1.0, minor=None)
    map_plot.add_coordinate_system(length=0.5, position=(0, 0))

    # Add some points
    map_plot.add_point(position=(0, 0), color='black', label='Origin', size=0.1)
    map_plot.add_point(position=(4, 2), color='red', label='Target')
    map_plot.add_point(position=(2, -1), color='blue', label='Waypoint')

    map_plot.show()
    return map_plot


def example_labels():
    """
    Demonstrates various label styles, placements, and formatting options.
    """
    map_plot = MapPlot(size=(4, 4), title="Label Examples", padding=0.3,
                       mathtext_fontset='stix', font_family='STIXGeneral')
    map_plot.add_grid(major=1.0, minor=0.5, major_opacity=0.3, minor_opacity=0.15)
    map_plot.add_coordinate_system(length=0.3)

    # Basic centered label
    map_plot.add_label('Centered', position=(0, 0), fontsize=12)

    # Corner-anchored labels with padding
    map_plot.add_label('Top-Left', position=(-2, 2),
                       horizontal_anchor='left', vertical_anchor='top',
                       padding_x=0.05, padding_y=0.05,
                       background=True)

    map_plot.add_label('Top-Right', position=(2, 2),
                       horizontal_anchor='right', vertical_anchor='top',
                       padding_x=0.05, padding_y=0.05,
                       background=True)

    map_plot.add_label('Bottom-Left', position=(-2, -2),
                       horizontal_anchor='left', vertical_anchor='bottom',
                       padding_x=0.05, padding_y=0.05,
                       background=True)

    map_plot.add_label('Bottom-Right', position=(1, -1),
                       horizontal_anchor='right', vertical_anchor='bottom',
                       padding_x=0.05, padding_y=0.05,
                       background=True)

    # Styled labels
    map_plot.add_label('Bold', position=(-1.5, 1),
                       font_weight='bold', fontsize=11)

    map_plot.add_label('Italic', position=(-1.5, 0.5),
                       font_style='italic', fontsize=11)

    map_plot.add_label('Colored', position=(-1.5, 0),
                       color='red', fontsize=11)

    # Rotated labels
    map_plot.add_label('Rotated 45°', position=(1, 0.5),
                       rotation=45, fontsize=10, background=True)

    map_plot.add_label('Rotated -30°', position=(1, -0.5),
                       rotation=-30, fontsize=10, background=True)

    # Background styles
    map_plot.add_label('Custom BG', position=(0, 1.2),
                       background=True,
                       background_color='lightyellow',
                       background_edge_color='orange',
                       background_edge_width=1.5)

    map_plot.add_label('Blue BG', position=(0, -1.2),
                       background=True,
                       background_color='lightblue',
                       background_opacity=0.9,
                       background_edge_color='blue')

    # Math label using matplotlib's mathtext
    map_plot.add_label(r'$\theta = \frac{\pi}{4}$', position=(1.5, 1.2),
                       fontsize=12, background=True)

    map_plot.add_label(r'$v = \sqrt{x^2 + y^2}$', position=(1.5, -1.2),
                       fontsize=11, background=True)

    map_plot.show()
    return map_plot


def example_latex():
    """
    Demonstrates real LaTeX rendering using usetex=True.

    Requires a working LaTeX installation (e.g., MiKTeX, TeX Live).
    """
    map_plot = MapPlot(size=(4, 4), title="LaTeX Rendering", padding=0.3)
    map_plot.add_grid(major=1.0, minor=None, major_opacity=0.2)
    map_plot.add_coordinate_system(length=0.3)

    # Basic Greek letters
    map_plot.add_label(r'$\alpha, \beta, \gamma, \delta$', position=(0, 1.5),
                       usetex=True, fontsize=14)

    # Fractions and integrals
    map_plot.add_label(r'$\int_0^1 x^2 \, dx = \frac{1}{3}$', position=(0, 0.8),
                       usetex=True, fontsize=14, background=True)

    # Summation
    map_plot.add_label(r'$\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$', position=(0, 0),
                       usetex=True, fontsize=14, background=True)

    # Square roots and exponents
    map_plot.add_label(r'$\sqrt{x^2 + y^2} = r$', position=(0, -0.8),
                       usetex=True, fontsize=14, background=True)

    # Matrices (using array)
    map_plot.add_label(
        r'$\mathbf{R} = \left[\begin{array}{cc} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{array}\right]$',
        position=(0, -1.6),
        usetex=True, fontsize=11, background=True
    )

    # Mixed text and math
    map_plot.add_label(r'Position: $(x, y) = (1.5, 2.0)$', position=(-1.8, 1.5),
                       usetex=True, fontsize=10, horizontal_anchor='left',
                       background=True)

    map_plot.add_label(r'Velocity: $v = 0.5 \, \mathrm{m/s}$', position=(-1.8, -1.5),
                       usetex=True, fontsize=10, horizontal_anchor='left',
                       background=True)

    map_plot.show_pdf()
    return map_plot


def example_complete():
    """
    Complete example combining multiple features.
    """
    map_plot = MapPlot(
        size=(5, 4),
        title="Complete Map Example",
        padding=0.2,
        background_color='#fefefe'
    )

    # Background
    map_plot.add_tiles(size=0.5, color_1='#f5f5f5', color_2='white')
    map_plot.add_grid(major=1.0, minor=0.25, major_opacity=0.4, minor_opacity=0.15)
    map_plot.add_coordinate_system(length=0.4)

    # Obstacles
    map_plot.add_rectangle(position=(-2, -1.5), width=1, height=0.6,
                           color='gray', opacity=0.6)
    map_plot.add_circle(position=(1.5, 1), radius=0.4,
                        color='gray', opacity=0.6)

    # Goal zone
    map_plot.add_circle(position=(2, -1), radius=0.3,
                        color='lightgreen', opacity=0.4,
                        border_color='green', border_width=2)

    # Trajectory with gradient
    t = np.linspace(0, 2 * np.pi, 100)
    x = -1.5 + 1.5 * t / (2 * np.pi) + 0.3 * np.sin(3 * t)
    y = 0.5 * np.cos(2 * t) + 0.5 * t / (2 * np.pi)
    map_plot.add_trajectory(x, y,
                            gradient=True,
                            gradient_cmap='plasma',
                            width=2.5,
                            show_start=True,
                            show_end=True)

    # Key positions
    map_plot.add_point(position=(-1.5, 0), color='green', size=0.06,
                       label='Start', label_position='left', label_background=True)
    map_plot.add_point(position=(2, -1), color='red', size=0.06,
                       label='Goal', label_position='right', label_background=True)

    map_plot.show_pdf()
    return map_plot


if __name__ == "__main__":
    # Run one of the examples
    # example_basic_map()
    # example_tiles_and_grid()
    # example_points_and_labels()
    # example_lines()
    # example_trajectory_simple()
    # example_trajectory_gradient()
    # example_trajectory_custom_gradient()
    # example_multiple_trajectories()
    # example_shapes()
    # example_asymmetric_bounds()
    # example_labels()
    example_latex()
    # example_complete()
