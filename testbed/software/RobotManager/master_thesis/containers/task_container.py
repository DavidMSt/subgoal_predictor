from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer


@dataclass(frozen=False, slots = False)
class TaskState:
    assigned_agent: str = ''
    priority: int = 0
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    is_assignable: bool = True

@dataclass(frozen=True, slots=True)
class Task_Config:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0
    goal_tolerance_xy: float = 0.15  # Position tolerance in meters (15cm radius)
    goal_tolerance_psi: float | None = None  # Orientation tolerance in radians (None = ignore orientation)
    temporary: bool = False # For RL-waypoint prediction we want to remove them later again

@dataclass(frozen=False, slots = False)
class TaskContainer(BaseContainer):
    object_id: str = field(kw_only=True)
    config: Task_Config = field(default_factory=Task_Config)
    state: TaskState = field(default_factory=TaskState)