"""
Example: Plot Annotations with Vertical Lines and Phase Bars

Demonstrates how to create a plot with time series data and add:
- Vertical lines with optional labels to mark specific events or times
- Phase bars to indicate different modes/phases in the data
"""

import numpy as np

from core.utils.plotting.plot import (
    Plot,
    Axis,
    AxisConfig,
    LineConfig,
    LabelConfig,
    PhaseBarConfig,
    PhaseConfig,
    PhaseBackgroundConfig,
    BackgroundPhaseConfig,
)


def example_vertical_lines():
    """
    Create a plot with time series data and annotate it with vertical lines.

    This example shows:
    - Creating a basic plot with time series
    - Adding vertical lines at specific x positions
    - Adding labels above or below the vertical lines
    - Customizing line and label appearance
    """
    # Generate sample time series data
    t = np.linspace(0, 10, 500)
    signal_1 = np.sin(2 * np.pi * 0.5 * t) + 0.1 * np.random.randn(len(t))
    signal_2 = 0.5 * np.cos(2 * np.pi * 0.3 * t) + 0.5

    # Create the plot
    plot = Plot(
        rows=1,
        columns=1,
        size=(10, 5),
        use_agg_backend=False,
    )

    # Configure the axis
    axis_cfg = AxisConfig(
        title="Time Series with Event Markers",
        xlabel="Time [s]",
        ylabel="Amplitude",
        legend=True,
        grid=True,
        ylim=(-2, 2.5),
    )
    axis = Axis(id="main", config=axis_cfg)
    plot.set_axis(1, 1, axis)

    # Plot the time series
    axis.plot(t, signal_1, label="Signal 1", color="tab:blue")
    axis.plot(t, signal_2, label="Signal 2", color="tab:orange")

    # --- Add vertical lines to mark events ---

    # Simple vertical line (no label)
    axis.add_vertical_line(
        x=1.0,
        color="gray",
        linewidth=1,
        style=":",
        alpha=0.7,
    )

    # Vertical line with label above (default position)
    axis.add_vertical_line(
        x=3.0,
        label="Start",
        color="green",
        linewidth=1.5,
        style="--",
    )

    # Vertical line with label below
    axis.add_vertical_line(
        x=5.0,
        label="Midpoint",
        label_position="below",
        color="red",
        linewidth=1.5,
        style="--",
    )

    # Vertical line with custom LineConfig
    line_cfg = LineConfig(
        color="purple",
        linewidth=2,
        style="-",
        alpha=0.8,
    )
    axis.add_vertical_line(
        x=7.5,
        config=line_cfg,
        label="Event A",
        label_position="above",
    )

    # Vertical line with label_config as dict (quick overrides)
    axis.add_vertical_line(
        x=8.5,
        label="Dict Style",
        label_position="below",
        label_config={'fontsize': 10, 'background_color': 'lightyellow'},
        color="orange",
        linewidth=1.5,
        style="--",
    )

    # Vertical line with full LabelConfig for complete control
    custom_label_cfg = LabelConfig(
        color="white",
        fontsize=9,
        background_box=True,
        background_color="darkblue",
        background_alpha=0.9,
        box_padding=0.3,
    )
    axis.add_vertical_line(
        x=9.5,
        label="End",
        label_position="above",
        label_config=custom_label_cfg,
        color="darkblue",
        linewidth=2,
        style="-",
    )

    # Show the plot
    plot.show_temp_pdf()

    return plot


