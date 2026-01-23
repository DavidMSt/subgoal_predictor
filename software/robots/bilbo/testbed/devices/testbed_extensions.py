import time

from robots.bilbo.testbed.devices.testbed_display import TestbedDisplayClient
from robots.bilbo.testbed.devices.testbed_limbo_bar import TestbedLimboIndicator
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger


class BILBO_TestbedExtensions:
    limbo_bar: TestbedLimboIndicator
    display: TestbedDisplayClient

    _display_connected: bool = False
    _limbo_bar_connected: bool = False

    # === INIT =========================================================================================================
    def __init__(self, use_limbobar: bool = True, use_display: bool = True):
        self.logger = Logger('BILBO Testbed Extensions', 'DEBUG')
        self.limbo_bar = TestbedLimboIndicator() if use_limbobar else None
        self.display = TestbedDisplayClient() if use_display else None

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def start(self):
        if self.display is not None:
            if not self.display.start():
                self.logger.error("Could not start display client.")
                self._display_connected = False
            else:
                self._display_connected = True
                self.display.clear()

        if self.limbo_bar is not None:
            if not self.limbo_bar.start():
                self.logger.error("Could not start limbo bar.")
                self._limbo_bar_connected = False
            else:
                self._limbo_bar_connected = True
                self.limbo_bar.clear()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        if self._display_connected and self.display is not None:
            self.display.clear()
        if self._limbo_bar_connected and self.limbo_bar is not None:
            self.limbo_bar.clear()
            
    # ------------------------------------------------------------------------------------------------------------------
    def test(self):
        if self.display is not None and self._display_connected:
            self.display.set_text("TEST", color=(0, 255, 255))


if __name__ == "__main__":
    extensions = BILBO_TestbedExtensions()
    extensions.start()
    extensions.test()

    while True:
        time.sleep(1)
