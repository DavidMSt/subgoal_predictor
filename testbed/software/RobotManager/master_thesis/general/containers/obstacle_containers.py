from dataclasses import dataclass
from master_thesis.general.containers.base_container import OverarchingContainer
from core.utils.states import State

@dataclass(frozen=True, slots=True)
class Obstacle_Config:
    x: float
    y: float
    psi: float
    length: float = 2.0
    width: float = 0.5
    height: float = 1.0

@dataclass(frozen= False, slots = False)
class Obstacle_State(State):
    ...

@dataclass(frozen=False, slots = False)
class ObstacleContainer(OverarchingContainer):
    config: Obstacle_Config
    state:  Obstacle_State

    def update(self):
        raise NotImplementedError("obstacles are currently thought of as static")