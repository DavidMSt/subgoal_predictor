from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer
from master_thesis.containers.task_container import TaskContainer

@dataclass(frozen=False, slots=True)
class AgentTAState:
    """Mutable runtime state for agent task execution"""
    
    # Available/known tasks (for decentralized decision making)
    available_tasks: list[TaskContainer] = field(default_factory=list)
    decentralized_planning: bool = False
    
    # Task assignment
    assigned_task: TaskContainer| None = None
    strategy: str = "HUNGARIAN" # TODO: Import the available strategies here? 

    # Execution state - subgoal 
    #prediction
    waypoints: list[tuple[float, float]] | None = None
    current_waypoint_idx: int = 0
    
    # Local world representation
    local_obstacles: list = field(default_factory=list)  # agent's perception
    

@dataclass(frozen=True, slots=True)
class AgentTAConfig:
    """Immutable configuration for agent task management"""
    # Decentralized assignment policy (if None, use simple greedy)
    # Examples: 'greedy_nearest', 'auction', 'gnn', etc.
    decentralized_policy: str | None = None

    # Distance computation parameters
    distance_metric: str = 'euclidean'  # 'euclidean', 'manhattan', etc.

    # Task selection parameters
    max_task_distance: float = 10.0
    task_preference_weight: float = 1.0

@dataclass(slots=True)
class AgentTAContainer(OverarchingContainer):
    config: AgentTAConfig
    state: AgentTAState
