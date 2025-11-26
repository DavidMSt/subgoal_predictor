from dataclasses import dataclass

from master_thesis.general.containers.base_container import OverarchingContainer

@dataclass(frozen= True, slots= True) # must be dynamically changeable since env can change
class EnvironmentConfig:
    limits: list[list[float]]
    Ts: float

@dataclass(frozen= False, slots= False) # must be dynamically changeable since env can change
class EnvironmentState:
    obstacles: list[]
    agents: list[dict]

@dataclass(frozen=False, slots = False)
class EnvironmentContainer(OverarchingContainer):
    config: EnvironmentConfig
    state:  EnvironmentState