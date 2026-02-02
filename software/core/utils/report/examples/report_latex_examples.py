"""
LaTeX Report Generation Examples

Demonstrates the LaTeX report generation system with Jinja2 templating.
"""

import numpy as np
from pathlib import Path

from core.utils.plotting.plot import Plot, Axis, AxisConfig
from core.utils.report import LatexReport, render_latex_report, latex_table


# === HELPER FUNCTIONS =================================================================================================
def create_velocity_plot() -> Plot:
    """Create a sample velocity tracking plot."""
    t = np.linspace(0, 10, 500)
    target = np.ones_like(t) * 0.5
    target[t < 1] = 0
    target[t > 8] = 0
    actual = target + 0.05 * np.sin(5 * t) + 0.02 * np.random.randn(len(t))
    actual = np.convolve(actual, np.ones(10)/10, mode='same')  # Smooth

    p = Plot(rows=1, columns=1, size=(6, 3.5), use_agg_backend=True)
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

    p = Plot(rows=1, columns=1, size=(5, 3.5), use_agg_backend=True)
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

    p = Plot(rows=1, columns=1, size=(5, 3.5), use_agg_backend=True)
    axis = Axis(id="main", config=AxisConfig(
        title="Tracking Error",
        xlabel="Time [s]",
        ylabel="Error [m/s]",
        grid=True,
    ))
    p.set_axis(1, 1, axis)
    axis.plot(t, error, color="tab:red", linewidth=1)
    axis.plot(t, np.zeros_like(t), color="black", linestyle="--", linewidth=0.5, alpha=0.5)
    return p


def create_motor_plot(motor_id: int) -> Plot:
    """Create a motor current plot."""
    t = np.linspace(0, 10, 500)
    current = 0.3 * np.sin(2 * t + motor_id) + 0.1 * np.random.randn(len(t))

    p = Plot(rows=1, columns=1, size=(4, 2.5), use_agg_backend=True)
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
    template_path = Path(__file__).parent / "report_template.tex"

    # Create and render report
    report = LatexReport(template_path)
    report.render(
        title="Velocity Tracking Experiment",
        author="BilboLab",
        introduction="This report presents the results of a velocity tracking experiment "
                     "performed with the BILBO robot.",
        main_plot=velocity_plot,
        main_plot_caption="Velocity tracking performance over 10 seconds.",
        conclusion="The robot successfully tracked the target velocity with minimal error.",
        status="success",
        status_message="Experiment completed successfully",
    )

    # Show in PDF viewer
    report.show_pdf()
    # report.save_pdf("basic_report.pdf")
    # report.save_tex("basic_report.tex")


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
    template_path = Path(__file__).parent / "report_template.tex"

    # Create report
    report = LatexReport(template_path, plot_dpi=150)

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
        main_plot_caption="Velocity tracking performance showing target (dashed) "
                          "and actual (solid) velocities.",

        # Comparison plots
        comparison_title="Position and Error Analysis",
        plot_left=position_plot,
        plot_left_caption="XY trajectory during experiment.",
        plot_right=error_plot,
        plot_right_caption="Tracking error over time.",

        # Additional plots as a list
        additional_plots_title="Motor Analysis",
        additional_plots=[
            {"plot": motor1_plot, "caption": "Left motor current."},
            {"plot": motor2_plot, "caption": "Right motor current."},
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

    # Show PDF
    report.show_pdf()


# === EXAMPLE 3: Report with Warnings ==================================================================================
def example_report_with_warnings():
    """
    Report showing warning/failure states.
    """
    velocity_plot = create_velocity_plot()
    template_path = Path(__file__).parent / "report_template.tex"

    report = LatexReport(template_path)
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

    report.show_pdf()


# === EXAMPLE 4: Using render_latex_report() Convenience Function ======================================================
def example_quick_report():
    """
    Quick report generation using the convenience function.
    """
    velocity_plot = create_velocity_plot()
    template_path = Path(__file__).parent / "report_template.tex"

    # One-liner report generation
    render_latex_report(
        template_path,
        output=None,  # None = open in viewer
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

    # Define template as a string (using Jinja2 LaTeX syntax)
    template_str = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{geometry}
\geometry{margin=2.5cm}

\begin{document}

\begin{center}
{\Huge\bfseries \VAR{title|e}}

\vspace{1em}
{\large \VAR{description|e}}
\end{center}

\section*{Results}
\begin{figure}[h]
    \centering
    \VAR{plot}
    \caption{Experimental results}
\end{figure}

\section*{Metrics}
\begin{tabular}{ll}
\toprule
\textbf{Metric} & \textbf{Value} \\
\midrule
\BLOCK{for name, value in metrics.items()}
\VAR{name|e} & \VAR{value|format_number(3)} \\
\BLOCK{endfor}
\bottomrule
\end{tabular}

\vfill
\begin{center}
\small Generated: \VAR{generated_at|format_date}
\end{center}

\end{document}
"""

    report = LatexReport(template_str)
    report.render(
        title="Inline Template Example",
        description="This report uses an inline template defined in Python.",
        plot=velocity_plot,
        metrics={"Error": 0.0234, "Accuracy": 0.9876, "Speed": 1.234},
    )

    report.show_pdf()


# === EXAMPLE 6: Using the latex_table Helper ==========================================================================
def example_table_helper():
    """
    Demonstrate the latex_table helper function for generating tables.
    """
    # Generate a table
    table_code = latex_table(
        headers=["Robot", "Speed [m/s]", "Error [m]", "Status"],
        data=[
            ["BILBO-1", 0.5, 0.023, "OK"],
            ["BILBO-2", 0.48, 0.031, "OK"],
            ["BILBO-3", 0.52, 0.019, "OK"],
        ],
        caption="Robot performance comparison",
        label="tab:performance",
        alignment="lccc",
    )

    print("Generated LaTeX table:")
    print(table_code)


# === MAIN =============================================================================================================
if __name__ == "__main__":
    # Run one of the examples
    example_basic_report()
    # example_full_report()
    # example_report_with_warnings()
    # example_quick_report()
    # example_inline_template()
    # example_table_helper()
