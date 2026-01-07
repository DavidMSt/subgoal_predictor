import numpy as np

from core.utils.colors import get_segmented_progression_colors
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import redirections, addLogRedirection, LOGGING_COLORS
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.image import UpdatableImageWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.text import TextWidget, StatusWidget, StatusWidgetElement, LineScrollWidget
from robots.bilbo.robot.bilbo import BILBO
# from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_Experiment_Status
# from robots.bilbo.robot.experiment.experiments import DILC_Experiment


class DILC_App(GUI_Popup_Application):
    # experiment: DILC_Experiment

    # === INIT =========================================================================================================
    def __init__(self, robot: BILBO, config: dict = None):
        super().__init__('dilc_app', 'DILC APP', config)

        self.robot = robot

        self.popup = Popup(f"{self.id}_popup",
                           title='DILC',
                           allow_multiple=False,
                           grid=[20, 20],
                           size=[1100, 700],
                           type='window')

        if self.robot.experiment_handler.experiment is None:
            self.logger.error("No DILC experiment running")

        elif not isinstance(self.robot.experiment_handler.experiment, DILC_Experiment):
            self.logger.error("Experiment is not a DILC experiment")

        else:
            self.experiment = self.robot.experiment_handler.experiment

        self.new_output_trajectory = None
        self.new_error_norm = None
        self._buildPopup()

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def close(self, *args, **kwargs):
        self.popup.close()

    # ------------------------------------------------------------------------------------------------------------------
    def onMessage(self, message, sender=None) -> None:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def _onPopupClosed(self, *args, **kwargs):
        self.logger.warning(f"DILC Application closed")

    # === PRIVATE METHODS ==============================================================================================
    def _buildPopup(self):
        self.experiment_status_widget = StatusWidget(
            widget_id='experiment_status_widget',
            title='Experiment Status',
            elements={
                'status': StatusWidgetElement(label='Status:',
                                              color=[0, 0.5, 0],
                                              status='idle',
                                              ),
            }
        )

        self.popup.group.addWidget(self.experiment_status_widget, row=1, column=1, width=6, height=1)

        def set_experiment_status(*args, **kwargs):
            match self.experiment.status:
                case BILBO_Experiment_Status.NONE:
                    self.experiment_status_widget.elements['status'].status = '---'
                    self.experiment_status_widget.elements['status'].color = [0.3, 0.3, 0.3]
                case BILBO_Experiment_Status.RUNNING_TRAJECTORY:
                    self.experiment_status_widget.elements['status'].status = 'trajectory'
                    self.experiment_status_widget.elements['status'].color = [219 / 255, 222 / 255, 75 / 255]
                case BILBO_Experiment_Status.CALCULATING:
                    self.experiment_status_widget.elements['status'].status = 'calculating'
                    self.experiment_status_widget.elements['status'].color = [0.0, 0.0, 0.5]
                case BILBO_Experiment_Status.WAITING_FOR_USER:
                    self.experiment_status_widget.elements['status'].status = 'waiting for user'
                    self.experiment_status_widget.elements['status'].color = [184 / 255, 107 / 255, 48 / 255]
                case BILBO_Experiment_Status.FINISHED:
                    self.experiment_status_widget.elements['status'].status = 'finished'
                    self.experiment_status_widget.elements['status'].color = [0, 0.5, 0]
                case BILBO_Experiment_Status.ABORTED:
                    self.experiment_status_widget.elements['status'].status = 'aborted'
                    self.experiment_status_widget.elements['status'].color = [0.5, 0, 0]
            self.experiment_status_widget.updateConfig()

        set_experiment_status()
        self.experiment.events.status_changed.on(set_experiment_status)

        self.overview_widget = TextWidget(widget_id='overview_widget',
                                          title='',
                                          horizontal_alignment='left',
                                          vertical_alignment='top')

        self.popup.group.addWidget(self.overview_widget, row=2, column=1, width=6, height=6)

        # Add a text output widget to the popup
        self.text_output_widget = LineScrollWidget('text_output', font_size=10)
        self.popup.group.addWidget(self.text_output_widget, row=16, column=1, width=20, height=5)

        addLogRedirection(self._logRedirection,
                          redirect_all=False,
                          minimum_level='INFO',
                          past_time=4)

        # Add a settings group
        self.group_settings = Widget_Group(group_id='settings',
                                           title='Settings',
                                           show_title=True,
                                           rows=2, columns=5)
        self.popup.group.addWidget(self.group_settings, row=8, column=1, width=6, height=4)

        # Add Buttons for experiment control
        self.group_control = Widget_Group(group_id='control',
                                          title='Control',
                                          show_title=True,
                                          rows=2, columns=5)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])
        self.resume_button.disable()
        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=4, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[110 / 255, 82 / 255, 0 / 255])
        self.revert_button.disable()
        self.revert_button.callbacks.click.register(self.robot.core.interface_events.revert.set, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=5, width=1, height=1)

        self.start_button = Button(widget_id='start_button', text='Start', color=[0.0, 0.4, 0.0])
        self.start_button.callbacks.click.register(self.robot.core.interface_events.start.set, discard_inputs=True)
        self.experiment.events.experiment_started.on(self.start_button.disable)

        self.group_control.addWidget(self.start_button, row=1, column=1, width=1, height=1)

        stop_button = Button(widget_id='stop_button', text='Stop', color=[0.4, 0, 0])
        stop_button.callbacks.click.register(self.robot.experiment_handler.stopExperiment, discard_inputs=True)
        self.group_control.addWidget(stop_button, row=1, column=2, width=1, height=1)

        self.popup.group.addWidget(self.group_control, row=12, column=1, width=6, height=4)

        # Add the data plots
        self.plot_outputs = UpdatableImageWidget(widget_id='plot_outputs')
        self.popup.group.addWidget(self.plot_outputs, row=1, column=7, width=7, height=8)

        self._plotOutputData()

        self.experiment.events.trajectory_finished.on(self._onTrajectoryFinished)
        self.experiment.events.update.on(self._onUpdate)

        self.plot_error_norms = UpdatableImageWidget(widget_id='plot_error_norms')
        self.popup.group.addWidget(self.plot_error_norms, row=9, column=7, width=7, height=7)

        self.plot_iml_error_norms = UpdatableImageWidget(widget_id='plot_iml_error_norms')
        self.popup.group.addWidget(self.plot_iml_error_norms, row=9, column=14, width=7, height=7)

        self.plot_inputs = UpdatableImageWidget(widget_id='plot_inputs')
        self.popup.group.addWidget(self.plot_inputs, row=1, column=14, width=7, height=8)

        self._plotErrorNorms()
        self._plotIMLErrorNorms()
        self._plotInputs()

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.text_output_widget.addLine(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _plotOutputData(self):
        time_vector = self.experiment.reference_trajectory.time_vector
        reference = self.experiment.reference_trajectory_vec

        # Progression colors for trials
        anchors = [
            [0.09, 0.28, 0.67],  # blue-ish
            [0.00, 0.60, 0.33],  # green-ish
            [0.95, 0.60, 0.10],  # orange
        ]
        output_colors = get_segmented_progression_colors(self.experiment.num_trials, anchors, gamma=1.0)

        fig, ax = new_figure_agg(figsize=(6, 4), dpi=200)
        ax.set_title("Outputs", color="black")
        ax.set_ylim([-100, 100])
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Angle [deg]")
        ax.grid(True, alpha=0.3)

        # Reference trajectory (always bold dashed black)
        ax.plot(
            time_vector,
            np.rad2deg(reference),
            color="black",
            lw=2,
            linestyle="--",
            label="Reference",
            zorder=1,
        )

        outputs = self.experiment.outputs
        have_new = self.new_output_trajectory is not None

        # Style knobs
        base_alpha = 0.35 if have_new else 1.0
        base_lw = 1.2 if have_new else 1.5
        z_other = 1 if have_new else 2

        # Plot all existing outputs
        for i, output in enumerate(outputs):
            color = output_colors[i % max(1, len(output_colors))]
            ax.plot(
                time_vector,
                np.rad2deg(output),
                lw=base_lw,
                color=color,
                alpha=base_alpha,
                label=(f"Output {i + 1}" if not have_new else None),
                zorder=z_other,
            )

        # Plot the new output trajectory in its "future" color
        if have_new:
            new_index = len(outputs)  # index it would take if appended
            new_color = output_colors[new_index % max(1, len(output_colors))]
            ax.plot(
                time_vector,
                np.rad2deg(self.new_output_trajectory),
                color=new_color,
                lw=2.5,
                alpha=1.0,
                label=f"Output {new_index + 1} (new)",
                zorder=3,
            )

        ax.legend(loc="upper right")
        self.plot_outputs.setFromMatplotLib(fig, dpi=200)

    # ------------------------------------------------------------------------------------------------------------------
    def _onTrajectoryFinished(self, data, *args, **kwargs):
        trial_index = data['index']
        output_data = data['data']
        self.new_output_trajectory = output_data
        self.new_error_norm = data['error_norm']

        self._plotOutputData()
        self._plotErrorNorms()

    # ------------------------------------------------------------------------------------------------------------------
    def _onUpdate(self, data, *args, **kwargs):
        self.new_output_trajectory = None
        self.new_error_norm = None
        self._plotOutputData()
        self._plotErrorNorms()
        self._plotIMLErrorNorms()
        self._plotInputs()

    # ------------------------------------------------------------------------------------------------------------------
    def _plotErrorNorms(self):
        J = self.experiment.num_trials

        fig, ax = new_figure_agg(figsize=(6, 4), dpi=200)
        ax.set_title("Error Norms ILC", color="black")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Error Norm")
        ax.set_xlim([0, J + 1])
        ax.grid(True, alpha=0.3)

        # Collect data and pad
        error_norms = list(self.experiment.error_norms_ilc)
        error_norms = error_norms + [None] * (J - len(error_norms))

        x = np.arange(1, J + 1)
        y_line = np.array([
            np.nan if (v is None or (isinstance(v, float) and np.isnan(v))) else v
            for v in error_norms
        ], dtype=float)

        # Y limits based on current + new value
        valid_vals = [v for v in error_norms if v is not None and not np.isnan(v)]
        if self.new_error_norm is not None:
            valid_vals.append(self.new_error_norm)
        ymax = max(valid_vals) if valid_vals else 1.0
        ax.set_ylim(0, ymax * 1.1)

        # Draw connecting line (only for existing trials)
        ax.plot(x, y_line, color="red", lw=2, alpha=1.0, zorder=1, label="Error norm")

        # Marker styles
        base_size = 36
        new_size = 90
        base_alpha = 0.5 if self.new_error_norm is not None else 1.0

        # Draw markers for existing error norms
        for i, v in enumerate(error_norms):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            ax.scatter(
                [x[i]], [v],
                s=base_size,
                color="red",
                edgecolors="white", linewidths=0.8,
                alpha=base_alpha,
                zorder=2,
            )

        # Draw the new error norm if present (as an extra marker at the next trial index)
        if self.new_error_norm is not None:
            new_x = len(self.experiment.error_norms_ilc) + 1
            ax.scatter(
                [new_x], [self.new_error_norm],
                s=new_size,
                color="red",
                edgecolors="white", linewidths=1.2,
                alpha=1.0,
                zorder=3,
                label=f"Trial {new_x} (new)",
            )

        ax.legend(loc="upper right")
        self.plot_error_norms.setFromMatplotLib(fig, dpi=200)

    def _plotIMLErrorNorms(self):
        J = self.experiment.num_trials

        fig, ax = new_figure_agg(figsize=(6, 4), dpi=200)
        ax.set_title("Error Norms IML", color="black")
        ax.set_xlabel("Trial")
        ax.set_ylabel("Error Norm")
        ax.set_xlim([0, J + 1])
        ax.grid(True, alpha=0.3)

        # Collect data and pad
        error_norms = list(self.experiment.error_norms_iml)
        error_norms = error_norms + [None] * (J - len(error_norms))

        x = np.arange(1, J + 1)
        y_line = np.array([
            np.nan if (v is None or (isinstance(v, float) and np.isnan(v))) else v
            for v in error_norms
        ], dtype=float)

        # Y limits based on current + new value
        valid_vals = [v for v in error_norms if v is not None and not np.isnan(v)]
        ymax = max(valid_vals) if valid_vals else 1.0
        ax.set_ylim(0, ymax * 1.1)

        # Draw connecting line (only for existing trials)
        ax.plot(x, y_line, color="red", lw=2, alpha=1.0, zorder=1, label="Error norm")

        # Marker styles
        base_size = 36
        new_size = 90
        base_alpha = 1.0

        # Draw markers for existing error norms
        for i, v in enumerate(error_norms):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            ax.scatter(
                [x[i]], [v],
                s=base_size,
                color="red",
                edgecolors="white", linewidths=0.8,
                alpha=base_alpha,
                zorder=2,
            )

        ax.legend(loc="upper right")
        self.plot_iml_error_norms.setFromMatplotLib(fig, dpi=200)

    # ------------------------------------------------------------------------------------------------------------------
    def _plotInputs(self, *args, **kwargs):
        # --- Also plot the input trajectories (same color scheme as outputs) ---
        time_vector = self.experiment.reference_trajectory.time_vector
        inputs = self.experiment.inputs

        # Same segmented progression colors used in _plotOutputData
        anchors = [
            [0.09, 0.28, 0.67],  # blue-ish
            [0.00, 0.60, 0.33],  # green-ish
            [0.95, 0.60, 0.10],  # orange
        ]
        input_colors = get_segmented_progression_colors(self.experiment.num_trials, anchors, gamma=1.0)

        fig, ax = new_figure_agg(figsize=(6, 4), dpi=200)
        ax.set_title("Inputs", color="black")
        ax.set_xlabel("Time [s]")
        ax.set_ylabel("Input")
        ax.grid(True, alpha=0.3)

        for i, u in enumerate(inputs):
            color = input_colors[i % max(1, len(input_colors))]
            ax.plot(time_vector, u, lw=1.5, color=color, alpha=1.0, label=f"Input {i + 1}")

        if len(inputs) > 0:
            ax.legend(loc="upper right")

        self.plot_inputs.setFromMatplotLib(fig, dpi=200)
