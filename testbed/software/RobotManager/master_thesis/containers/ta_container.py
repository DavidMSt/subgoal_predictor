from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer
from master_thesis.containers.task_container import TaskContainer

@dataclass(frozen=False, slots=True)
class AgentTAState:
    """Mutable runtime state for agent task execution"""

    # Available/known tasks (for decentralized decision making)
    available_tasks: list[TaskContainer] = field(default_factory=list)
    assignment_pending: bool = False

    # Task assignment
    assigned_task: TaskContainer| None = None 

    # Execution state - subgoal 
    #prediction
    waypoints: list[tuple[float, float]] | None = None
    current_waypoint_idx: int = 0
    
    # Local world representation
    local_obstacles: list = field(default_factory=list)  # agent's perception
    

@dataclass(frozen=True, slots=True)
class AgentTAConfig:
    """Immutable configuration for agent task management"""

    # Distance computation parameters
    distance_metric: str = 'euclidean'  # 'euclidean', 'manhattan', 'dubins', etc.

@dataclass(slots=True)
class AgentTAContainer(OverarchingContainer):
    config: AgentTAConfig = field(default_factory=AgentTAConfig)
    state: AgentTAState = field(default_factory=AgentTAState)
