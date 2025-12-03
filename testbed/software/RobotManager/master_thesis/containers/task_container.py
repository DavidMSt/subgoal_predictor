from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer


@dataclass(frozen=False, slots = False)
class TaskState:
    is_assigned: bool = False
    priority: int = 0
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    is_assignable: bool = True

@dataclass(frozen=True, slots=True)
class Task_Config:
    x: float = 0.0
    y: float = 0.0
    psi: float = 0.0

@dataclass(frozen=False, slots = False)
class TaskContainer(OverarchingContainer):
    object_id: str = field(kw_only=True)
    config: Task_Config = field(default_factory=Task_Config)
    state: TaskState = field(default_factory=TaskState)