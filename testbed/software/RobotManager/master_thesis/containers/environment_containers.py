from dataclasses import dataclass, field
import numpy as np

from master_thesis.containers.base_container import OverarchingContainer
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.obstacle_container import ObstacleContainer
from master_thesis.containers.task_container import TaskContainer

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentState:
    obstacle_conts: dict[str, ObstacleContainer] = field(default_factory=dict)
    agent_conts: dict[str, FRODOAgentContainer] = field(default_factory=dict)
    task_conts: dict[str, TaskContainer] = field(default_factory=dict)
    occupancy_grid_full: np.ndarray | None = None  # obstacles + agents + tasks (for spawning)
    occupancy_grid_static: np.ndarray | None = None  # obstacles only (for RL observations)
    entities_creation_frozen: bool = False  # locked after sim.start()

@dataclass(frozen= True, slots= True)
class EnvironmentConfig:
    limits: tuple[tuple[int, int], ...]
    Ts: float
    grid_resolution: float = 0.1  # 10cm grid cells
    grid_padding: float = 0.5  # extra space around workspace boundaries

@dataclass(frozen=False, slots = False)
class EnvironmentContainer(OverarchingContainer):
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