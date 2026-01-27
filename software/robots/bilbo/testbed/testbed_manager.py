import dataclasses

from robots.bilbo.settings import AUTOSTOP_ROBOTS, AUTOSTART_ROBOTS
from robots.bilbo.testbed.devices.testbed_extensions import BILBO_TestbedExtensions
from robots.bilbo.testbed.testbed_objects import BILBO_TestbedAgent
from robots.bilbo.testbed.tracker.bilbo_tracker import BILBO_Tracker, BILBO_Tracker_Status
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, EventFlag
from core.utils.files import get_absolute_path
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak
from core.utils.timecode.timecode_server import TimecodeServer
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_OriginConfig, BILBO_LimboMarkerConfig
from core.utils.yaml_utils import load_yaml


@event_definition
class BILBO_TestbedManager_Events:
    new_robot: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    robot_disconnected: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    new_tracker_sample: Event
    initialized: Event = Event(copy_data_on_set=False)


DEFAULT_TESTBED_SIZE = {
    'x': [-5, 5],
    'y': [-5, 5]
}

# Available predefined testbed configurations
AVAILABLE_TESTBEDS = ['track', 'lab']


@dataclasses.dataclass
class BILBO_TestbedManager_Settings:
    """Settings for the testbed manager.

    Testbed resolution logic:
    1. If testbed_type is set (e.g., 'track', 'lab'): Load predefined config from configs/testbeds/
    2. If testbed_type is None and testbed_size is set: Use custom size
    3. If both are None: Use default 10x10m testbed
    """
    testbed_type: str | None = 'track'  # Name of predefined testbed ('track', 'lab') or None
    testbed_size: dict[str, list[
        float]] | None = None  # Custom size (dict with 'x' and 'y' keys. Size is a list with [min, max] values) or None
    tracker_max_sample_rate: int = 30
    use_optitrack: bool = True
    optitrack_server: str = 'palantir.lan'
    use_limbobar: bool = True
    use_display: bool = True
    use_timecode: bool = False


@dataclasses.dataclass
class BILBO_TestbedConfig:
    """Configuration loaded from a testbed YAML file."""
    size: dict[str, list[float]]
    origin_position: str = 'corner'
    origin: dict | None = None
    limbo_marker: dict | None = None


