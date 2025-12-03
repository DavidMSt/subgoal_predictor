from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer

# @dataclass(frozen= False, slots = False) #TODO obstacles are static, therefore strictly speaking 
# class Obstacle_State():
#     x: float
#     y: float
#     psi: float

@dataclass(frozen=True, slots=True)
class Obstacle_Config:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0
    length: float = 2.0
    width: float = 0.5
    height: float = 1.0
    shape: str = 'box'

@dataclass(frozen=False, slots = False)
class ObstacleContainer(OverarchingContainer):
    object_id: str = field(kw_only=True)
    config: Obstacle_Config = field(default_factory=Obstacle_Config)
    state: None = None
    
