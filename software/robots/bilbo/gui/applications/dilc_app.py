from core.utils.colors import random_color_from_palette
from core.utils.exit import register_exit_callback
from extensions.gui.src.lib.objects.objects import Widget_Group
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.image import UpdatableImageWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.experiment.multi_trial_experiments import DILC_Experiment


class DILC_APP(GUI_Popup_Application):
    experiment: DILC_Experiment

    def __init__(self,
                 gui,
                 robot: BILBO,
                 experiment: DILC_Experiment,
                 config: dict = None):
        super().__init__('dilc_app', 'DILC APP', config)
        self.gui = gui
        self.robot = robot
        self.experiment = experiment

        self.popup = Popup(f"{self.id}_popup",
                           title='DILC',
                           allow_multiple=False,
                           grid=[20, 20],
                           size=[1100, 700],
                           type='window')

        self._build_popup()

        self.experiment.events.experiment_error.on(self.close)

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.popup.close()

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def onMessage(self, message, sender=None) -> None:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def _onPopupClosed(self, *args, **kwargs):
        self.logger.warning(f"DILC Application closed")

    # ------------------------------------------------------------------------------------------------------------------
    def _build_popup(self):
        # Experiment Status
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

        # Add Buttons for experiment control
        self.group_control = Widget_Group(group_id='control',
                                          title='Control',
                                          show_title=True,
                                          rows=2, columns=5)

        self.popup.group.addWidget(self.group_control, row=12, column=1, width=6, height=4)

        self.resume_button = Button(widget_id='resume_button', text='Resume', color=[0.0, 0.4, 0.0])

        # self.resume_button.disable()

        self.resume_button.callbacks.click.register(self.robot.core.interface_events.resume.set, discard_inputs=True)
        self.group_control.addWidget(self.resume_button, row=1, column=4, width=1, height=1)

        self.revert_button = Button(widget_id='revert_button', text='Revert', color=[110 / 255, 82 / 255, 0 / 255])
        # self.revert_button.disable()
        self.revert_button.callbacks.click.register(self.robot.core.interface_events.revert.set, discard_inputs=True)
        self.group_control.addWidget(self.revert_button, row=1, column=5, width=1, height=1)

        self.start_button = Button(widget_id='start_button', text='Start', color=[0.0, 0.4, 0.0])
        self.start_button.callbacks.click.register(self.robot.core.interface_events.start.set, discard_inputs=True)
        # self.experiment.events.experiment_started.on(self.start_button.disable)

        self.group_control.addWidget(self.start_button, row=1, column=1, width=1, height=1)

        stop_button = Button(widget_id='stop_button', text='Stop', color=[0.4, 0, 0])
        stop_button.disable()
        # stop_button.callbacks.click.register(self.robot.experiment_handler.stopExperiment, discard_inputs=True)
        self.group_control.addWidget(stop_button, row=1, column=2, width=1, height=1)



        self.plot_outputs = UpdatableImageWidget(widget_id='plot_outputs')
        self.popup.group.addWidget(self.plot_outputs, row=1, column=7, width=7, height=8)

        self.plot_error_norms = UpdatableImageWidget(widget_id='plot_error_norms')
        self.popup.group.addWidget(self.plot_error_norms, row=9, column=7, width=7, height=7)

        self.plot_iml_error_norms = UpdatableImageWidget(widget_id='plot_iml_error_norms')
        self.popup.group.addWidget(self.plot_iml_error_norms, row=9, column=14, width=7, height=7)

        self.plot_inputs = UpdatableImageWidget(widget_id='plot_inputs')
        self.popup.group.addWidget(self.plot_inputs, row=1, column=14, width=7, height=8)
