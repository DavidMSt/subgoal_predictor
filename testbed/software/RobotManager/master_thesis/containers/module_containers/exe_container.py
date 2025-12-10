from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer

@dataclass(frozen=False, slots = False)
class ExecutionState:
    waypoints: list[tuple[float, float]] | None = None
    current_waypoint_idx: int = 0
    
@dataclass(frozen=True, slots=True)
class Execution_Config:
    ...

@dataclass(frozen=False, slots = False)
class ExecutionContainer(BaseContainer):
    config: Execution_Config = field(default_factory=Execution_Config)
    state: ExecutionState = field(default_factory=ExecutionState)