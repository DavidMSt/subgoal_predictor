from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from core.utils.logging_utils import Logger

@dataclass(frozen=False, slots=True)
class AgentTAState:
    """Mutable runtime state for agent task execution"""
    # Set from the simulation, flag get polled by the agent
    assignment_pending: bool = False

    # Task assignment
    _assigned_task: TaskContainer| None = None 

    # scores for each visible task
    task_scores: list[float] | None = None  # Scores for each visible task
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
    logger: Logger | None = None

    @property
    def assigned_task(self) -> TaskContainer | None:
        return self.state._assigned_task

    @assigned_task.setter
    def assigned_task(self, value: TaskContainer | None):
        self.state._assigned_task = value
        
        if self.logger is not None:
            self.logger.info('Assigned task set to: ', value)