def example_phase_bars():
    """
    Create a plot with phase bars to indicate different operating modes.

    This example shows:
    - Configuring phase bars at different positions (top, bottom inside, bottom outside)
    - Adding phases with different colors and layers
    - Concurrent phases using layer stacking
    - Customizing phase appearance
    - Rounded corners and auto-darkened borders
    """
    # Generate sample data simulating a robot going through different modes
    t = np.linspace(0, 20, 1000)
    velocity = np.zeros_like(t)
    velocity[(t >= 2) & (t < 5)] = np.linspace(0, 1, np.sum((t >= 2) & (t < 5)))
    velocity[(t >= 5) & (t < 15)] = 1.0 + 0.1 * np.sin(2 * np.pi * 0.5 * t[(t >= 5) & (t < 15)])
    velocity[(t >= 15) & (t < 18)] = np.linspace(1, 0, np.sum((t >= 15) & (t < 18)))
    velocity += 0.05 * np.random.randn(len(t))

    # --- Example 1: Bottom inside phase bar ---
    plot1 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis1_cfg = AxisConfig(
        title="Phase Bar - Bottom Inside (with rounded corners and auto borders)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
        ylim=(-0.3, 1.5),
    )
    axis1 = Axis(id="main1", config=axis1_cfg)
    plot1.set_axis(1, 1, axis1)
    axis1.plot(t, velocity, color="tab:blue", linewidth=1.5)

    # Configure phase bar with rounded corners
    axis1.configure_phase_bar(
        position="bottom_inside",
        height=0.07,
        fontsize=8,
        corner_radius=0.012,  # Rounded corners
        horizontal_padding=0.003,  # Gap between phases
    )

    # Add phases - borders are auto-darkened by default
    axis1.add_phase("Idle", start=0, end=2, color="gray")
    axis1.add_phase("Accelerating", start=2, end=5, color="tab:orange")
    axis1.add_phase("Running", start=5, end=15, color="tab:green")
    axis1.add_phase("Decelerating", start=15, end=18, color="tab:orange")
    axis1.add_phase("Idle", start=18, end=20, color="gray")

    plot1.show_temp_pdf()

    # --- Example 2: Top inside phase bar ---
    plot2 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis2_cfg = AxisConfig(
        title="Phase Bar - Top Inside",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis2 = Axis(id="main2", config=axis2_cfg)
    plot2.set_axis(1, 1, axis2)
    axis2.plot(t, velocity, color="tab:blue", linewidth=1.5)

    axis2.configure_phase_bar(position="top_inside", height=0.06, fontsize=7)
    axis2.add_phase("Idle", start=0, end=2, color="lightgray", alpha=0.7)
    axis2.add_phase("Accel", start=2, end=5, color="tab:orange")
    axis2.add_phase("Running", start=5, end=15, color="tab:green")
    axis2.add_phase("Decel", start=15, end=18, color="tab:orange")
    axis2.add_phase("Stop", start=18, end=20, color="lightgray", alpha=0.7)

    plot2.show_temp_pdf()

    # --- Example 3: Bottom outside phase bar ---
    plot3 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis3_cfg = AxisConfig(
        title="Phase Bar - Bottom Outside (below tick labels)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis3 = Axis(id="main3", config=axis3_cfg)
    plot3.set_axis(1, 1, axis3)
    axis3.plot(t, velocity, color="tab:blue", linewidth=1.5)

    # Adjust outside_offset to position below xlabel
    axis3.configure_phase_bar(
        position="bottom_outside",
        height=0.06,
        fontsize=8,
        outside_offset=0.28,  # Adjust based on your tick/label sizes
    )
    axis3.add_phase("Init", start=0, end=2, color="tab:gray")
    axis3.add_phase("Ramp Up", start=2, end=5, color="tab:orange")
    axis3.add_phase("Steady State", start=5, end=15, color="tab:green")
    axis3.add_phase("Ramp Down", start=15, end=18, color="tab:red")
    axis3.add_phase("Done", start=18, end=20, color="tab:gray")

    plot3.show_temp_pdf()

    # --- Example 4: Multiple layers (concurrent phases) ---
    plot4 = Plot(rows=1, columns=1, size=(12, 5), use_agg_backend=False)
    axis4_cfg = AxisConfig(
        title="Phase Bar - Multiple Layers (Concurrent Phases)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
        ylim=(-0.3, 1.5),
    )
    axis4 = Axis(id="main4", config=axis4_cfg)
    plot4.set_axis(1, 1, axis4)
    axis4.plot(t, velocity, color="tab:blue", linewidth=1.5)

    axis4.configure_phase_bar(
        position="bottom_inside",
        height=0.05,
        fontsize=7,
        layer_gap=0.01,
        bottom_padding=0.03,
    )

    # Layer 0: Control mode
    axis4.add_phase("OFF", start=0, end=2, color="gray", layer=0)
    axis4.add_phase("VELOCITY", start=2, end=18, color="tab:blue", layer=0)
    axis4.add_phase("OFF", start=18, end=20, color="gray", layer=0)

    # Layer 1: High-level state (concurrent with control mode)
    axis4.add_phase("Idle", start=0, end=2, color="lightgray", layer=1, alpha=0.7)
    axis4.add_phase("Moving", start=2, end=18, color="tab:green", layer=1, alpha=0.7)
    axis4.add_phase("Idle", start=18, end=20, color="lightgray", layer=1, alpha=0.7)

    plot4.show_temp_pdf()

    # --- Example 5: Custom styling with explicit borders ---
    plot5 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis5_cfg = AxisConfig(
        title="Phase Bar - Custom Styling (explicit edge colors)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis5 = Axis(id="main5", config=axis5_cfg)
    plot5.set_axis(1, 1, axis5)
    axis5.plot(t, velocity, color="tab:blue", linewidth=1.5)

    axis5.configure_phase_bar(
        position="top_inside",
        height=0.08,
        fontsize=9,
        global_alpha=0.9,
        corner_radius=0.015,
    )

    # Custom phase config with explicit edge colors
    axis5.add_phase(
        "Startup",
        start=0,
        end=5,
        config=PhaseConfig(
            color="darkblue",
            alpha=0.8,
            edge_color="black",
            edge_width=1.5,
            text_color="white",
        ),
    )
    axis5.add_phase(
        "Operation",
        start=5,
        end=15,
        config={'color': 'darkgreen', 'edge_color': 'black', 'edge_width': 1.5},
    )
    axis5.add_phase(
        "Shutdown",
        start=15,
        end=20,
        color="darkred",
        edge_color="black",
        edge_width=1.5,
        text_color="white",
    )

    plot5.show_temp_pdf()

    return plot1, plot2, plot3, plot4, plot5


def example_phase_backgrounds():
    """
    Create plots with colored background regions to indicate different phases.

    This example shows:
    - Coloring the plot background for different time periods
    - Adding labels at top or bottom with rounded background boxes
    - Showing/hiding divider lines between phases
    - Customizing colors and opacity
    """
    # Generate sample data
    t = np.linspace(0, 20, 1000)
    velocity = np.zeros_like(t)
    velocity[(t >= 2) & (t < 5)] = np.linspace(0, 1, np.sum((t >= 2) & (t < 5)))
    velocity[(t >= 5) & (t < 15)] = 1.0 + 0.1 * np.sin(2 * np.pi * 0.5 * t[(t >= 5) & (t < 15)])
    velocity[(t >= 15) & (t < 18)] = np.linspace(1, 0, np.sum((t >= 15) & (t < 18)))
    velocity += 0.05 * np.random.randn(len(t))

    # --- Example 1: Basic phase backgrounds with labels at top (default styling) ---
    plot1 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis1_cfg = AxisConfig(
        title="Phase Backgrounds - Default (labels with white background box)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis1 = Axis(id="main1", config=axis1_cfg)
    plot1.set_axis(1, 1, axis1)
    axis1.plot(t, velocity, color="black", linewidth=1.5)

    # Configure phase backgrounds (defaults: label_box=True, darkened labels)
    axis1.configure_phase_background(
        alpha=0.2,
        label_position="top",
        show_dividers=True,
        fontsize=9,
    )

    # Add background phases
    axis1.add_background_phase("Idle", start=0, end=2, color="tab:gray")
    axis1.add_background_phase("Accelerating", start=2, end=5, color="tab:orange")
    axis1.add_background_phase("Running", start=5, end=15, color="tab:green")
    axis1.add_background_phase("Decelerating", start=15, end=18, color="tab:red")
    axis1.add_background_phase("Stopped", start=18, end=20, color="tab:gray")

    plot1.show_temp_pdf()

    # --- Example 2: Labels at bottom, no box ---
    plot2 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis2_cfg = AxisConfig(
        title="Phase Backgrounds - Labels at Bottom, No Box",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis2 = Axis(id="main2", config=axis2_cfg)
    plot2.set_axis(1, 1, axis2)
    axis2.plot(t, velocity, color="black", linewidth=1.5)

    axis2.configure_phase_background(
        alpha=0.15,
        label_position="bottom",
        show_dividers=False,
        fontsize=8,
        label_offset=0.03,
        label_box=False,  # No background box
        label_color_darken=0.5,  # Make labels even darker
    )

    axis2.add_background_phase("Init", start=0, end=2, color="tab:blue")
    axis2.add_background_phase("Ramp", start=2, end=5, color="tab:orange")
    axis2.add_background_phase("Steady", start=5, end=15, color="tab:green")
    axis2.add_background_phase("Ramp Down", start=15, end=18, color="tab:orange")
    axis2.add_background_phase("Done", start=18, end=20, color="tab:blue")

    plot2.show_temp_pdf()

    # --- Example 3: Custom label box styling ---
    plot3 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis3_cfg = AxisConfig(
        title="Phase Backgrounds - Custom Label Box Styling",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis3 = Axis(id="main3", config=axis3_cfg)
    plot3.set_axis(1, 1, axis3)
    axis3.plot(t, velocity, color="black", linewidth=1.5)

    axis3.configure_phase_background(
        alpha=0.25,
        label_position="top",
        show_dividers=True,
        divider_color="black",
        divider_width=1.0,
        divider_style="-",
        divider_alpha=0.8,
        fontsize=10,
        # Custom label box
        label_box=True,
        label_box_color="white",
        label_box_alpha=0.9,
        label_box_edgecolor="gray",
        label_box_edgewidth=0.5,
        label_box_padding=0.4,
    )

    axis3.add_background_phase("Phase A", start=0, end=5, color="tab:blue")
    axis3.add_background_phase("Phase B", start=5, end=12, color="tab:purple")
    axis3.add_background_phase("Phase C", start=12, end=20, color="tab:cyan")

    plot3.show_temp_pdf()

    # --- Example 4: No labels, just colored backgrounds ---
    plot4 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis4_cfg = AxisConfig(
        title="Phase Backgrounds - No Labels (visual regions only)",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis4 = Axis(id="main4", config=axis4_cfg)
    plot4.set_axis(1, 1, axis4)
    axis4.plot(t, velocity, color="black", linewidth=1.5)

    axis4.configure_phase_background(
        alpha=0.12,
        show_labels=False,
        show_dividers=True,
        divider_style=":",
        divider_alpha=0.3,
    )

    axis4.add_background_phase("p1", start=0, end=5, color="red")
    axis4.add_background_phase("p2", start=5, end=10, color="green")
    axis4.add_background_phase("p3", start=10, end=15, color="blue")
    axis4.add_background_phase("p4", start=15, end=20, color="orange")

    plot4.show_temp_pdf()

    # --- Example 5: Per-phase alpha with emphasized regions ---
    plot5 = Plot(rows=1, columns=1, size=(12, 4), use_agg_backend=False)
    axis5_cfg = AxisConfig(
        title="Phase Backgrounds - Emphasized Critical Regions",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        legend=False,
        grid=True,
    )
    axis5 = Axis(id="main5", config=axis5_cfg)
    plot5.set_axis(1, 1, axis5)
    axis5.plot(t, velocity, color="black", linewidth=1.5)

    axis5.configure_phase_background(
        alpha=0.1,  # Default alpha
        label_position="top",
        show_dividers=True,
    )

    # Different alpha values per phase to emphasize certain regions
    axis5.add_background_phase("Setup", start=0, end=2, color="gray", alpha=0.1)
    axis5.add_background_phase("Critical!", start=2, end=5, color="red", alpha=0.3)
    axis5.add_background_phase("Normal", start=5, end=15, color="green", alpha=0.1)
    axis5.add_background_phase("Warning!", start=15, end=18, color="orange", alpha=0.25)
    axis5.add_background_phase("Done", start=18, end=20, color="gray", alpha=0.1)

    plot5.show_temp_pdf()

    return plot1, plot2, plot3, plot4, plot5


if __name__ == "__main__":
    # example_vertical_lines()
    # example_phase_bars()
    example_phase_backgrounds()