class BILBO_TestbedManager:
    robot_manager: BILBO_Manager
    tracker: BILBO_Tracker | None
    bilbos: dict[str, BILBO_TestbedAgent]
    extensions: BILBO_TestbedExtensions | None
    settings: BILBO_TestbedManager_Settings
    testbed_config: BILBO_TestbedConfig | None
    timecode_server: TimecodeServer | None

    # === INIT =========================================================================================================
    def __init__(self, settings: BILBO_TestbedManager_Settings):
        self.logger = Logger('BILBO Testbed Manager', 'DEBUG')
        self.settings = settings

        self.robot_manager = BILBO_Manager(enable_scanner=AUTOSTART_ROBOTS, autostop_robots=AUTOSTOP_ROBOTS)
        self.events = BILBO_TestbedManager_Events()

        # OptiTrack tracker (optional)
        if self.settings.use_optitrack:
            self.tracker = BILBO_Tracker(max_sample_rate=self.settings.tracker_max_sample_rate,
                                         server_address=self.settings.optitrack_server)
            self.tracker.events.new_sample.on(self._on_new_tracker_sample, max_rate=30)
            self.tracker.events.description_received.on(self._on_tracker_initialized, once=True)
            self.tracker.events.new_rigid_body.on(self._on_tracker_new_rigid_body)
        else:
            self.tracker = None

        # Joystick Control
        self.joystick_control = BILBO_JoystickControl(bilbo_manager=self.robot_manager, run_in_thread=True)

        self.bilbos = {}

        # Timecode server (optional)
        if self.settings.use_timecode:
            self.timecode_server = TimecodeServer()
        else:
            self.timecode_server = None

        # Testbed extensions (display, limbobar) - only create if any extension is enabled
        if self.settings.use_display or self.settings.use_limbobar:
            self.extensions = BILBO_TestbedExtensions(
                use_limbobar=self.settings.use_limbobar,
                use_display=self.settings.use_display
            )
        else:
            self.extensions = None

        self.testbed_config = None

        self.robot_manager.events.new_robot.on(self._on_new_robot)
        self.robot_manager.events.robot_disconnected.on(self._on_robot_disconnected)

    # === METHODS ======================================================================================================
    def init(self):
        # Load or create testbed config
        self.testbed_config = self._resolve_testbed_config()

        # self.logger.info(f"Testbed size: {self.testbed_config.size['x'][0]}m x {self.testbed_config.size['x'][1]}m x {self.testbed_config.size['y'][0]}m x {self.testbed_config.size['y'][1]}m")

        self.robot_manager.init()
        self.joystick_control.init()

        if self.tracker is not None:
            self.tracker.init()

        self.events.initialized.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _resolve_testbed_config(self) -> BILBO_TestbedConfig:
        """Resolve testbed configuration based on settings.

        Priority:
        1. Named testbed (testbed_type) → Load from predefined config file
        2. Custom size (testbed_size) → Create minimal config with given size
        3. Neither → Use default 10x10m testbed
        """
        if self.settings.testbed_type is not None:
            # Load predefined testbed config
            if self.settings.testbed_type not in AVAILABLE_TESTBEDS:
                raise ValueError(
                    f"Testbed '{self.settings.testbed_type}' not found. "
                    f"Available testbeds: {AVAILABLE_TESTBEDS}"
                )
            config_path = get_absolute_path(f'../configs/testbeds/testbed-{self.settings.testbed_type}.yaml')
            config_dict = load_yaml(config_path)
            return from_dict_auto(BILBO_TestbedConfig, config_dict)

        elif self.settings.testbed_size is not None:
            # Use custom size
            self.logger.info(f"Using custom testbed size: {self.settings.testbed_size}")
            return BILBO_TestbedConfig(
                size=self.settings.testbed_size,
                origin_position='corner'
            )

        else:
            # Use default size
            self.logger.info(f"No testbed specified, using default size: {DEFAULT_TESTBED_SIZE}")
            return BILBO_TestbedConfig(
                size=DEFAULT_TESTBED_SIZE,
                origin_position='corner'
            )

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        if self.tracker is not None:
            self.tracker.start()

        if self.timecode_server is not None:
            self.timecode_server.start()

        self.robot_manager.start()
        self.joystick_control.start()

        if self.extensions is not None:
            self.extensions.start()

    # ------------------------------------------------------------------------------------------------------------------
    def emergency_stop(self):
        self.robot_manager.emergencyStop()

    # === PRIVATE METHODS ==============================================================================================
    def _on_new_robot(self, robot: BILBO):

        if robot.id in self.bilbos:
            self.logger.warning(f"Robot {robot.id} already exists.")
            return

        self.logger.info(f"New robot connected: {robot.id}")
        speak(f"Robot {robot.id} connected")

        tracked_object = None
        if self.tracker is not None:
            if self.tracker.status != BILBO_Tracker_Status.RUNNING:
                self.logger.warning(f"Tracker is not running, cannot get optitrack data for robot {robot.id}")
            else:
                # Check if there is a tracked object for this robot
                tracked_object = self.tracker.add_robot(robot.id, robot.config)
                if tracked_object is None:
                    self.logger.warning(f"OptiTrack is running, but robot {robot.id} does not exist in tracker")

        container = BILBO_TestbedAgent(id=robot.id,
                                       robot=robot,
                                       tracked_object=tracked_object)

        self.bilbos[robot.id] = container

        if self.timecode_server is not None:
            self.timecode_server.add_target(robot.device.address)

        self.events.new_robot.set(container, flags={'type': 'robot', 'id': robot.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_robot_disconnected(self, robot: BILBO):
        self.logger.info(f"Robot disconnected: {robot.id}")
        speak(f"Robot {robot.id} disconnected")
        if robot.id not in self.bilbos:
            self.logger.warning(f"Robot {robot.id} does not exist in bilbos")
            return

        container = self.bilbos[robot.id]
        del self.bilbos[robot.id]

        if self.tracker is not None:
            self.tracker.remove_robot(robot.id)

        if self.timecode_server is not None:
            self.timecode_server.remove_target(robot.device.address)

        self.events.robot_disconnected.set(container, flags={'type': 'robot', 'id': robot.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_initialized(self, *args, **kwargs):
        if self.testbed_config is None:
            return

        if self.testbed_config.origin is not None:
            origin_config = from_dict_auto(BILBO_OriginConfig, self.testbed_config.origin)
            self.tracker.add_origin(origin_config.id, origin_config)

        if self.testbed_config.limbo_marker is not None:
            limbo_marker_config = from_dict_auto(BILBO_LimboMarkerConfig, self.testbed_config.limbo_marker)
            self.tracker.add_limbo_bar(limbo_marker_config.id, limbo_marker_config)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        self.events.new_tracker_sample.set()

        # # Skip limbo bar evaluation during cooldown
        # if self._limbobar_cooldown:
        #     return
        #
        # for bilbo in self.bilbos.values():
        #     self.limbobar.update(bilbo)
        #
        # if self.limbobar.hit:
        #     self.extensions.limbo_bar.blinkRed()
        #     self._limbobar_cooldown = True
        #     set_timeout(self._limbobar_end_cooldown, 3)

    # ------------------------------------------------------------------------------------------------------------------
    # def _limbobar_end_cooldown(self):
    #     """Reset limbo bar and end cooldown period."""
    #     self.limbobar.reset()
    #     self._limbobar_cooldown = False

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_new_rigid_body(self, rigid_body: dict):
        self.logger.error(f"Received rigid body from OptiTrack: {rigid_body}. This is currently not supported. All "
                          f"rigid bodies need to be available before starting the application!")
