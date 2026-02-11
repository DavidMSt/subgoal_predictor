import dataclasses

from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.uuid_utils import generate_uuid
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.paths import CONTROL_PATH
from robot.testbed.obstacles import Obstacle, CircleObstacle, BoxObstacle


@dataclasses.dataclass
class TestbedSize:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class TestbedConfig:
    """Configuration settings for the testbed environment.

    Attributes:
        id: Testbed identifier (e.g. 'track', 'lab'). Used to load a matching
            control config file (<id>.yaml) from the robot's control config folder.
        size: The physical dimensions of the testbed area.
    """
    size: TestbedSize
    id: str | None = None


@event_definition
class TestbedEvents:
    config_received: Event = Event(id='testbed_config_received')


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None


class BILBO_TestbedManager:
    testbed_config: TestbedConfig | None = None

    obstacles: list[Obstacle]

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, communication: BILBO_Communication, control: BILBO_Control):
        self.logger = Logger("Testbed Manager", "DEBUG")

        self.common = common
        self.communication = communication
        self.control = control
        self.events = TestbedEvents()
        self.obstacles = []
        self._register_wifi_commands()

    # === METHODS ======================================================================================================
    def set_testbed_config(self, config: TestbedConfig | dict):
        if isinstance(config, dict):
            config = from_dict_auto(TestbedConfig, config)

        self.testbed_config = config
        self.logger.info(f"Testbed config set to {config}")
        self.events.config_received.set(data=config)

        # Load testbed-specific control config if a matching file exists
        if config.id is not None:
            self._load_testbed_control_config(config.id)

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self):
        data = TestbedData(config=self.testbed_config)
        return data

    # ------------------------------------------------------------------------------------------------------------------
    def add_obstacle(self, type: str, config: dict | None):
        if config is None:
            config = {}
        match type:
            case 'circle':
                id = config.get('id', generate_uuid(prefix='circle_'))
                if id in [obstacle.id for obstacle in self.obstacles]:
                    self.logger.error(f"Obstacle with ID '{id}' already exists")
                    return
                circle = CircleObstacle(id=id, **config)
                self.obstacles.append(circle)
            case 'box':
                id = config.get('id', generate_uuid(prefix='box_'))
                if id in [obstacle.id for obstacle in self.obstacles]:
                    self.logger.error(f"Obstacle with ID '{id}' already exists")
                    return
                box = BoxObstacle(id=id, **config)
                self.obstacles.append(box)
            case _:
                raise ValueError(f"Unknown obstacle type '{type}'")

    # ------------------------------------------------------------------------------------------------------------------
    def remove_obstacle(self, obstacle_id: str):
        for obstacle in self.obstacles:
            if obstacle.id == obstacle_id:
                self.obstacles.remove(obstacle)
                return

    # ------------------------------------------------------------------------------------------------------------------
    def clear_obstacles(self):
        self.obstacles.clear()

    # ------------------------------------------------------------------------------------------------------------------
    def set_obstacle_state(self, obstacle_id: str, x: float, y: float, psi: float | None = None):
        obstacle = next((obstacle for obstacle in self.obstacles if obstacle.id == obstacle_id), None)
        if obstacle is not None:
            obstacle.set_state(x, y, psi)

    # === PRIVATE METHODS ==============================================================================================
    def _load_testbed_control_config(self, testbed_id: str):
        """Load and apply a control config matching the testbed ID.

        Looks for <testbed_id>.yaml in the robot's control config folder
        (e.g. ~/robot/control/lab.yaml). If found, loads and applies it.
        """
        config_file = f"{CONTROL_PATH}{testbed_id}.yaml"
        if not file_exists(config_file):
            self.logger.info(f"No testbed-specific control config found at '{config_file}', keeping current config")
            return

        self.logger.info(f"Loading testbed control config '{testbed_id}.yaml'")
        config = self.control.load_config(testbed_id)
        if config is None:
            self.logger.warning(f"Failed to load testbed control config '{testbed_id}.yaml'")
            return

        result = self.control.set_config(config)
        if not result:
            self.logger.warning(f"Failed to apply testbed control config '{testbed_id}.yaml'")
            return

        self.logger.info(f"Testbed control config '{testbed_id}.yaml' applied successfully")

    # ------------------------------------------------------------------------------------------------------------------
    def _register_wifi_commands(self):
        self.communication.wifi.newCommand(identifier='set_testbed_config',
                                           function=self.set_testbed_config,
                                           arguments=['config'],
                                           description='Sets the testbed configuration')

        self.communication.wifi.newCommand(identifier='add_obstacle',
                                           function=self.add_obstacle,
                                           arguments=['type',
                                                      'config'],
                                           description='Adds an obstacle to the testbed')

        self.communication.wifi.newCommand(identifier='remove_obstacle',
                                           function=self.remove_obstacle,
                                           arguments=['obstacle_id'],
                                           description='Removes an obstacle from the testbed')
        self.communication.wifi.newCommand(identifier='clear_obstacles',
                                           function=self.clear_obstacles,
                                           arguments=[],
                                           description='Clears all obstacles from the testbed')
        self.communication.wifi.newCommand(identifier='set_obstacle_state',
                                           function=self.set_obstacle_state,
                                           arguments=['obstacle_id', 'x', 'y', 'psi'],
                                           description='Sets the state of an obstacle')
