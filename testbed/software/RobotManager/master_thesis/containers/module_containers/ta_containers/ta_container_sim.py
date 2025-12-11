from dataclasses import dataclass, field
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
import numpy as np

# from master_thesis.task_assignment.strategies.centralized_strategies import BaseStrategy


# ============================================================================
# BASE CLASSES - Common fields for both centralized and decentralized
# ============================================================================

@dataclass(frozen=False, slots=True)
class AssignmentContextStateBase:
    """Common state fields for both centralized and decentralized"""
    strategy: str | None = None
    computation_time: float | None = None


@dataclass(frozen=True, slots=True)
class AssignmentContextConfigBase:
    """Common config fields - shared parameters"""
    pass


# ============================================================================
# CENTRALIZED ASSIGNMENT CONTAINER
# ============================================================================

@dataclass(frozen=False, slots=True)
class SimTAState(AssignmentContextStateBase):
    """State for centralized assignment - global view"""
    matches: list[tuple[int, int]] | None = None  # (agent_idx, task_idx) pairs
    scores: np.ndarray | None = None  # Cost matrix (n_agents, n_tasks)


@dataclass(frozen=True, slots=True)
class SimTAConfig(AssignmentContextConfigBase):
    """Config for centralized assignment - full information"""
    strategy: str


@dataclass(slots=True)
class SimTAContainer(BaseContainer):
    """Container for centralized assignment strategy context and results.

    Used when a central coordinator has full information about all agents and tasks.
    """
    config: SimTAConfig = field(default_factory=SimTAConfig)
    state: SimTAState = field(default_factory=SimTAState)

    def get_assignment_matrix(self) -> np.ndarray:
        """Compute global assignment matrix from matches.

        Returns:
            Boolean matrix of shape (n_agents, n_tasks) where True indicates assignment
        """
        n = len(self.matches)
        assignment = np.zeros((n, n), dtype=np.bool_)

        if self.matches is not None:
            for i, j in self.matches:
                assignment[i, j] = True

        return assignment
