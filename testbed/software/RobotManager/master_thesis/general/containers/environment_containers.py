from dataclasses import dataclass

from master_thesis.general.containers.base_container import OverarchingContainer
from master_thesis.general.containers.agent_containers import FRODOAgentContainer
from master_thesis.general.containers.obstacle_containers import ObstacleContainer

@dataclass(frozen= True, slots= True) # must be dynamically changeable since env can change
class EnvironmentConfig:
    limits: list[list[float]]
    Ts: float

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentState:
    obstacles: dict[str, ObstacleContainer]
    agents: dict[str, FRODOAgentContainer]

@dataclass(frozen=False, slots = False)
class EnvironmentContainer(OverarchingContainer):
    config: EnvironmentConfig
    state:  EnvironmentState

    def add_obstacles(self):
        ...

    def remove_obstacles(self):
        ...

    def add_agents(self):
        ...
    
    def remove_agents(self):
        ...