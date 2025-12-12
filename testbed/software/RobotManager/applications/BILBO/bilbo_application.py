import logging
import os
import sys
import time

from applications.BILBO.testbed_manager import BILBO_TestbedManager, BILBO_TestbedAgent
from core.utils.callbacks import Callback
from robots.bilbo.robot.bilbo import BILBO

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one or more levels as needed
top_level_module = os.path.abspath(os.path.join(current_dir, '..', '..'))  # adjust as needed

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

# === CUSTOM MODULES ===================================================================================================
from applications.BILBO.gui.bilbo_application_gui import BILBO_Application_GUI
from applications.BILBO.settings import AUTOSTART_ROBOTS, AUTOSTOP_ROBOTS
from applications.BILBO.tracker.bilbo_tracker import BILBO_Tracker
# from extensions.cli.archive.cli_gui import CLI_GUI_Server
from extensions.cli.cli import CommandSet, CLI
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils.loop import infinite_loop
from core.utils.sound.sound import speak, SoundSystem
from core.utils.files import get_absolute_path

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True


# EXPERIMENT_DIR = relativeToFullPath('~/bilbolab/experiments/bilbo')


# ======================================================================================================================
class BILBO_Application:
    manager: BILBO_TestbedManager
    soundsystem: SoundSystem

    def __init__(self):
        # self.robot_manager = BILBO_Manager(enable_scanner=AUTOSTART_ROBOTS, autostop_robots=AUTOSTOP_ROBOTS)
        #
        # # self.robot_manager.callbacks.stream.register(self.gui.sendRawStream)
        # self.robot_manager.callbacks.new_robot.register(self._newRobot_callback)
        # self.robot_manager.callbacks.robot_disconnected.register(self._robotDisconnected_callback)

        self.manager = BILBO_TestbedManager()
        self.manager.events.new_robot.on(self._newRobot_callback)
        self.manager.events.robot_disconnected.on(self._robotDisconnected_callback)
        # self.manager.robot_manager.callbacks.stream.register(self.gui.sendRawStream)

        # CLI
        self.cli = CLI(id='bilbo_app_cli')

        # Logging
        self.logger = Logger('APP')
        self.logger.setLevel('INFO')

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # GUI
        self.gui = BILBO_Application_GUI(host=self.manager.robot_manager.host,
                                         testbed_manager=self.manager,
                                         cli=self.cli,
                                         joystick_control=self.manager.joystick_control)

        self.gui.callbacks.emergency_stop.register(self.manager.emergency_stop)

        # Exit Handling
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        setLoggerLevel(logger=['tcp', 'server', 'UDP', 'UDP Socket', 'Sound'], level=logging.WARNING)

        self.manager.init()

        self.cli.root.addChild(self.manager.robot_manager.cli)
        self.cli.root.addChild(self.manager.joystick_control.cli_command_set)

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
        time.sleep(2)
        global ENABLE_SPEECH_OUTPUT
        ENABLE_SPEECH_OUTPUT = False

    # ==================================================================================================================
    def _newRobot_callback(self, bilbo: BILBO_TestbedAgent, *args, **kwargs):

        # Wait until the first sample is received
        if not bilbo.robot.core.initialized:
            bilbo.robot.core.events.initialized.on(callback=Callback(function=self.gui.addRobot,
                                                                     inputs={'robot': bilbo.robot},
                                                                     discard_inputs=True),
                                                   once=True,
                                                   discard_data=True)
        else:
            self.gui.addRobot(bilbo.robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _robotDisconnected_callback(self, bilbo, *args, **kwargs):
        self.gui.removeRobot(bilbo)


# ======================================================================================================================
def run_bilbo_application():
    app = BILBO_Application()
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_bilbo_application()
