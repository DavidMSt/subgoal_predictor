from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.task_container import TaskContainer

@dataclass(frozen=False, slots=True)
class AgentTAState:
    """Mutable runtime state for agent task execution"""
    # Set from the simulation, flag get polled by the agent
    assignment_pending: bool = False

    # Task assignment
    assigned_task: TaskContainer| None = None 

    # scores for each nearby task
    task_scores: list[float] | None = None  # Scores for each nearby task
    bid_values: dict[str, float] | None = None  # For auction-based strategies (CBBA)

    
    

@dataclass(frozen=True, slots=True)
class AgentTAConfig:
    """Immutable configuration for agent task management"""

    # Distance computation parameters
    distance_metric: str = 'euclidean'  # 'euclidean', 'manhattan', 'dubins', etc.

@dataclass(slots=True)
class AgentTAContainer(BaseContainer):
    config: AgentTAConfig = field(default_factory=AgentTAConfig)
    state: AgentTAState = field(default_factory=AgentTAState)
