import dataclasses
import threading
import time

from applications.BILBO.tracker.bilbo_tracker import TrackedBILBO
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.geometry import is_point_in_rotated_rect
from core.utils.logging_utils import Logger


@dataclasses.dataclass
class BILBO_PhysicalObject:
    height: float  # in m
    width: float  # in m


@dataclasses.dataclass
class Obstacle:
    id: str
    position_x: float
    position_z: float


@callback_definition
class Testbed_Agent_Callbacks:
    collision: CallbackContainer
    in_target_zone: CallbackContainer


@dataclasses.dataclass
class Testbed_Agent:
    id: str

    optitrack: TrackedBILBO
    physical_object: BILBO_PhysicalObject

    obstacle_hit: bool = False
    in_target_zone: bool = False

    callbacks: Testbed_Agent_Callbacks = dataclasses.field(default_factory=Testbed_Agent_Callbacks)

    def reset(self):
        self.obstacle_hit = False
        self.in_target_zone = False


# ======================================================================================================================
@callback_definition
class BILBO_Testbed_Callbacks:
    collision: CallbackContainer
    in_target_zone: CallbackContainer


class BILBO_Testbed:
    obstacles: dict[str, Obstacle]
    agents: dict[str, Testbed_Agent]

    start_zone_x: list[float]
    target_zone_x: list[float]

    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO Testbed', 'DEBUG')
        self.callbacks = BILBO_Testbed_Callbacks()
        self.obstacles = {}
        self.agents = {}

        self._thread = threading.Thread(target=self._task, daemon=True)

    # === METHODS ======================================================================================================
    def start(self):
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def addObstacle(self, obstacle: Obstacle):
        if obstacle.id in self.obstacles:
            self.logger.error(f"Obstacle with id {obstacle.id} already exists")
            return

        if len(self.obstacles) > 0:
            raise NotImplementedError("Currently only one obstacle is supported.")

        self.obstacles[obstacle.id] = obstacle

    # ------------------------------------------------------------------------------------------------------------------
    def addAgent(self, agent: Testbed_Agent):
        if agent.id in self.agents:
            self.logger.error(f"Agent with id {agent.id} already exists")

        if len(self.agents) > 0:
            raise NotImplementedError("Currently only one agent is supported.")

        self.agents[agent.id] = agent

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        for agent in self.agents.values():
            agent.reset()

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        while not self._exit:
            self._update()
            time.sleep(0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def _update(self):
        any_agent_collided = False
        any_agent_in_target_zone = False

        for agent in self.agents.values():

            # Only update if the agent is not in collided state, because then it does not matter anymore
            if agent.obstacle_hit or agent.in_target_zone:
                continue

            # Check if the agent collided with an obstacle
            agent_collided = self._checkAgentCollision(agent)
            any_agent_collided = any_agent_collided or agent_collided

            # Check if the agent is in the target zone, but only if it did not collide
            if not agent_collided:
                agent_in_target_zone = self._checkAgentInTargetZone(agent)
                any_agent_in_target_zone = any_agent_in_target_zone or agent_in_target_zone

        if any_agent_collided:
            self.callbacks.collision.call()

        if any_agent_in_target_zone:
            self.callbacks.in_target_zone.call()

    # ------------------------------------------------------------------------------------------------------------------
    def _checkAgentCollision(self, agent: Testbed_Agent) -> bool:

        # Get the only obstacle we have
        obstacle = list(self.obstacles.values())[0]

        collision = is_point_in_rotated_rect(height=agent.physical_object.height,
                                             width=agent.physical_object.width,
                                             E=(agent.optitrack.state.x, agent.optitrack.state.z),
                                             F=(obstacle.position_x, obstacle.position_z),
                                             theta=agent.optitrack.state.theta)

        if collision:
            agent.obstacle_hit = True
            agent.callbacks.collision.call()
            return True
        else:
            return False

    # ------------------------------------------------------------------------------------------------------------------
    def _checkAgentInTargetZone(self, agent: Testbed_Agent) -> bool:
        if self.target_zone_x[0] < agent.optitrack.state.x < self.target_zone_x[1]:
            agent.in_target_zone = True
            return True
        else:
            return False
