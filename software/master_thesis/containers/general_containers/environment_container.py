from dataclasses import dataclass, field
import numpy as np

from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.obstacle_container import ObstacleContainer
from master_thesis.containers.general_containers.task_container import TaskContainer

# ---------------------------------------------------------------------------
# EnvironmentState:
# Holds the complete *global* world state.
# This is the "true" world representation inside the simulator.
# - Obstacles (static or dynamic)
# - Agents (their true state containers)
# - Tasks
# - Occupancy grids (full + static)
#
# This state is written by the environment and the simulation,
# and read by:
# - collision checker
# - local world updater
# - spawning logic
# - task assignment / motion modules
# ---------------------------------------------------------------------------

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentState:
    obstacle_conts: dict[str, ObstacleContainer] = field(default_factory=dict)
    agent_conts: dict[str, FRODOAgentContainer] = field(default_factory=dict)
    task_conts: dict[str, TaskContainer] = field(default_factory=dict)
    occupancy_grid_full: np.ndarray | None = None  # obstacles + agents + tasks (for spawning)
    occupancy_grid_static: np.ndarray | None = None  # obstacles only (for RL observations)
    entities_creation_frozen: bool = False  # locked after sim.start()

#
# ---------------------------------------------------------------------------
# EnvironmentConfig:
# Stores global, static configuration of the environment.
# These parameters define the physics and resolution of the simulated world.
#
# - limits: workspace boundaries
# - Ts: simulation step size
# - grid_resolution: occupancy grid cell size
# - grid_padding: extra margin around limits for grid construction
# - agent_ranges: generic sensing range for all agents (if needed)
#
# This configuration is identical for all agents and
# remains constant during simulation.
# ---------------------------------------------------------------------------

@dataclass(frozen= True, slots= True)
class EnvironmentConfig:
    limits: tuple[tuple[int, int], ...]
    Ts: float
    grid_resolution: float = 0.1  # 10cm grid cells
    grid_padding: float = 0.5  # extra space around workspace boundaries

    # agent visibility ranges
    agent_range: float | None = None
    task_range: float| None = None
    obstacle_range: float | None = None


#
# ---------------------------------------------------------------------------
# EnvironmentContainer:
# High–level container combining:
#   - config  (static world definition)
#   - state   (dynamic world elements)
#
# This container is the central entry point for:
#   - adding/removing obstacles, agents, tasks
#   - accessing global state for updates
#   - providing world info to modules (TA, MP, EXE)
#
# It mirrors the overall world representation used by the simulation.
# ---------------------------------------------------------------------------

@dataclass(frozen=False, slots = False)
class EnvironmentContainer(BaseContainer):
    config: EnvironmentConfig  # No default - must be provided (requires limits and Ts)
    state: EnvironmentState = field(default_factory=EnvironmentState)

    def add_obstacles(self, obstacle):
        assert isinstance(obstacle, ObstacleContainer)
        self.state.obstacle_conts[obstacle.object_id] = obstacle

    def remove_obstacles(self, obstacle_id):
        ...

    def add_agents(self, agent):
        assert isinstance(agent, FRODOAgentContainer)
        self.state.agent_conts[agent.agent_id] = agent

    def remove_agents(self, agent_id):
        ...

    def add_tasks(self, task):
        assert isinstance(task, TaskContainer)
        self.state.task_conts[task.object_id] = task

    def remove_tasks(self, task_id):
        if task_id in self.state.task_conts:
            del self.state.task_conts[task_id]