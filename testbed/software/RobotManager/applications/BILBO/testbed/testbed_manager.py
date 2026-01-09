import dataclasses
import time

import yaml

from applications.BILBO.settings import AUTOSTOP_ROBOTS, AUTOSTART_ROBOTS
from applications.BILBO.testbed.testbed_extensions import BILBO_TestbedExtensions
from applications.BILBO.tracker.bilbo_tracker import BILBO_Tracker, TrackedBILBO, BILBO_Tracker_Status
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event, EventFlag
from core.utils.files import file_exists, get_absolute_path
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak
from core.utils.time import set_timeout
from core.utils.timecode.timecode_server import TimecodeServer
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_OriginConfig, BILBO_LimboMarkerConfig
from core.utils.yaml_utils import load_yaml


@dataclasses.dataclass
class BILBO_TestbedAgent:
    id: str
    robot: BILBO
    tracked_object: TrackedBILBO


@event_definition
class BILBO_TestbedManager_Events:
    new_robot: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    robot_disconnected: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    new_tracker_sample: Event
    initialized: Event = Event(copy_data_on_set=False)


@dataclasses.dataclass
class BILBO_TestbedManager_Settings:
    testbed: str = 'track'  # can be 'track' or 'lab'


@dataclasses.dataclass
class BILBO_TestbedConfig:
    size: list[float]
    origin_position: str
    origin: dict | None = None
    limbo_marker: dict | None = None


class BILBO_TestbedManager:
    robot_manager: BILBO_Manager
    tracker: BILBO_Tracker
    bilbos: dict[str, BILBO_TestbedAgent]
    extensions: BILBO_TestbedExtensions
    settings: BILBO_TestbedManager_Settings
    testbed_config: BILBO_TestbedConfig

    # === INIT =========================================================================================================
    def __init__(self, settings: BILBO_TestbedManager_Settings):
        self.logger = Logger('BILBO Testbed Manager', 'DEBUG')
        self.settings = settings

        self.robot_manager = BILBO_Manager(enable_scanner=AUTOSTART_ROBOTS, autostop_robots=AUTOSTOP_ROBOTS)
        self.tracker = BILBO_Tracker()
        self.events = BILBO_TestbedManager_Events()

        self.tracker.events.new_sample.on(self._on_new_tracker_sample, max_rate=20)
        self.tracker.events.description_received.on(self._on_tracker_initialized, once=True)
        self.tracker.events.new_rigid_body.on(self._on_tracker_new_rigid_body)

        # Joystick Control
        self.joystick_control = BILBO_JoystickControl(bilbo_manager=self.robot_manager, run_in_thread=True)

        self.bilbos = {}

        self.timecode_server = TimecodeServer()
        # self.extensions = BILBO_TestbedExtensions()

        self.robot_manager.events.new_robot.on(self._on_new_robot)
        self.robot_manager.events.robot_disconnected.on(self._on_robot_disconnected)

    # === METHODS ======================================================================================================
    def init(self):

        # Load the testbed config
        match self.settings.testbed:
            case 'track':
                testbed_config = get_absolute_path('../configs/testbed-track.yaml')
                testbed_config_dict = load_yaml(testbed_config)
                self.testbed_config = from_dict_auto(BILBO_TestbedConfig, testbed_config_dict)
            case 'lab':
                testbed_config = get_absolute_path('../configs/testbed-lab.yaml')
                testbed_config_dict = load_yaml(testbed_config)
                self.testbed_config = from_dict_auto(BILBO_TestbedConfig, testbed_config_dict)
            case _:
                raise ValueError(f"Testbed '{self.settings.testbed}' not supported.")

        self.robot_manager.init()
        self.joystick_control.init()
        self.tracker.init()

        self.events.initialized.set()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.tracker.start()
        self.timecode_server.start()
        self.robot_manager.start()
        self.joystick_control.start()

        # self.extensions.start()

        # set_timeout(self.extensions.limbo_bar.blink, 2, (0, 100, 0), 5, 400)

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

        if self.tracker.status != BILBO_Tracker_Status.RUNNING:
            self.logger.warning(f"Tracker is not running, cannot get optitrack data for robot {robot.id}")
            tracked_object = None
        else:
            # Check if there is a tracked object for this robot
            tracked_object = self.tracker.add_robot(robot.id, robot.config)

            if tracked_object is None:
                self.logger.warning(f"OptiTrack is running, but robot {robot.id} does not exist in tracker")

        container = BILBO_TestbedAgent(id=robot.id,
                                       robot=robot,
                                       tracked_object=tracked_object)

        self.bilbos[robot.id] = container

        # self.timecode_server.add_target(robot.device.address)

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
        self.tracker.remove_robot(robot.id)
        self.timecode_server.remove_target(robot.device.address)
        self.events.robot_disconnected.set(container, flags={'type': 'robot', 'id': robot.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_initialized(self, *args, **kwargs):

        if self.testbed_config.origin is not None:
            origin_config = from_dict_auto(BILBO_OriginConfig, self.testbed_config.origin)
            self.tracker.add_origin(origin_config.id, origin_config)

        if self.testbed_config.limbo_marker is not None:
            limbo_marker_config = from_dict_auto(BILBO_LimboMarkerConfig, self.testbed_config.limbo_marker)
            self.tracker.add_limbo_bar(limbo_marker_config.id, limbo_marker_config)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        self.events.new_tracker_sample.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_new_rigid_body(self, rigid_body: dict):
        self.logger.error(f"Received rigid body from OptiTrack: {rigid_body}. This is currently not supported. All "
                          f"rigid bodies need to be available before starting the application!")
