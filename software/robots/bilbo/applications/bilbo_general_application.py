import dataclasses
import logging
import os
import sys
import time

from core.utils.dataclass_utils import from_dict_auto

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one or more levels as needed
top_level_module = os.path.abspath(os.path.join(current_dir, '..', '..'))  # adjust as needed

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)


# === CUSTOM MODULES ===================================================================================================
from robots.bilbo.gui.bilbo_gui import BILBO_Application_GUI
# from extensions.cli.archive.cli_gui import CLI_GUI_Server
from extensions.cli.cli import CommandSet, CLI, Command
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from core.utils.exit import register_exit_callback, exit_program
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils.loop import infinite_loop
from core.utils.sound.sound import speak, SoundSystem
from core.utils.files import get_absolute_path
from robots.bilbo.testbed.testbed_manager import TestbedManager, TestbedManagerSettings, TestbedSettings, \
    TrackerSettings, TrackedObjects, ExtensionsSettings, RobotSettings
from robots.bilbo.simulation.virtual_testbed import VirtualTestbed_Config
from core.utils.callbacks import Callback
from core.utils.network.network import getHostIP
from robots.bilbo.robot.bilbo import BILBO
from core.utils.yaml_utils import load_yaml

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True


@dataclasses.dataclass
class MDNSSettings:
    enabled: bool = True
    hostname: str = 'bilbolab'
    use_port_80: bool = False


@dataclasses.dataclass
class ApplicationSettings:
    """Settings as loaded from application_settings.yaml. Top-level keys map 1:1 to the YAML."""
    testbed: TestbedSettings = dataclasses.field(default_factory=TestbedSettings)
    robots: RobotSettings = dataclasses.field(default_factory=RobotSettings)
    extensions: ExtensionsSettings = dataclasses.field(default_factory=ExtensionsSettings)
    simulation: VirtualTestbed_Config = dataclasses.field(default_factory=VirtualTestbed_Config)
    tracker: TrackerSettings = dataclasses.field(default_factory=TrackerSettings)
    tracked_objects: TrackedObjects = dataclasses.field(default_factory=TrackedObjects)
    mdns: MDNSSettings = dataclasses.field(default_factory=MDNSSettings)

    @property
    def testbed_manager_settings(self) -> TestbedManagerSettings:
        return TestbedManagerSettings(
            testbed=self.testbed,
            robots=self.robots,
            tracker=self.tracker,
            tracked_objects=self.tracked_objects,
            extensions=self.extensions,
            simulation=self.simulation,
        )


def load_application_settings(path: str | None = None) -> ApplicationSettings:
    """Load application settings from YAML file."""
    if path is None:
        path = get_absolute_path('application_settings.yaml')

    yaml_data = load_yaml(path)
    return from_dict_auto(ApplicationSettings, yaml_data)



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
    settings = load_application_settings()

    app = BILBO_Application(settings=settings)
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_bilbo_application()
