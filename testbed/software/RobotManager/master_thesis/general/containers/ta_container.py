from dataclasses import dataclass, field
from master_thesis.general.containers.base_container import OverarchingContainer

@dataclass(frozen=True, slots=True)
class AgentTaskConfig:
    """Immutable configuration for agent task management"""
    # Decentralized assignment policy (if None, use simple greedy)
    # Examples: 'greedy_nearest', 'auction', 'gnn', etc.
    decentralized_policy: str | None = None

    # Distance computation parameters
    distance_metric: str = 'euclidean'  # 'euclidean', 'manhattan', etc.

    # Task selection parameters
    max_task_distance: float = 10.0
    task_preference_weight: float = 1.0

@dataclass(frozen=False, slots=True)
class AgentTaskState:
    """Mutable runtime state for agent task execution"""
    # Task assignment
    assigned_tasks: list[str] = field(default_factory=list)  # queue of task_ids
    current_task_id: str | None = None
    
    # Available/known tasks (for decentralized decision making)
    available_tasks: list[str] = field(default_factory=list)
    
    # Execution state - subgoal 
    #prediction
    waypoints: list[tuple[float, float]] | None = None
    current_waypoint_idx: int = 0
    
    # Local world representation
    local_obstacles: list = field(default_factory=list)  # agent's perception
    
    # Task metrics
    tasks_completed: int = 0
    current_task_progress: float = 0.0  # 0.0 to 1.0

@dataclass(slots=True)
class AgentTAContainer(OverarchingContainer):
    config: AgentTaskConfig
    state: AgentTaskState
