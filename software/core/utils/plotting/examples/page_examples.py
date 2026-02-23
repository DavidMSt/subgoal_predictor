"""
Page Layout Examples

Demonstrates the page layout system for creating multi-plot PDF documents
with images, text, and nested groups.
"""

import numpy as np

from core.utils.plotting.plot import (
    Plot,
    Axis,
    AxisConfig,
)
from core.utils.plotting.page import (
    Page,
    PageConfig,
    Group,
    ImageElement,
    TextElement,
    PlotElement,
    image,
    text,
    plot,
)


def create_sample_plot(title: str, color: str = "tab:blue", transparent: bool = False) -> Plot:
    """Helper to create a simple sample plot."""
    x = np.linspace(0, 10, 200)
    y = np.sin(x * 0.5) + 0.1 * np.random.randn(len(x))

    p = Plot(
        rows=1,
        columns=1,
        size=(5, 3),
        use_agg_backend=True,
        facealpha=0 if transparent else 1,
    )
    axis_cfg = AxisConfig(
        title=title,
        xlabel="Time [s]",
        ylabel="Value",
        grid=True,
        legend=False,
        facecolor='none' if transparent else 'white',  # Transparent axis background
    )
    axis = Axis(id="main", config=axis_cfg)
    p.set_axis(1, 1, axis)
    axis.plot(x, y, color=color, linewidth=1.5)
    return p


def example_basic_grid():
    """
    Basic 2x2 grid of plots.

    This is the simplest usage pattern.
    """
    # Create sample plots
    plot1 = create_sample_plot("Sensor A", "tab:blue")
    plot2 = create_sample_plot("Sensor B", "tab:orange")
    plot3 = create_sample_plot("Sensor C", "tab:green")
    plot4 = create_sample_plot("Sensor D", "tab:red")

    # Create page with 2x2 grid
    page = Page(rows=2, cols=2, size=(11, 8.5))

    # Place plots
    page.place(plot(plot1), row=1, col=1)
    page.place(plot(plot2), row=1, col=2)
    page.place(plot(plot3), row=2, col=1)
    page.place(plot(plot4), row=2, col=2)

    # Show the result
    page.show()
    return page


def example_spanning_cells():
    """
    Plots that span multiple grid cells.

    Useful for creating layouts with a main plot and smaller subplots.
    """
    # Create plots
    main_plot = create_sample_plot("Main Result", "tab:blue")
    detail1 = create_sample_plot("Detail 1", "tab:orange")
    detail2 = create_sample_plot("Detail 2", "tab:green")

    # Create page with 2x2 grid
    page = Page(rows=2, cols=2, size=(11, 8.5))

    # Main plot spans the entire top row
    page.place(plot(main_plot), row=1, col=1, colspan=2)

    # Details in the bottom row
    page.place(plot(detail1), row=2, col=1)
    page.place(plot(detail2), row=2, col=2)

    page.show()
    return page


def example_with_text():
    """
    Combining plots with text descriptions.
    """
    # Create a plot
    p = create_sample_plot("Experiment Results", "tab:blue")

    # Create page with 3x2 grid
    page = Page(rows=3, cols=2, size=(11, 8.5), title="Experiment Report", debug=True)

    # Title text at the top
    page.place(
        text(
            "Velocity Tracking Experiment",
            fontsize=18,
            font_weight='bold',
            vertical_alignment='top',
        ),
        row=1, col=1, colspan=2
    )

    # Main plot
    page.place(plot(p), row=2, col=1, colspan=2)

    # Description text at the bottom
    page.place(
        text(
            "The plot above shows the velocity tracking performance during the "
            "experiment. The robot successfully maintained the target velocity "
            "with minimal deviation from the setpoint.",
            fontsize=10,
            alignment='left',
            vertical_alignment='top',
            background_color='lightyellow',
        ),
        row=3, col=1, colspan=2
    )

    page.show()
    return page


def example_nested_groups():
    """
    Nested groups for complex layouts.

    Shows how to create hierarchical layouts with groups inside groups,
    using outline and background styling.
    """
    # Create plots
    overview = create_sample_plot("System Overview", "tab:blue")
    detail_a1 = create_sample_plot("Motor 1", "tab:red")
    detail_a2 = create_sample_plot("Motor 2", "tab:red")
    detail_b1 = create_sample_plot("Sensor 1", "tab:green")
    detail_b2 = create_sample_plot("Sensor 2", "tab:green")

    # Create page
    page = Page(rows=2, cols=2, size=(11, 8.5))

    # Overview plot in top-left
    page.place(plot(overview), row=1, col=1)

    # Create a nested group for motor details (top-right) with styling
    motor_group = page.group(
        rows=2, cols=1,
        title="Motors",
        show_outline=True,
        outline_color='tab:red',
        outline_width=1.5,
        background_color='mistyrose',
        background_alpha=0.3,
    )
    motor_group.place(plot(detail_a1), row=1, col=1)
    motor_group.place(plot(detail_a2), row=2, col=1)
    page.place(motor_group, row=1, col=2)

    # Create a nested group for sensor details (bottom, spanning both columns)
    sensor_group = page.group(
        rows=1, cols=2,
        title="Sensors",
        show_outline=True,
        outline_color='tab:green',
        outline_width=1.5,
        outline_style='--',
        background_color='honeydew',
        background_alpha=0.3,
    )
    sensor_group.place(plot(detail_b1), row=1, col=1)
    sensor_group.place(plot(detail_b2), row=1, col=2)
    page.place(sensor_group, row=2, col=1, colspan=2)

    page.show()
    return page


