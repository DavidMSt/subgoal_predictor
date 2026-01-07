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
from robots.bilbo.robot.bilbo_definitions import BILBO_OriginConfig


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


class BILBO_TestbedManager:
    robot_manager: BILBO_Manager
    tracker: BILBO_Tracker
    bilbos: dict[str, BILBO_TestbedAgent]
    extensions: BILBO_TestbedExtensions

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO Testbed Manager', 'DEBUG')
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
        self.robot_manager.init()
        self.joystick_control.init()
        self.tracker.init()

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
        # 1. Load the testbed config
        testbed_config_file = get_absolute_path('../configs/testbed.yaml')

        if not file_exists(testbed_config_file):
            self.logger.warning(f"Testbed config file '{testbed_config_file}' does not exist.")
            return

        with open(testbed_config_file, 'r') as file:
            testbed_config = yaml.safe_load(file)

        if testbed_config['origin'] is not None:
            origin_config = from_dict_auto(BILBO_OriginConfig, testbed_config['origin'])
            self.tracker.add_origin(origin_config.id, origin_config)
        else:
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        self.events.new_tracker_sample.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_new_rigid_body(self, rigid_body: dict):
        self.logger.error(f"Received rigid body from OptiTrack: {rigid_body}. This is currently not supported. All "
                          f"rigid bodies need to be available before starting the application!")
