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
    matches: list[tuple[str, str]] | None = None  # (agent_id, task_id) pairs
    scores: np.ndarray | None = None  # Cost matrix (n_agents, n_tasks)


@dataclass(frozen=True, slots=True)
class SimTAConfig(AssignmentContextConfigBase):
    """Config for centralized assignment - full information"""
    strategy: str


@dataclass(slots=True)
class SimTAResultContainer(BaseContainer):
    """Container for centralized assignment strategy context and results.

    Used when a central coordinator has full information about all agents and tasks.
    """
    config: SimTAConfig = field(default_factory=SimTAConfig)
    state: SimTAState = field(default_factory=SimTAState)

    def get_assignment_matrix(self, agent_containers: dict[str, 'FRODOAgentContainer'], task_containers: dict[str, 'TaskContainer']) -> np.ndarray:
        """Compute global assignment matrix from matches.

        Args:
            agent_containers: Dict of agent containers by object_id (for ordering)
            task_containers: Dict of task containers by object_id (for ordering)

        Returns:
            Boolean matrix of shape (n_agents, n_tasks) where True indicates assignment
        """
        n_agents = len(agent_containers)
        n_tasks = len(task_containers)
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)

        if self.matches is not None:
            # Build index mappings from IDs
            agent_ids = list(agent_containers.keys())
            task_ids = list(task_containers.keys())
            agent_id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}
            task_id_to_idx = {tid: j for j, tid in enumerate(task_ids)}

            # Fill assignment matrix
            for agent_id, task_id in self.matches:
                i = agent_id_to_idx[agent_id]
                j = task_id_to_idx[task_id]
                assignment[i, j] = True

        return assignment
