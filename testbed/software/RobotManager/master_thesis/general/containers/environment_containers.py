from dataclasses import dataclass, field

from master_thesis.general.containers.base_container import OverarchingContainer
from master_thesis.general.containers.agent_containers import FRODOAgentContainer
from testbed.software.RobotManager.master_thesis.general.containers.obstacle_container import ObstacleContainer

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentState:
    obstacles: dict[str, ObstacleContainer] = field(default_factory=dict)
    agents: dict[str, FRODOAgentContainer] = field(default_factory=dict)

@dataclass(frozen= True, slots= True) # must be dynamically changeable since env can change
class EnvironmentConfig:
    limits: tuple[tuple[int, int], ...]
    Ts: float

@dataclass(frozen=False, slots = False)
class EnvironmentContainer(OverarchingContainer):
    config: EnvironmentConfig
    state: EnvironmentState = field(default_factory=EnvironmentState)

    def add_obstacles(self, obstacle):
        assert isinstance(obstacle, ObstacleContainer)
        self.state.obstacles[obstacle.object_id] = obstacle

    def remove_obstacles(self, obstacle_id):
        ...

    def add_agents(self, agent):
        assert isinstance(agent, FRODOAgentContainer)
        self.state.agents[agent.agent_id] = agent
    
    def remove_agents(self, agent_id):
        ...