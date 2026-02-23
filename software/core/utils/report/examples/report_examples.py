"""
Report Generation Examples

Demonstrates the HTML report generation system with Jinja2 templating.
"""

import numpy as np
from pathlib import Path

from core.utils.plotting.plot import Plot, Axis, AxisConfig
from core.utils.report import Report, render_report


# === HELPER FUNCTIONS =================================================================================================
def create_velocity_plot() -> Plot:
    """Create a sample velocity tracking plot."""
    t = np.linspace(0, 10, 500)
    target = np.ones_like(t) * 0.5
    target[t < 1] = 0
    target[t > 8] = 0
    actual = target + 0.05 * np.sin(5 * t) + 0.02 * np.random.randn(len(t))
    actual = np.convolve(actual, np.ones(10)/10, mode='same')  # Smooth

    p = Plot(rows=1, columns=1, size=(8, 4), use_agg_backend=True)
    axis = Axis(id="main", config=AxisConfig(
        title="Velocity Tracking",
        xlabel="Time [s]",
        ylabel="Velocity [m/s]",
        grid=True,
        legend=True,
    ))
    p.set_axis(1, 1, axis)
    axis.plot(t, target, label="Target", color="tab:blue", linestyle="--", linewidth=2)
    axis.plot(t, actual, label="Actual", color="tab:orange", linewidth=1.5)
    return p


def create_position_plot() -> Plot:
    """Create a sample position plot."""
    t = np.linspace(0, 10, 500)
    x = np.cumsum(0.5 * np.ones_like(t) * 0.02) + 0.01 * np.cumsum(np.random.randn(len(t)))
    y = 0.5 * np.sin(0.5 * t) + 0.02 * np.cumsum(np.random.randn(len(t)))

    p = Plot(rows=1, columns=1, size=(6, 4), use_agg_backend=True)
    axis = Axis(id="main", config=AxisConfig(
        title="Position Trajectory",
        xlabel="X [m]",
        ylabel="Y [m]",
        grid=True,
    ))
    p.set_axis(1, 1, axis)
    axis.plot(x, y, color="tab:green", linewidth=1.5)
    return p


def create_error_plot() -> Plot:
    """Create an error distribution plot."""
    t = np.linspace(0, 10, 500)
    error = 0.02 * np.sin(3 * t) + 0.01 * np.random.randn(len(t))

    p = Plot(rows=1, columns=1, size=(6, 4), use_agg_backend=True)
    axis = Axis(id="main", config=AxisConfig(
        title="Tracking Error",
        xlabel="Time [s]",
        ylabel="Error [m/s]",
        grid=True,
    ))
    p.set_axis(1, 1, axis)
    axis.plot(t, error, color="tab:red", linewidth=1)
    # Add zero line
    axis.plot(t, np.zeros_like(t), color="black", linestyle="--", linewidth=0.5, alpha=0.5)
    return p


def create_motor_plot(motor_id: int) -> Plot:
    """Create a motor current plot."""
    t = np.linspace(0, 10, 500)
    current = 0.3 * np.sin(2 * t + motor_id) + 0.1 * np.random.randn(len(t))

    p = Plot(rows=1, columns=1, size=(5, 3), use_agg_backend=True)
    axis = Axis(id="main", config=AxisConfig(
        title=f"Motor {motor_id} Current",
        xlabel="Time [s]",
        ylabel="Current [A]",
        grid=True,
    ))
    p.set_axis(1, 1, axis)
    axis.plot(t, current, color=f"tab:{'blue' if motor_id == 1 else 'orange'}", linewidth=1)
    return p


# === EXAMPLE 1: Basic Report ==========================================================================================
def example_basic_report():
    """
    Basic report with a single plot and some text.
    """
    # Create plot
    velocity_plot = create_velocity_plot()

    # Get template path
    template_path = Path(__file__).parent / "report_template.html"

    # Create and render report
    report = Report(template_path)
    report.render(
        title="Velocity Tracking Experiment",
        author="BilboLab",
        introduction="This report presents the results of a velocity tracking experiment "
                     "performed with the BILBO robot.",
        main_plot=velocity_plot,
        main_plot_caption="Figure 1: Velocity tracking performance over 10 seconds.",
        conclusion="The robot successfully tracked the target velocity with minimal error.",
        status="success",
        status_message="Experiment completed successfully",
    )

    # Show in browser (or save)
    # report.show_html()
    report.show_pdf()
    # report.save_pdf("basic_report.pdf")
    # report.save_html("basic_report.html")


