import threading
import time

from core.utils.colors import random_color_from_palette
from core.utils.time import delayed_execution
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.number import DigitalNumberWidget
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.objects.python.popup import Popup


class ExampleApp(GUI_Popup_Application):
    _exit = False

    # === INIT =========================================================================================================
    def __init__(self, config: dict = None):
        super().__init__('example_app', 'Example', config)
        self.popup = Popup(f"{self.id}_popup",
                           title='Example App',
                           allow_multiple=True,
                           grid=[10, 10],
                           size=[800, 600],
                           type='window')

        self._buildApp()
        self.i = 0

        self.thread = threading.Thread(target=self._task, daemon=True)
        self.thread.start()

    # === METHODS ======================================================================================================
    def onMessage(self, message, sender=None) -> None:
        pass

    def getConfiguration(self):
        config = super().getConfiguration()
        return config

    def close(self):
        self._exit = True
        self.thread.join()
        self.popup.close()
        self.logger.important("Closing Example App")

    # === PRIVATE METHODS ==============================================================================================
    def _buildApp(self):
        test_button = Button('test_button', 'Test Button', color=[0.3, 0, 0])
        self.popup.group.addWidget(test_button)

        def test_button_callback(*args, **kwargs):
            print('test_button_callback')
            test_button.updateConfig(color=random_color_from_palette('dark'))

        test_button.callbacks.click.register(test_button_callback)

        self.digital_number_widget = DigitalNumberWidget('digital_number_widget',
                                                         min_value=-1000,
                                                         max_value=1000,
                                                         value=0,
                                                         increment=1,
                                                         title='Theta',
                                                         title_position='left',
                                                         color=[0.3, 0, 0])

        self.popup.group.addWidget(self.digital_number_widget, width=3, height=1)

    def _task(self):

        while not self._exit:
            self.i += 1
            if self.i > 1000:
                self.i = 0
            self.digital_number_widget.value = self.i
            time.sleep(0.1)

    def _onPopupClosed(self, *args, **kwargs):
        if not self._exit:
            self.close()
