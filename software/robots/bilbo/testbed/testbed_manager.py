import dataclasses
import os
import threading
import time

from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import Event, event_definition, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak
from extensions.cli.cli import CommandSet, Command, CommandArgument
from core.utils.timecode.timecode_server import TimecodeServer
from core.utils.yaml_utils import load_yaml
from robots.bilbo.definitions import BoxObstacle_Config, BoxObstacle_State, Line_Config, Point_Config, Pose_Config
from robots.bilbo.manager.bilbo_manager import BILBO_Manager
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from robots.bilbo.simulation.virtual_testbed import VirtualTestbed, SimulatedBoxObstacle, VirtualTestbed_Config
from robots.bilbo.testbed.devices.testbed_extensions import BILBO_TestbedExtensions
from robots.bilbo.testbed.objects import RealTestbedBILBO, VirtualTestbedBILBO, \
    RealBoxObstacle, VirtualTestbedBoxObstacle
from robots.bilbo.testbed.testbed import Testbed, TestbedConfig
from robots.bilbo.testbed.tracker.tracked_objects import Origin_OptiTrack_Config, LimboMarker_OptiTrack_Config, \
    BoxObstacle_OptiTrack_Config, WallObstacle_OptiTrack_Config
from robots.bilbo.testbed.tracker.tracked_objects import OptiTrackOutlierFilterConfig
from robots.bilbo.testbed.tracker.tracker import BILBO_Tracker, BILBO_Tracker_Config, BILBO_Tracker_Status

# Config directories
_CONFIGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'configs'))
_TRACKED_OBJECTS_DIR = os.path.join(_CONFIGS_DIR, 'tracked_objects')
_ROBOTS_DIR = os.path.join(_CONFIGS_DIR, 'robots')


def _resolve_config_from_file(name: str, directory: str, data_class):
    """Load a YAML config file and convert it to a dataclass instance."""
    path = os.path.join(directory, f'{name}.yaml')
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file for '{name}' not found: {path}")
    yaml_data = load_yaml(path)
    return from_dict_auto(data_class, yaml_data)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TestbedSettings:
    id: str | None = None  # ID of the testbed. Is used by the robots to set specific control configs
    size: dict[str, list[float]] | None = None
    obstacles: list[BoxObstacle_Config] | None = None
    lines: list[Line_Config] | None = None
    points: list[Point_Config] | None = None
    poses: list[Pose_Config] | None = None


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TrackerSettings:
    enabled: bool = True
    server: str = 'palantir.lan'
    sample_rate: int = 50
    outlier_filter: OptiTrackOutlierFilterConfig = dataclasses.field(default_factory=OptiTrackOutlierFilterConfig)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TrackedObjects:
    origin: Origin_OptiTrack_Config | None | str = None
    limbo_bar: LimboMarker_OptiTrack_Config | None | str = None
    boxes: list[BoxObstacle_OptiTrack_Config | str] | None = dataclasses.field(default_factory=list)
    walls: list[WallObstacle_OptiTrack_Config | str] | None = dataclasses.field(default_factory=list)
    robots: list[BILBO_Config | str] | None = dataclasses.field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.origin, str):
            self.origin = _resolve_config_from_file(self.origin, _TRACKED_OBJECTS_DIR, Origin_OptiTrack_Config)

        if isinstance(self.limbo_bar, str):
            self.limbo_bar = _resolve_config_from_file(self.limbo_bar, _TRACKED_OBJECTS_DIR, LimboMarker_OptiTrack_Config)

        self.boxes = [
            _resolve_config_from_file(box, _TRACKED_OBJECTS_DIR, BoxObstacle_OptiTrack_Config) if isinstance(box, str) else box
            for box in self.boxes
        ]

        self.walls = [
            _resolve_config_from_file(wall, _TRACKED_OBJECTS_DIR, WallObstacle_OptiTrack_Config) if isinstance(wall, str) else wall
            for wall in self.walls
        ]

        self.robots = [
            _resolve_config_from_file(robot, _ROBOTS_DIR, BILBO_Config) if isinstance(robot, str) else robot
            for robot in self.robots
        ]


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class ExtensionsSettings:
    timecode: bool = False
    limbobar: bool = True
    display: bool = True


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class RobotSettings:
    autostart: bool = False
    autostop: bool = False


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TestbedManagerSettings:
    testbed: TestbedSettings = dataclasses.field(default_factory=TestbedSettings)
    robots: RobotSettings = dataclasses.field(default_factory=RobotSettings)
    tracker: TrackerSettings = dataclasses.field(default_factory=TrackerSettings)
    tracked_objects: TrackedObjects = dataclasses.field(default_factory=TrackedObjects)
    extensions: ExtensionsSettings = dataclasses.field(default_factory=ExtensionsSettings)
    simulation: VirtualTestbed_Config = dataclasses.field(default_factory=VirtualTestbed_Config)


