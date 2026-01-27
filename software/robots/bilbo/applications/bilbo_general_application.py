import dataclasses
import logging
import os
import sys
import time

from robots.bilbo.testbed.testbed_objects import BILBO_TestbedAgent

# Get the directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Go up one or more levels as needed
top_level_module = os.path.abspath(os.path.join(current_dir, '..', '..'))  # adjust as needed

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

# === CUSTOM MODULES ===================================================================================================
from robots.bilbo.gui.bilbo_application_gui import BILBO_Application_GUI
from robots.bilbo.settings import AUTOSTART_ROBOTS, AUTOSTOP_ROBOTS
from robots.bilbo.testbed.tracker.bilbo_tracker import BILBO_Tracker
# from extensions.cli.archive.cli_gui import CLI_GUI_Server
from extensions.cli.cli import CommandSet, CLI
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from core.utils.exit import register_exit_callback, exit_program
from core.utils.logging_utils import setLoggerLevel, Logger
from core.utils.loop import infinite_loop
from core.utils.sound.sound import speak, SoundSystem
from core.utils.files import get_absolute_path
from robots.bilbo.testbed.testbed_manager import BILBO_TestbedManager, BILBO_TestbedManager_Settings
from core.utils.callbacks import Callback
from core.utils.network.network import getHostIP
from robots.bilbo.robot.bilbo import BILBO
from core.utils.yaml_utils import load_yaml

# ======================================================================================================================
ENABLE_SPEECH_OUTPUT = True


# ======================================================================================================================
# Settings dataclasses for YAML parsing
# ======================================================================================================================
@dataclasses.dataclass
class ExtensionsSettings:
    display: bool = True
    limbobar: bool = True
    timecode: bool = False


@dataclasses.dataclass
class OptitrackSettings:
    enabled: bool = True
    server: str = 'palantir.lan'


@dataclasses.dataclass
class TestbedSettings:
    type: str | None = None
    size: dict | None = None


@dataclasses.dataclass
class MDNSSettings:
    enabled: bool = True
    hostname: str = 'bilbolab'  # Will be accessible as bilbolab.local
    use_port_80: bool = False  # If True, runs reverse proxy on port 80 (requires sudo)


@dataclasses.dataclass
class ApplicationSettingsYAML:
    """Settings as loaded from application_settings.yaml"""
    extensions: ExtensionsSettings = dataclasses.field(default_factory=ExtensionsSettings)
    optitrack: OptitrackSettings = dataclasses.field(default_factory=OptitrackSettings)
    testbed: TestbedSettings = dataclasses.field(default_factory=TestbedSettings)
    mdns: MDNSSettings = dataclasses.field(default_factory=MDNSSettings)


def load_application_settings(path: str | None = None) -> ApplicationSettingsYAML:
    """Load application settings from YAML file."""
    if path is None:
        path = get_absolute_path('application_settings.yaml')

    yaml_data = load_yaml(path)

    # Parse nested dataclasses
    extensions = ExtensionsSettings(**yaml_data.get('extensions', {})) if yaml_data.get(
        'extensions') else ExtensionsSettings()
    optitrack = OptitrackSettings(**yaml_data.get('optitrack', {})) if yaml_data.get(
        'optitrack') else OptitrackSettings()
    testbed = TestbedSettings(**yaml_data.get('testbed', {})) if yaml_data.get('testbed') else TestbedSettings()
    mdns = MDNSSettings(**yaml_data.get('mdns', {})) if yaml_data.get('mdns') else MDNSSettings()

    return ApplicationSettingsYAML(
        extensions=extensions,
        optitrack=optitrack,
        testbed=testbed,
        mdns=mdns
    )


# ======================================================================================================================
class BILBO_Application:
    manager: BILBO_TestbedManager
    soundsystem: SoundSystem

    def __init__(self, settings: ApplicationSettingsYAML):

        self.settings = settings

        # Logging
        self.logger = Logger('APP')
        self.logger.setLevel('INFO')

        # Check if there is a valid host IP
        ip = getHostIP()
        if ip is None:
            self.logger.error("No valid IP address for the server")
            exit_program()

        # Convert testbed size from list to tuple if provided
        testbed_size = settings.testbed.size if settings.testbed.size else None

        testbed_settings = BILBO_TestbedManager_Settings(
            testbed_type=settings.testbed.type,
            testbed_size=testbed_size,
            optitrack_server=settings.optitrack.server,
            use_optitrack=settings.optitrack.enabled,
            use_limbobar=settings.extensions.limbobar,
            use_display=settings.extensions.display,
            use_timecode=settings.extensions.timecode,
        )

        self.manager = BILBO_TestbedManager(testbed_settings)
        self.manager.events.new_robot.on(self._newRobot_callback)
        self.manager.events.robot_disconnected.on(self._robotDisconnected_callback)
        # self.manager.robot_manager.callbacks.stream.register(self.gui.sendRawStream)

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
                                         joystick_control=self.manager.joystick_control,
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
        self.gui.close()
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
    # Load settings from YAML file
    settings = load_application_settings()

    app = BILBO_Application(settings=settings)
    app.init()
    app.start()

    infinite_loop()


if __name__ == '__main__':
    run_bilbo_application()