# === EXAMPLE 2: Full Report with Multiple Plots =======================================================================
def example_full_report():
    """
    Comprehensive report with multiple plots, tables, and metrics.
    """
    # Create plots
    velocity_plot = create_velocity_plot()
    position_plot = create_position_plot()
    error_plot = create_error_plot()
    motor1_plot = create_motor_plot(1)
    motor2_plot = create_motor_plot(2)

    # Get template path
    template_path = Path(__file__).parent / "report_template.html"

    # Create report
    report = Report(template_path, plot_dpi=150)

    # Render with all the data
    report.render(
        # Header info
        title="BILBO Velocity Control Experiment",
        author="Robotics Lab",
        experiment_id="EXP-2024-001",

        # Introduction
        introduction="This comprehensive report documents a velocity control experiment "
                     "conducted on the BILBO two-wheeled inverted pendulum robot. "
                     "The experiment tests the robot's ability to track velocity setpoints "
                     "while maintaining balance.",

        # Summary box
        summary="The experiment achieved a mean tracking error of 0.023 m/s with "
                "99.2% uptime. All safety parameters remained within acceptable limits.",

        # Main result
        main_plot=velocity_plot,
        main_plot_caption="Figure 1: Velocity tracking performance showing target (dashed) "
                          "and actual (solid) velocities.",

        # Comparison plots
        comparison_title="Position and Error Analysis",
        plot_left=position_plot,
        plot_left_caption="Figure 2: XY trajectory during experiment.",
        plot_right=error_plot,
        plot_right_caption="Figure 3: Tracking error over time.",

        # Additional plots as a list
        additional_plots_title="Motor Analysis",
        additional_plots=[
            {"plot": motor1_plot, "caption": "Figure 4: Left motor current."},
            {"plot": motor2_plot, "caption": "Figure 5: Right motor current."},
        ],

        # Key metrics
        metrics={
            "Mean Tracking Error": 0.0234,
            "Max Tracking Error": 0.0891,
            "RMS Error": 0.0312,
            "Experiment Duration": "10.0 s",
            "Sample Rate": "100 Hz",
            "Control Mode": "Velocity",
        },

        # Data table
        table_title="Performance Summary by Phase",
        table_headers=["Phase", "Duration [s]", "Mean Error", "Max Error", "Status"],
        table_data=[
            ["Startup", 1.0, 0.045, 0.089, "OK"],
            ["Ramp Up", 1.5, 0.032, 0.067, "OK"],
            ["Steady State", 5.0, 0.018, 0.042, "OK"],
            ["Ramp Down", 1.5, 0.028, 0.058, "OK"],
            ["Shutdown", 1.0, 0.012, 0.031, "OK"],
        ],

        # Observations
        observations=[
            "Velocity tracking was stable throughout the experiment.",
            "Transient response during ramp phases was within specifications.",
            "Motor currents remained well below thermal limits.",
            "No balance corrections were required during steady state.",
        ],

        # Conclusion
        conclusion="The velocity control experiment was successful. The BILBO robot "
                   "demonstrated excellent tracking performance with errors consistently "
                   "below the 0.1 m/s threshold. The system is ready for more advanced "
                   "trajectory tracking experiments.",

        # Status
        status="success",
    )

    # Save as PDF and HTML
    report.show_html()
    # report.save_pdf("full_report.pdf")


# === EXAMPLE 3: Report with Warnings ==================================================================================
def example_report_with_warnings():
    """
    Report showing warning/failure states.
    """
    velocity_plot = create_velocity_plot()
    template_path = Path(__file__).parent / "report_template.html"

    report = Report(template_path)
    report.render(
        title="Experiment with Issues",
        introduction="This experiment encountered some issues during execution.",

        main_plot=velocity_plot,

        metrics={
            "Mean Error": 0.156,
            "Max Error": 0.423,
            "Uptime": "87.3%",
        },

        warnings=[
            "High tracking error detected during phase 2 (0.42 m/s peak).",
            "Motor 1 current exceeded soft limit at t=5.2s.",
            "IMU calibration may have drifted during experiment.",
        ],

        observations=[
            "Performance degraded after the 5-second mark.",
            "Possible external disturbance detected.",
        ],

        conclusion="The experiment completed but with degraded performance. "
                   "Recommend re-calibration before next run.",

        status="failure",
        status_message="Completed with errors - review required",
    )

    report.show_html()


# === EXAMPLE 4: Using render_report() Convenience Function ============================================================
def example_quick_report():
    """
    Quick report generation using the convenience function.
    """
    velocity_plot = create_velocity_plot()
    template_path = Path(__file__).parent / "report_template.html"

    # One-liner report generation
    render_report(
        template_path,
        output=None,  # None = open in viewer
        format='html',
        title="Quick Report",
        main_plot=velocity_plot,
        summary="A quick summary of the results.",
        metrics={"Error": 0.025, "Duration": "10s"},
    )


# === EXAMPLE 5: Custom Inline Template ================================================================================
def example_inline_template():
    """
    Create a report with an inline template string.
    """
    velocity_plot = create_velocity_plot()

    # Define template as a string
    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ title }}</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
            h1 { color: #2c3e50; }
            .metric { background: #f5f5f5; padding: 10px; margin: 5px 0; border-radius: 4px; }
            img { max-width: 100%; border: 1px solid #ddd; }
        </style>
    </head>
    <body>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>

        <h2>Results</h2>
        {{ plot }}

        <h2>Metrics</h2>
        {% for name, value in metrics.items() %}
        <div class="metric"><strong>{{ name }}:</strong> {{ value | format_number(3) }}</div>
        {% endfor %}

        <hr>
        <small>Generated: {{ generated_at | format_date }}</small>
    </body>
    </html>
    """

    report = Report(template_str)  # Pass string directly
    report.render(
        title="Inline Template Example",
        description="This report uses an inline template defined in Python.",
        plot=velocity_plot,
        metrics={"Error": 0.0234, "Accuracy": 0.9876, "Speed": 1.234},
    )

    report.show_html()


# === MAIN =============================================================================================================
if __name__ == "__main__":
    # Run one of the examples
    example_basic_report()
    # example_full_report()
    # example_report_with_warnings()
    # example_quick_report()
    # example_inline_template()
