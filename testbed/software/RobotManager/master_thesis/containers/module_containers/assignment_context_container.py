from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
import numpy as np

if TYPE_CHECKING:
    from master_thesis.task_assignment.ta_strategies import StrategyABC


# ============================================================================
# BASE CLASSES - Common fields for both centralized and decentralized
# ============================================================================

@dataclass(frozen=False, slots=True)
class AssignmentContextStateBase:
    """Common state fields for both centralized and decentralized"""
    strategy: "StrategyABC | None" = None
    computation_time: float | None = None


@dataclass(frozen=True, slots=True)
class AssignmentContextConfigBase:
    """Common config fields - shared parameters"""
    pass


# ============================================================================
# CENTRALIZED ASSIGNMENT CONTAINER
# ============================================================================

@dataclass(frozen=False, slots=True)
class CentralizedAssignmentState(AssignmentContextStateBase):
    """State for centralized assignment - global view"""
    matches: list[tuple[int, int]] | None = None  # (agent_idx, task_idx) pairs
    scores: np.ndarray | None = None  # Cost matrix (n_agents, n_tasks)


@dataclass(frozen=True, slots=True)
class CentralizedAssignmentConfig(AssignmentContextConfigBase):
    """Config for centralized assignment - full information"""
    nearby_agents: dict[str, FRODOAgentContainer] = field(default_factory=dict)  # All agents
    nearby_tasks: dict[str, TaskContainer] = field(default_factory=dict)  # All tasks


@dataclass(slots=True)
class CentralizedAssignmentContainer(BaseContainer):
    """Container for centralized assignment strategy context and results.

    Used when a central coordinator has full information about all agents and tasks.
    """
    config: CentralizedAssignmentConfig = field(default_factory=CentralizedAssignmentConfig)
    state: CentralizedAssignmentState = field(default_factory=CentralizedAssignmentState)

    def get_assignment_matrix(self) -> np.ndarray:
        """Compute global assignment matrix from matches.

        Returns:
            Boolean matrix of shape (n_agents, n_tasks) where True indicates assignment
        """
        n_agents = len(self.nearby_agents)
        n_tasks = len(self.nearby_tasks)
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)

        if self.matches is not None:
            for i, j in self.matches:
                assignment[i, j] = True

        return assignment


# ============================================================================
# DECENTRALIZED ASSIGNMENT CONTAINER
# ============================================================================

@dataclass(frozen=False, slots=True)
class DecentralizedAssignmentState(AssignmentContextStateBase):
    """State for decentralized assignment - single agent's decision"""
    chosen_task_id: str | None = None  # ID of chosen task
    task_scores: list[float] | None = None  # Scores for each nearby task
    bid_values: dict[str, float] | None = None  # For auction-based strategies (CBBA)


@dataclass(frozen=True, slots=True)
class DecentralizedAssignmentConfig(AssignmentContextConfigBase):
    """Config for decentralized assignment - limited local information"""
    self_state: FRODOAgentContainer  # The agent making the decision
    nearby_agents: dict[str, FRODOAgentContainer] = field(default_factory=dict)  # Visible neighbors
    nearby_tasks: dict[str, TaskContainer] = field(default_factory=dict)  # Visible tasks


@dataclass(slots=True)
class DecentralizedAssignmentContainer(BaseContainer):
    """Container for decentralized assignment - single agent's perspective.

    Each agent maintains its own container with its local decision.
    The simulation can aggregate multiple agents' containers for visualization.
    """
    config: DecentralizedAssignmentConfig
    state: DecentralizedAssignmentState = field(default_factory=DecentralizedAssignmentState)

    def get_chosen_task(self) -> TaskContainer | None:
        """Get the task container this agent chose.

        Returns:
            TaskContainer if a task was chosen, None otherwise
        """
        if self.chosen_task_id is None:
            return None
        return self.nearby_tasks.get(self.chosen_task_id)
