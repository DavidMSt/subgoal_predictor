import dataclasses
from copy import copy

from core.utils.dataclass_utils import from_dict_auto, update_dataclass_from_dict
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from core.utils.uuid_utils import generate_uuid
from robots.bilbo.definitions import BoxObstacle_Config, BoxObstacle_State
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState


@event_definition
class VirtualTestbed_Events:
    new_bilbo: Event = Event(copy_data_on_set=False)
    bilbo_removed: Event = Event(copy_data_on_set=False)
    new_obstacle: Event = Event(copy_data_on_set=False)
    obstacle_removed: Event = Event(copy_data_on_set=False)


class SimulatedBILBO:

    def get_state(self) -> BILBO_DynamicState:
        return BILBO_DynamicState(x=0, y=0, v=0, theta=0, theta_dot=0, psi=0, psi_dot=0)


@dataclasses.dataclass
class SimulatedObstacle:
    pass


@dataclasses.dataclass(kw_only=True)
class SimulatedBoxObstacle(SimulatedObstacle):
    config: BoxObstacle_Config
    state: BoxObstacle_State

    # ------------------------------------------------------------------------------------------------------------------
    def set_state(self, x: float, y: float, psi: float):
        self.state.x = x
        self.state.y = y
        self.state.psi = psi

    # ------------------------------------------------------------------------------------------------------------------
    def get_payload(self) -> dict:
        payload = {
            'config': dataclasses.asdict(self.config),
            'state': dataclasses.asdict(self.state)
        }
        return payload


@dataclasses.dataclass
class VirtualTestbed_Config:
    enabled: bool = False
    Ts: float = 0.01
    obstacles: list[BoxObstacle_Config] | None = None
    robots: list | None = None


class VirtualTestbed:
    bilbos: dict[str, SimulatedBILBO]
    obstacles: dict[str, SimulatedObstacle]

    # === INIT =========================================================================================================
    def __init__(self, config: VirtualTestbed_Config | dict | None = None):
        if config is None:
            config = {}

        if isinstance(config, dict):
            config = from_dict_auto(VirtualTestbed_Config, config)

        self.config = config
        self.events = VirtualTestbed_Events()
        self.bilbos = {}
        self.obstacles = {}
        self.logger = Logger('Virtual Testbed', 'DEBUG')

    # === METHODS ======================================================================================================
    def init(self):
        # Add obstacles and BILBOs from config
        if self.config.obstacles is not None:
            for obstacle_config in self.config.obstacles:
                # Extract initial state from config if provided as YAML shorthand
                state = None
                if hasattr(obstacle_config, 'state') and obstacle_config.state is not None:
                    s = obstacle_config.state
                    if isinstance(s, (list, tuple)) and len(s) >= 2:
                        state = BoxObstacle_State(
                            x=float(s[0]),
                            y=float(s[1]),
                            psi=float(s[2]) if len(s) > 2 else 0
                        )
                self.add_box_obstacle(obstacle_config, state=state)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting Virtual Testbed")

    # ------------------------------------------------------------------------------------------------------------------
    def add_bilbo(self, id: str) -> SimulatedBILBO | None:
        if id in self.bilbos:
            self.logger.error(f"BILBO with ID {id} already exists!")
            return None

        self.logger.info(f"Added BILBO with ID {id}")
        self.bilbos[id] = SimulatedBILBO()
        self.events.new_bilbo.set(id)
        return self.bilbos[id]

    # ------------------------------------------------------------------------------------------------------------------
    def add_box_obstacle(self,
                         config: BoxObstacle_Config | dict | None = None,
                         state: BoxObstacle_State | None = None,
                         **kwargs) -> SimulatedObstacle | None:

        if config is None:
            config = {}

        if isinstance(config, dict):
            config = from_dict_auto(BoxObstacle_Config, config)

        update_dataclass_from_dict(config, kwargs)

        if state is None:
            state = BoxObstacle_State()

        update_dataclass_from_dict(state, kwargs)

        if config.id in self.obstacles:
            self.logger.error(f"Obstacle with ID {config.id} already exists!")
            return None

        self.logger.info(f"Added obstacle with ID {config.id}")
        self.obstacles[config.id] = SimulatedBoxObstacle(config=config, state=state)
        self.events.new_obstacle.set(self.obstacles[config.id])
        return self.obstacles[config.id]

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
