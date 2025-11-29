from dataclasses import dataclass
from master_thesis.general.containers.base_container import OverarchingContainer
from core.utils.states import State

@dataclass(frozen= False, slots = False)
class Obstacle_State(State):
    x: float
    y: float
    psi: float

@dataclass(frozen=True, slots=True)
class Obstacle_Config:
    x0: float = 0.0
    y0: float = 0.0
    psi0: float = 0.0
    length: float = 2.0
    width: float = 0.5
    height: float = 1.0

@dataclass(frozen=False, slots = False)
class ObstacleContainer(OverarchingContainer):
    object_id: str
    config: Obstacle_Config
    
