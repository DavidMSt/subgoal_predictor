import dataclasses

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent,
)
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.uuid_utils import generate_uuid
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.paths import CONTROL_PATH
from robot.testbed.obstacles import Obstacle, CircleObstacle, BoxObstacle, LimboBar, LimboBarGeometry, \
    Line, Point, Pose


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
    limbo_bar_hit: Event = Event(id='limbo_bar_hit')


@wifi_event_definition
class TestbedWifiEvents(WifiEventContainer):
    limbo_bar_hit: WifiEvent = WifiEvent(data_type=dict)


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None


class BILBO_TestbedManager:
    testbed_config: TestbedConfig | None = None

    obstacles: list[Obstacle]
    lines: list[Line]
    points: list[Point]
    poses: list[Pose]
    limbo_bars: list[LimboBar]

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, communication: BILBO_Communication, control: BILBO_Control):
        self.logger = Logger("Testbed Manager", "DEBUG")

        self.common = common
        self.communication = communication
        self.control = control
        self.events = TestbedEvents()
        self.wifi_events = TestbedWifiEvents(wifi=communication.wifi.wifi, id='testbed')
        self.obstacles = []
        self.lines = []
        self.points = []
        self.poses = []
        self.limbo_bars = []
        self._register_wifi_commands()

        # Subscribe to the SPI sample batch to check limbo bar collisions at 100 Hz
        self.communication.spi.callbacks.rx_samples.register(self._on_sample_batch)

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

    # --- OBSTACLES ----------------------------------------------------------------------------------------------------
    def add_obstacle(self, type: str, config: dict | None):
        if config is None:
            config = {}
        # Extract id separately; strip 'id' and 'type' before unpacking into dataclass
        obs_id = config.get('id')
        kwargs = {k: v for k, v in config.items() if k not in ('id', 'type')}
        match type:
            case 'circle':
                obs_id = obs_id or generate_uuid(prefix='circle_')
                if obs_id in [obstacle.id for obstacle in self.obstacles]:
                    self.logger.error(f"Obstacle with ID '{obs_id}' already exists")
                    return
                self.obstacles.append(CircleObstacle(id=obs_id, **kwargs))
            case 'box':
                obs_id = obs_id or generate_uuid(prefix='box_')
                if obs_id in [obstacle.id for obstacle in self.obstacles]:
                    self.logger.error(f"Obstacle with ID '{obs_id}' already exists")
                    return
                self.obstacles.append(BoxObstacle(id=obs_id, **kwargs))
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

    # ------------------------------------------------------------------------------------------------------------------
    def update_obstacle_states(self, states: dict):
        """Batch-update obstacle positions.

        Args:
            states: Mapping of obstacle_id to state dict, e.g.
                    {'box1': {'x': 1.0, 'y': 2.0, 'psi': 0.5}, ...}
                    The 'psi' key is optional per entry.
        """
        obstacle_map = {obs.id: obs for obs in self.obstacles}
        for obstacle_id, state in states.items():
            obs = obstacle_map.get(obstacle_id)
            if obs is not None:
                obs.set_state(x=float(state['x']), y=float(state['y']),
                              psi=float(state['psi']) if 'psi' in state else None)

    # --- LINES --------------------------------------------------------------------------------------------------------
    def add_line(self, config: dict):
        line_id = config.get('id') or generate_uuid(prefix='line_')
        if line_id in [l.id for l in self.lines]:
            self.logger.error(f"Line with ID '{line_id}' already exists")
            return
        self.lines.append(Line(
            id=line_id,
            start=config.get('start', [0, 0]),
            end=config.get('end', [0, 0]),
        ))

    def remove_line(self, line_id: str):
        for line in self.lines:
            if line.id == line_id:
                self.lines.remove(line)
                return

    def clear_lines(self):
        self.lines.clear()

    # --- POINTS -------------------------------------------------------------------------------------------------------
    def add_point(self, config: dict):
        point_id = config.get('id') or generate_uuid(prefix='point_')
        if point_id in [p.id for p in self.points]:
            self.logger.error(f"Point with ID '{point_id}' already exists")
            return
        self.points.append(Point(
            id=point_id,
            position=config.get('position', [0, 0]),
        ))

    def remove_point(self, point_id: str):
        for point in self.points:
            if point.id == point_id:
                self.points.remove(point)
                return

    def clear_points(self):
        self.points.clear()

    # --- POSES --------------------------------------------------------------------------------------------------------
    def add_pose(self, config: dict):
        pose_id = config.get('id') or generate_uuid(prefix='pose_')
        if pose_id in [p.id for p in self.poses]:
            self.logger.error(f"Pose with ID '{pose_id}' already exists")
            return
        self.poses.append(Pose(
            id=pose_id,
            x=float(config.get('x', 0)),
            y=float(config.get('y', 0)),
            psi=float(config.get('psi', 0)),
        ))

    def remove_pose(self, pose_id: str):
        for pose in self.poses:
            if pose.id == pose_id:
                self.poses.remove(pose)
                return

    def clear_poses(self):
        self.poses.clear()

    # --- LIMBO BARS ---------------------------------------------------------------------------------------------------
    def add_limbo_bar(self, config: dict) -> str:
        bar_id = config.get('id') or generate_uuid(prefix='limbo_')
        if bar_id in [bar.id for bar in self.limbo_bars]:
            self.logger.error(f"Limbo bar with ID '{bar_id}' already exists")
            return bar_id
        geometry_data = {k: v for k, v in config.items() if k not in ('id',)}
        geometry = from_dict_auto(LimboBarGeometry, geometry_data)
        bar = LimboBar(id=bar_id, geometry=geometry)
        self.limbo_bars.append(bar)
        self.logger.info(f"Added limbo bar '{bar_id}': height={geometry.height}")
        return bar_id

    # ------------------------------------------------------------------------------------------------------------------
    def remove_limbo_bar(self, bar_id: str):
        for bar in self.limbo_bars:
            if bar.id == bar_id:
                self.limbo_bars.remove(bar)
                self.logger.info(f"Removed limbo bar '{bar_id}'")
                return

    # ------------------------------------------------------------------------------------------------------------------
    def clear_limbo_bars(self):
        self.limbo_bars.clear()
        self.logger.info("Cleared all limbo bars")

    # ------------------------------------------------------------------------------------------------------------------
    def reset_limbo_bars(self):
        for bar in self.limbo_bars:
            bar.reset()

    # ------------------------------------------------------------------------------------------------------------------
    def get_limbo_bar_states(self) -> dict:
        return {bar.id: {'hit': bar.hit} for bar in self.limbo_bars}

    # ------------------------------------------------------------------------------------------------------------------
    def update_limbo_bar(self, bar_id: str, config: dict):
        bar = next((b for b in self.limbo_bars if b.id == bar_id), None)
        if bar is None:
            self.logger.error(f"Limbo bar '{bar_id}' not found")
            return
        geometry_data = {k: v for k, v in config.items() if k not in ('id',)}
        bar.geometry = from_dict_auto(LimboBarGeometry, geometry_data)

    # === PRIVATE METHODS ==============================================================================================
    def _on_sample_batch(self, samples: list[dict]):
        """Called with each batch of ~10 LL samples from the SPI.
        Checks every sample in the batch against all limbo bars so that
        brief collisions lasting only 2-3 ticks are not missed."""
        if not self.limbo_bars:
            return

        config = self.common.config
        for sample in samples:
            est = sample['estimation']['state']
            x, y = est['x'], est['y']
            theta, psi = est['theta'], est['psi']
            for bar in self.limbo_bars:
                was_hit = bar.hit
                bar.update(x, y, theta, psi, config)
                if bar.hit and not was_hit:
                    self.logger.info(f"Limbo bar '{bar.id}' hit!")
                    self.events.limbo_bar_hit.set(data={'bar_id': bar.id})
                    self.wifi_events.limbo_bar_hit.send(data={'bar_id': bar.id})

    # ------------------------------------------------------------------------------------------------------------------
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

        self.communication.wifi.newCommand(identifier='update_obstacle_states',
                                           function=self.update_obstacle_states,
                                           arguments=['states'],
                                           description='Batch-update obstacle states: {id: {x, y, psi}, ...}')

        # Line commands
        self.communication.wifi.newCommand(identifier='add_line',
                                           function=self.add_line,
                                           arguments=['config'],
                                           description='Adds a line: {id, start: [x,y], end: [x,y]}')

        self.communication.wifi.newCommand(identifier='remove_line',
                                           function=self.remove_line,
                                           arguments=['line_id'],
                                           description='Removes a line by ID')

        self.communication.wifi.newCommand(identifier='clear_lines',
                                           function=self.clear_lines,
                                           arguments=[],
                                           description='Removes all lines')

        # Point commands
        self.communication.wifi.newCommand(identifier='add_point',
                                           function=self.add_point,
                                           arguments=['config'],
                                           description='Adds a point: {id, position: [x,y]}')

        self.communication.wifi.newCommand(identifier='remove_point',
                                           function=self.remove_point,
                                           arguments=['point_id'],
                                           description='Removes a point by ID')

        self.communication.wifi.newCommand(identifier='clear_points',
                                           function=self.clear_points,
                                           arguments=[],
                                           description='Removes all points')

        # Pose commands
        self.communication.wifi.newCommand(identifier='add_pose',
                                           function=self.add_pose,
                                           arguments=['config'],
                                           description='Adds a pose: {id, x, y, psi}')

        self.communication.wifi.newCommand(identifier='remove_pose',
                                           function=self.remove_pose,
                                           arguments=['pose_id'],
                                           description='Removes a pose by ID')

        self.communication.wifi.newCommand(identifier='clear_poses',
                                           function=self.clear_poses,
                                           arguments=[],
                                           description='Removes all poses')

        # Limbo bar commands
        self.communication.wifi.newCommand(identifier='add_limbo_bar',
                                           function=self.add_limbo_bar,
                                           arguments=['config'],
                                           description='Adds a limbo bar: {start_x, end_x, start_y, end_y, height, [id]}')

        self.communication.wifi.newCommand(identifier='remove_limbo_bar',
                                           function=self.remove_limbo_bar,
                                           arguments=['bar_id'],
                                           description='Removes a limbo bar by ID')

        self.communication.wifi.newCommand(identifier='clear_limbo_bars',
                                           function=self.clear_limbo_bars,
                                           arguments=[],
                                           description='Removes all limbo bars')

        self.communication.wifi.newCommand(identifier='reset_limbo_bars',
                                           function=self.reset_limbo_bars,
                                           arguments=[],
                                           description='Resets hit state on all limbo bars')

        self.communication.wifi.newCommand(identifier='get_limbo_bar_states',
                                           function=self.get_limbo_bar_states,
                                           arguments=[],
                                           description='Returns hit state of all limbo bars')

        self.communication.wifi.newCommand(identifier='update_limbo_bar',
                                           function=self.update_limbo_bar,
                                           arguments=['bar_id', 'config'],
                                           description='Updates geometry of a limbo bar')
