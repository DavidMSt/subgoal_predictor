import logging
import os
import sys
import time

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one or more levels as needed
top_level_module = os.path.abspath(os.path.join(current_dir, '..', '..'))  # adjust as needed

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)


# === CUSTOM MODULES ===================================================================================================
from robots.bilbo.gui.bilbo_gui import BILBO_Application_GUI
from extensions.cli.cli import CLI
from core.utils.exit import register_exit_callback, exit_program
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils.loop import infinite_loop
from core.utils.sound.sound import speak, SoundSystem
from robots.bilbo.testbed.testbed_manager import TestbedManager
from core.utils.network.network import getHostIP
from robots.bilbo.settings import ApplicationSettings, load_settings

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True



# ======================================================================================================================
class BILBO_Application:
    manager: TestbedManager
    soundsystem: SoundSystem

    def __init__(self, settings: ApplicationSettings):

        self.settings = settings

        # Logging
        self.logger = Logger('APP')
        self.logger.setLevel('INFO')

        # Check if there is a valid host IP
        ip = getHostIP()
        if ip is None:
            self.logger.error("No valid IP address for the server")
            exit_program()


        self.manager = TestbedManager(settings=settings.testbed_manager_settings)

        # CLI
        self.cli = CLI(id='bilbo_app_cli')

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # GUI
        self.gui = BILBO_Application_GUI(settings=self.settings,
                                         host=self.manager.robot_manager.host,
                                         testbed_manager=self.manager,
                                         cli=self.cli,
                                         joystick_control=None,
                                         enable_mdns=settings.mdns.enabled,
                                         mdns_hostname=settings.mdns.hostname,
                                         mdns_use_port_80=settings.mdns.use_port_80)

        self.gui.callbacks.emergency_stop.register(self.manager.emergency_stop)

        # Exit Handling
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        setLoggerLevel(logger=['tcp', 'server', 'UDP', 'UDP Socket', 'Sound'], level=logging.WARNING)

        self.manager.init()

        self.cli.root.addChild(self.manager.robot_manager.cli)
        self.cli.root.addChild(self.manager.cli)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info('Starting Bilbo application')
        speak('Start Bilbo application')
        self.manager.start()
        self.gui.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        speak('Stop Bilbo application')
        self.logger.info('Closing Bilbo application')
        self.gui.close()
        time.sleep(2)
        global ENABLE_SPEECH_OUTPUT
        ENABLE_SPEECH_OUTPUT = False


# ======================================================================================================================
def run_bilbo_application():
    # Load settings from YAML file
    settings = load_settings()

    app = BILBO_Application(settings=settings)
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_bilbo_application()