# ----------------------------------------------------------------------------------------------------------------------
@event_definition
class TestbedManagerEvents:
    new_bilbo: Event = Event(copy_data_on_set=False)
    bilbo_removed: Event = Event(copy_data_on_set=False)
    new_obstacle: Event = Event(copy_data_on_set=False)
    obstacle_removed: Event = Event(copy_data_on_set=False)

    new_robot: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    robot_disconnected: Event = Event(copy_data_on_set=False, flags=[EventFlag('type', str), EventFlag('id', str)])
    new_tracker_sample: Event
    initialized: Event = Event(copy_data_on_set=False)


# ----------------------------------------------------------------------------------------------------------------------
class TestbedManager:
    testbed: Testbed  # Combined testbed with real and virtual agents and objects

    # Sources
    tracker: BILBO_Tracker | None = None
    virtual_testbed: VirtualTestbed | None = None

    # Extensions
    extensions: BILBO_TestbedExtensions | None
    timecode_server: TimecodeServer | None

    # Robots
    robot_manager: BILBO_Manager

    # === INIT =========================================================================================================
    def __init__(self,
                 settings: TestbedManagerSettings | dict,
                 ):

        self.logger = Logger('BILBO Testbed Manager', 'DEBUG')

        if isinstance(settings, dict):
            settings = from_dict_auto(TestbedManagerSettings, settings)

        self.settings = settings
        self.events = TestbedManagerEvents()
        self.virtual_testbed = VirtualTestbed(settings.simulation)

        self.robot_manager = BILBO_Manager(enable_scanner=settings.robots.autostart,
                                           autostop_robots=settings.robots.autostop)

        if self.settings.tracker.enabled:
            self.tracker = BILBO_Tracker(BILBO_Tracker_Config(
                server=self.settings.tracker.server,
                max_sample_rate=self.settings.tracker.sample_rate,
                outlier_filter=self.settings.tracker.outlier_filter,
            ))
        else:
            self.tracker = None

        if self.settings.extensions.timecode:
            self.timecode_server = TimecodeServer()
        else:
            self.timecode_server = None

        if self.settings.extensions.limbobar or self.settings.extensions.display:
            self.extensions = BILBO_TestbedExtensions(
                use_limbobar=self.settings.extensions.limbobar,
                use_display=self.settings.extensions.display
            )
        else:
            self.extensions = None

        self.testbed = Testbed(config=self._build_testbed_config())
        self.cli = self._build_cli()

        self._running = False
        self._experiment_listeners: dict[str, list] = {}
        self._display_clear_timer: threading.Timer | None = None
        self._obstacle_sync_thread: threading.Thread | None = None
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self._register_events()
        self.robot_manager.init()
        self.virtual_testbed.init()
        self._load_obstacles_from_settings()

        if self.tracker is not None:
            self.tracker.init()

        self.events.initialized.set()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.robot_manager.start()
        self.virtual_testbed.start()
        if self.tracker is not None:
            self.tracker.start()
        if self.timecode_server is not None:
            self.timecode_server.start()
        if self.extensions is not None:
            self.extensions.start()

        self._running = True
        self._obstacle_sync_thread = threading.Thread(target=self._obstacle_sync_loop, daemon=True)
        self._obstacle_sync_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._running = False
        if self._obstacle_sync_thread is not None:
            self._obstacle_sync_thread.join(timeout=2)

    # ------------------------------------------------------------------------------------------------------------------
    def emergency_stop(self):
        self.robot_manager.emergencyStop()

    # === EVENT HANDLERS: ROBOT MANAGER ================================================================================
    def _on_new_robot(self, robot: BILBO):
        if robot.id in self.testbed.bilbos:
            self.logger.warning(f"Robot {robot.id} already exists.")
            return

        self.logger.info(f"New robot connected: {robot.id}")
        speak(f"Robot {robot.id} connected")

        # Get the tracked object for this robot
        tracked_object = None
        if self.tracker is not None:
            if self.tracker.status != BILBO_Tracker_Status.RUNNING:
                self.logger.warning(f"Tracker is not running, cannot get optitrack data for robot {robot.id}")
            else:
                tracked_object = self.tracker.add_robot(robot.id, robot.config)
                if tracked_object is None:
                    self.logger.warning(f"OptiTrack is running, but robot {robot.id} does not exist in tracker")

        testbed_bilbo = RealTestbedBILBO(
            id=robot.id,
            robot=robot,
            tracked_object=tracked_object,
            config=robot.config
        )

        if self.timecode_server is not None:
            self.timecode_server.add_target(robot.device.address)

        self._send_testbed_config_to_robot(robot)
        self._sync_obstacles_to_robot(robot)

        self.testbed.add_bilbo(testbed_bilbo)
        self.events.new_bilbo.set(testbed_bilbo)

        # Listen for experiment events to show status on testbed display
        listeners = [
            robot.experiment_handler.events.experiment_started.on(self._on_experiment_started, discard_match_data=False),
            robot.experiment_handler.events.experiment_finished.on(self._on_experiment_finished),
            robot.experiment_handler.events.experiment_error.on(self._on_experiment_finished),
            robot.experiment_handler.events.experiment_timeout.on(self._on_experiment_finished),
        ]
        self._experiment_listeners[robot.id] = listeners

    # ------------------------------------------------------------------------------------------------------------------
    def _on_robot_disconnected(self, robot: BILBO):
        self.logger.info(f"Robot disconnected: {robot.id}")
        speak(f"Robot {robot.id} disconnected")

        if robot.id not in self.testbed.bilbos:
            self.logger.warning(f"Robot {robot.id} does not exist in testbed")
            return

        if robot.id in self._experiment_listeners:
            for listener in self._experiment_listeners.pop(robot.id):
                listener.stop()

        self.testbed.remove_bilbo(robot.id)

        if self.tracker is not None:
            self.tracker.remove_robot(robot.id)

        if self.timecode_server is not None:
            self.timecode_server.remove_target(robot.device.address)

        self.events.bilbo_removed.set(robot.id)
        self.events.robot_disconnected.set(robot, flags={'type': 'robot', 'id': robot.id})

    # === EVENT HANDLERS: EXPERIMENTS ==================================================================================
    def _on_experiment_started(self, data, match):
        if self.extensions is not None and self.extensions.display is not None:
            if self._display_clear_timer is not None:
                self._display_clear_timer.cancel()
                self._display_clear_timer = None
            experiment_label = match.flags.get('experiment_label') or match.flags.get('experiment_id', '')
            self.extensions.display.set_title(experiment_label)
            self.extensions.display.start_clock(mode='replace_text')

    def _on_experiment_finished(self, data, *args, **kwargs):
        if self.extensions is not None and self.extensions.display is not None:
            self.extensions.display.stop_clock()
            if self._display_clear_timer is not None:
                self._display_clear_timer.cancel()
            self._display_clear_timer = threading.Timer(5.0, self.extensions.display.clear)
            self._display_clear_timer.daemon = True
            self._display_clear_timer.start()

    # === EVENT HANDLERS: TRACKER ======================================================================================
    def _on_tracker_initialized(self, *args, **kwargs):
        if self.settings.tracked_objects.origin is not None:
            self.tracker.add_origin(self.settings.tracked_objects.origin.id, self.settings.tracked_objects.origin)

        if self.settings.tracked_objects.limbo_bar is not None:
            self.tracker.add_limbo_bar(self.settings.tracked_objects.limbo_bar.id,
                                       self.settings.tracked_objects.limbo_bar)

        if self.settings.tracked_objects.boxes is not None and isinstance(self.settings.tracked_objects.boxes, list):
            for box_tracking_config in self.settings.tracked_objects.boxes:
                tracked_box = self.tracker.add_obstacle(box_tracking_config.id, box_tracking_config)
                if tracked_box is not None:
                    # Look up obstacle dimensions from testbed config by matching ID
                    obstacle_config = self._get_obstacle_config_by_id(box_tracking_config.id)
                    if obstacle_config is not None:
                        real_obstacle = RealBoxObstacle(
                            id=box_tracking_config.id,
                            config=obstacle_config,
                            tracked_object=tracked_box
                        )
                        self.testbed.add_obstacle(real_obstacle)
                        self.events.new_obstacle.set(real_obstacle)
                    else:
                        self.logger.warning(
                            f"Tracked box {box_tracking_config.id} has no matching obstacle config with dimensions")

        if self.settings.tracked_objects.walls is not None and isinstance(self.settings.tracked_objects.walls, list):
            for wall in self.settings.tracked_objects.walls:
                self.tracker.add_wall(wall.id, wall)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_tracker_sample(self, *args, **kwargs):
        self.testbed.update()
        self.events.new_tracker_sample.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_tracker_new_rigid_body(self, rigid_body, *args, **kwargs):
        self.logger.warning(f"Dynamically adding rigid body {rigid_body} to testbed is not yet supported!")

    # === EVENT HANDLERS: VIRTUAL TESTBED ==============================================================================
    def _on_virtual_new_bilbo(self, bilbo_id, *args, **kwargs):
        if bilbo_id in self.testbed.bilbos:
            self.logger.warning(f"Simulated BILBO {bilbo_id} already exists in testbed")
            return

        sim_bilbo = self.virtual_testbed.bilbos.get(bilbo_id)
        if sim_bilbo is None:
            self.logger.error(f"Simulated BILBO {bilbo_id} not found in virtual testbed")
            return

        testbed_bilbo = VirtualTestbedBILBO(
            id=bilbo_id,
            simulation_object=sim_bilbo,
            config=None
        )

        self.testbed.add_bilbo(testbed_bilbo)
        self.events.new_bilbo.set(testbed_bilbo)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_virtual_new_obstacle(self, sim_obstacle: SimulatedBoxObstacle, *args, **kwargs):
        if not isinstance(sim_obstacle, SimulatedBoxObstacle):
            self.logger.warning(f"Unsupported simulated obstacle type: {type(sim_obstacle).__name__}")
            return

        obstacle_id = sim_obstacle.config.id
        if obstacle_id in self.testbed.obstacles:
            self.logger.warning(f"Simulated obstacle {obstacle_id} already exists in testbed")
            return

        virtual_obstacle = VirtualTestbedBoxObstacle(
            id=obstacle_id,
            config=sim_obstacle.config,
            simulation_object=sim_obstacle
        )

        self.testbed.add_obstacle(virtual_obstacle)
        self.events.new_obstacle.set(virtual_obstacle)
        self._sync_obstacles_to_robots()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_virtual_bilbo_removed(self, bilbo_id, *args, **kwargs):
        if bilbo_id in self.testbed.bilbos:
            self.testbed.remove_bilbo(bilbo_id)
            self.events.bilbo_removed.set(bilbo_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_virtual_obstacle_removed(self, obstacle_id, *args, **kwargs):
        if obstacle_id in self.testbed.obstacles:
            self.testbed.remove_obstacle(obstacle_id)
            self.events.obstacle_removed.set(obstacle_id)
            self._sync_obstacles_to_robots()

    # === CLI ==========================================================================================================
    def _build_cli(self) -> CommandSet:
        """Build the 'testbed' command set for obstacle management."""

        add_box_command = Command(
            name='addBox',
            function=self._cli_add_box,
            description='Add a box obstacle to the virtual testbed',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='Center X [m]'),
                CommandArgument(name='y', type=float, description='Center Y [m]'),
                CommandArgument(name='width', short_name='w', type=float, description='Width [m]'),
                CommandArgument(name='height', short_name='h', type=float, description='Height [m]'),
                CommandArgument(name='psi', short_name='p', type=float, optional=True, default=0.0,
                                description='Orientation [rad]'),
                CommandArgument(name='id', short_name='i', type=str, optional=True, default='',
                                description='Obstacle ID (auto-generated if empty)'),
            ]
        )

        remove_command = Command(
            name='remove',
            function=self._cli_remove_obstacle,
            description='Remove an obstacle by ID',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='id', type=str, description='Obstacle ID to remove'),
            ]
        )

        clear_command = Command(
            name='clearAll',
            function=self._cli_clear_obstacles,
            description='Remove all virtual obstacles',
            arguments=[]
        )

        list_command = Command(
            name='list',
            function=self._cli_list_obstacles,
            description='List all obstacles',
            arguments=[]
        )

        set_state_command = Command(
            name='setState',
            function=self._cli_set_state,
            description='Change obstacle position/orientation',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='id', type=str, description='Obstacle ID'),
                CommandArgument(name='x', type=float, description='New X [m]'),
                CommandArgument(name='y', type=float, description='New Y [m]'),
                CommandArgument(name='psi', short_name='p', type=float, optional=True, default=None,
                                description='New orientation [rad]'),
            ]
        )

        run_final_command = Command(
            name='runFinal',
            function=self._cli_run_final,
            description='Run the Boppard final experiments on all three robots (staggered start)',
            arguments=[],
            execute_in_thread=True,
        )

        return CommandSet(
            name='testbed',
            commands=[add_box_command, remove_command, clear_command, list_command, set_state_command,
                      run_final_command]
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _cli_add_box(self, x: float, y: float, width: float, height: float,
                     psi: float = 0.0, id: str = ''):
        if not id:
            idx = 1
            while f"box_obstacle_{idx}" in self.virtual_testbed.obstacles:
                idx += 1
            id = f"box_obstacle_{idx}"
        config = BoxObstacle_Config(id=id, width=width, height=height)
        state = BoxObstacle_State(x=x, y=y, psi=psi)
        result = self.virtual_testbed.add_box_obstacle(config=config, state=state)
        if result:
            self.logger.info(f"Added box obstacle '{config.id}' at ({x:.2f}, {y:.2f}) "
                             f"{width:.2f}x{height:.2f} psi={psi:.2f}")
        else:
            self.logger.error("Failed to add box obstacle")

    def _cli_remove_obstacle(self, id: str):
        if id in self.virtual_testbed.obstacles:
            del self.virtual_testbed.obstacles[id]
            self.virtual_testbed.events.obstacle_removed.set(id)
            self.logger.info(f"Removed obstacle '{id}'")
        else:
            self.logger.error(f"Obstacle '{id}' not found in virtual testbed")

    def _cli_clear_obstacles(self):
        obstacle_ids = list(self.virtual_testbed.obstacles.keys())
        for obs_id in obstacle_ids:
            del self.virtual_testbed.obstacles[obs_id]
            self.virtual_testbed.events.obstacle_removed.set(obs_id)
        self.logger.info(f"Cleared {len(obstacle_ids)} obstacles")

    def _cli_list_obstacles(self):
        all_obstacles = self.testbed.obstacles
        if not all_obstacles:
            self.logger.info("No obstacles")
            return
        self.logger.info(f"Obstacles ({len(all_obstacles)}):")
        for obs_id, obs in all_obstacles.items():
            d = obs.to_dict()
            self.logger.info(f"  [{d['id']}] Box at ({d['x']:.2f}, {d['y']:.2f}) "
                             f"{d['width']:.2f}x{d['height']:.2f} psi={d.get('psi', 0):.2f}")

    def _cli_set_state(self, id: str, x: float, y: float, psi: float = None):
        if id not in self.virtual_testbed.obstacles:
            self.logger.error(f"Obstacle '{id}' not found in virtual testbed")
            return
        sim_obstacle = self.virtual_testbed.obstacles[id]
        sim_obstacle.set_state(x=x, y=y, psi=psi if psi is not None else sim_obstacle.state.psi)
        self.logger.info(f"Updated obstacle '{id}' to ({x:.2f}, {y:.2f})")

    def _cli_run_final(self):
        from research.Boppard_2026.experiments.final.run_final import run_final
        self.logger.info("Starting Boppard final experiments...")
        run_final(self)

    # === OBSTACLE SYNCING =============================================================================================
    def _sync_obstacles_to_robot(self, robot: BILBO):
        """Send the current obstacle, line, point, and pose lists to a single robot."""
        device = robot.device

        device.executeFunction('clear_obstacles', arguments={})
        for obs in self.testbed.obstacles.values():
            d = obs.to_dict()
            obs_type = d.pop('type', 'box')
            device.executeFunction('add_obstacle',
                                   arguments={'type': obs_type, 'config': d})

        device.executeFunction('clear_lines', arguments={})
        for line in self.testbed.lines.values():
            device.executeFunction('add_line',
                                   arguments={'config': dataclasses.asdict(line)})

        device.executeFunction('clear_points', arguments={})
        for point in self.testbed.points.values():
            device.executeFunction('add_point',
                                   arguments={'config': dataclasses.asdict(point)})

        device.executeFunction('clear_poses', arguments={})
        for pose in self.testbed.poses.values():
            device.executeFunction('add_pose',
                                   arguments={'config': dataclasses.asdict(pose)})

    # ------------------------------------------------------------------------------------------------------------------
    def _sync_obstacles_to_robots(self):
        """Send the current obstacle list to all connected robots via their TestbedManager."""
        for bilbo_id, testbed_bilbo in self.testbed.bilbos.items():
            if isinstance(testbed_bilbo, RealTestbedBILBO):
                self._sync_obstacles_to_robot(testbed_bilbo.robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _sync_obstacle_states_to_robots(self):
        """Send current obstacle positions to all connected robots."""
        if not self.testbed.obstacles:
            return
        states = {}
        for obs_id, obs in self.testbed.obstacles.items():
            s = obs.state
            states[obs_id] = {'x': s.x, 'y': s.y, 'psi': s.psi}
        for bilbo_id, testbed_bilbo in self.testbed.bilbos.items():
            if isinstance(testbed_bilbo, RealTestbedBILBO):
                testbed_bilbo.robot.device.executeFunction(
                    'update_obstacle_states', arguments={'states': states})

    # ------------------------------------------------------------------------------------------------------------------
    def _obstacle_sync_loop(self):
        """Background thread: push obstacle states to robots at a fixed rate."""
        interval = 1.0 / 5  # 5 Hz
        while self._running:
            try:
                self._sync_obstacle_states_to_robots()
            except Exception as e:
                self.logger.warning(f"Obstacle state sync error: {e}")
            time.sleep(interval)

    # === PRIVATE METHODS ==============================================================================================
    def _load_obstacles_from_settings(self):
        """Load obstacles, lines, and points from testbed settings into the testbed."""
        ts = self.settings.testbed

        # Load obstacles into virtual testbed (which bridges them to testbed via events)
        if ts.obstacles:
            for obstacle_config in ts.obstacles:
                state = None
                if hasattr(obstacle_config, 'state') and obstacle_config.state is not None:
                    s = obstacle_config.state
                    if isinstance(s, (list, tuple)) and len(s) >= 2:
                        state = BoxObstacle_State(
                            x=float(s[0]),
                            y=float(s[1]),
                            psi=float(s[2]) if len(s) > 2 else 0
                        )
                self.virtual_testbed.add_box_obstacle(obstacle_config, state=state)

        # Load lines directly into testbed
        if ts.lines:
            for line_config in ts.lines:
                self.testbed.add_line(line_config)

        # Load points directly into testbed
        if ts.points:
            for point_config in ts.points:
                self.testbed.add_point(point_config)

        # Load poses directly into testbed
        if ts.poses:
            for pose_config in ts.poses:
                self.testbed.add_pose(pose_config)

    # ------------------------------------------------------------------------------------------------------------------
    def _build_testbed_config(self) -> TestbedConfig | None:
        """Convert testbed settings (from application YAML) into a TestbedConfig."""
        ts = self.settings.testbed
        if ts is None or ts.size is None:
            return None
        from robots.bilbo.testbed.testbed import TestbedSize
        return TestbedConfig(
            id=ts.id,
            size=TestbedSize(
                x_min=ts.size['x'][0],
                x_max=ts.size['x'][1],
                y_min=ts.size['y'][0],
                y_max=ts.size['y'][1],
            )
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _send_testbed_config_to_robot(self, robot: BILBO):
        """Send the testbed config (size + obstacles) to a robot."""
        config = self.testbed.get_config()
        if not config:
            return
        robot.device.executeFunction('set_testbed_config', arguments={'config': config})
        self.logger.info(f"Sent testbed config to robot {robot.id}")

    # ------------------------------------------------------------------------------------------------------------------
    def _get_obstacle_config_by_id(self, obstacle_id: str) -> BoxObstacle_Config | None:
        """Look up obstacle dimensions from testbed settings by ID."""
        obstacles = self.settings.testbed.obstacles
        if not obstacles:
            return None
        for obs_config in obstacles:
            obs_id = obs_config.get('id') if isinstance(obs_config, dict) else getattr(obs_config, 'id', None)
            if obs_id == obstacle_id:
                if isinstance(obs_config, dict):
                    return from_dict_auto(BoxObstacle_Config, obs_config)
                return obs_config
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _register_events(self):
        # Robot Manager
        self.robot_manager.events.new_robot.on(self._on_new_robot)
        self.robot_manager.events.robot_disconnected.on(self._on_robot_disconnected)

        # Tracker
        if self.tracker is not None:
            self.tracker.events.new_sample.on(self._on_new_tracker_sample, max_rate=30)
            self.tracker.events.description_received.on(self._on_tracker_initialized, once=True)
            self.tracker.events.new_rigid_body.on(self._on_tracker_new_rigid_body)

        # Virtual Testbed
        if self.virtual_testbed is not None:
            self.virtual_testbed.events.new_bilbo.on(self._on_virtual_new_bilbo)
            self.virtual_testbed.events.bilbo_removed.on(self._on_virtual_bilbo_removed)
            self.virtual_testbed.events.new_obstacle.on(self._on_virtual_new_obstacle)
            self.virtual_testbed.events.obstacle_removed.on(self._on_virtual_obstacle_removed)