def example_group_styling():
    """
    Demonstrates group styling options: outlines, backgrounds, and nested styling.
    """
    # Create some plots with transparent backgrounds so group colors show through
    p1 = create_sample_plot("Plot A", "tab:blue", transparent=True)
    p2 = create_sample_plot("Plot B", "tab:orange", transparent=True)
    p3 = create_sample_plot("Plot C", "tab:green", transparent=True)
    p4 = create_sample_plot("Plot D", "tab:red", transparent=True)

    # Create page
    page = Page(rows=2, cols=2, size=(12, 9))

    # Group with outline only
    group1 = page.group(
        rows=1, cols=1,
        title="Outlined Group",
        show_outline=True,
        outline_color='tab:blue',
        outline_width=2,
        outline_style='-',
    )
    group1.place(plot(p1), row=1, col=1)
    page.place(group1, row=1, col=1)

    # Group with background color
    group2 = page.group(
        rows=1, cols=1,
        title="Background Color",
        background_color='lightyellow',
        background_alpha=0.5,
        show_outline=True,
        outline_color='orange',
        outline_width=1.5,
    )
    group2.place(plot(p2), row=1, col=1)
    page.place(group2, row=1, col=2)

    # Group with dashed outline
    group3 = page.group(
        rows=1, cols=1,
        title="Dashed Outline",
        show_outline=True,
        outline_color='gray',
        outline_width=1.5,
        outline_style='--',
        background_color='lightgray',
        background_alpha=0.2,
    )
    group3.place(plot(p3), row=1, col=1)
    page.place(group3, row=2, col=1)

    # Nested groups with different styles
    outer_group = page.group(
        rows=2, cols=1,
        title="Nested Groups",
        show_outline=True,
        outline_color='darkgreen',
        outline_width=2,
        background_color='honeydew',
        background_alpha=0.3,
    )

    inner_group = Group(
        rows=1, cols=1,
        show_outline=True,
        outline_color='green',
        outline_style=':',
        outline_width=1,
    )
    inner_group.place(plot(p4), row=1, col=1)

    outer_group.place(inner_group, row=1, col=1)
    outer_group.place(
        text("Nested group above", fontsize=10, vertical_alignment='center'),
        row=2, col=1
    )
    page.place(outer_group, row=2, col=2)

    page.show()
    return page


def example_debug_mode():
    """
    Debug mode showing grid lines and group borders.

    Useful for designing layouts.
    """
    # Create plots
    p1 = create_sample_plot("Plot 1", "tab:blue")
    p2 = create_sample_plot("Plot 2", "tab:orange")

    # Create page with debug mode enabled
    page = Page(
        rows=2,
        cols=3,
        size=(11, 8.5),
        debug=True,  # Enable debug visualization
        title="Debug Layout"
    )

    # Place some elements
    page.place(plot(p1), row=1, col=1, colspan=2)
    page.place(plot(p2), row=1, col=3)
    page.place(
        text("Description text here", fontsize=12, background_color='white'),
        row=2, col=1, colspan=3
    )

    page.show()
    return page


def example_complex_layout():
    """
    A complex layout demonstrating multiple features.
    """
    # Create various plots
    main_plot = create_sample_plot("Main Experiment", "tab:blue")
    sub1 = create_sample_plot("Subplot 1", "tab:orange")
    sub2 = create_sample_plot("Subplot 2", "tab:green")
    sub3 = create_sample_plot("Subplot 3", "tab:red")
    sub4 = create_sample_plot("Subplot 4", "tab:purple")

    # Create page with 3x4 grid
    page = Page(rows=3, cols=4, size=(12, 9))

    # Header text
    page.place(
        text(
            "Comprehensive Experiment Analysis",
            fontsize=16,
            font_weight='bold',
        ),
        row=1, col=1, colspan=4
    )

    # Main plot takes up most of the left side
    page.place(plot(main_plot), row=2, col=1, rowspan=2, colspan=3)

    # Side panel with smaller plots
    side_group = page.group(rows=4, cols=1, title="Details", padding=0.03)
    side_group.place(plot(sub1), row=1, col=1)
    side_group.place(plot(sub2), row=2, col=1)
    side_group.place(plot(sub3), row=3, col=1)
    side_group.place(plot(sub4), row=4, col=1)
    page.place(side_group, row=2, col=4, rowspan=2)

    page.show()
    return page


def example_text_styles():
    """
    Various text styling options.
    """
    page = Page(rows=4, cols=2, size=(11, 8.5), debug=True)

    # Different text styles
    page.place(
        text("Bold Title", fontsize=20, font_weight='bold'),
        row=1, col=1
    )
    page.place(
        text("Italic Subtitle", fontsize=14, font_style='italic', color='gray'),
        row=1, col=2
    )
    page.place(
        text(
            "Left aligned text with a light blue background box.",
            fontsize=11,
            alignment='left',
            background_color='lightblue',
        ),
        row=2, col=1, colspan=2
    )
    page.place(
        text(
            "Centered text can be used for important notes or summaries.",
            fontsize=11,
            alignment='center',
            vertical_alignment='center',
        ),
        row=3, col=1, colspan=2
    )
    page.place(
        text(
            "Right aligned works well for figure captions and attributions.",
            fontsize=9,
            alignment='right',
            color='darkgray',
        ),
        row=4, col=1, colspan=2
    )

    page.show()
    return page


if __name__ == "__main__":
    # Run one of the examples
    # example_basic_grid()
    # example_spanning_cells()
    # example_with_text()
    # example_nested_groups()
    # example_debug_mode()
    # example_complex_layout()
    # example_text_styles()
    example_group_styling()
