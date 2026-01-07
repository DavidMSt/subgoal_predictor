from core.utils.exit import register_exit_callback
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.text import StatusWidget, StatusWidgetElement
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.experiment.multi_trial_experiments import DILC_Experiment


class DILC_APP(GUI_Popup_Application):
    experiment: DILC_Experiment

    def __init__(self,
                 robot: BILBO,
                 experiment: DILC_Experiment,
                 config: dict = None):
        super().__init__('dilc_app', 'DILC APP', config)
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
