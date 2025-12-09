from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.task_container import TaskContainer
import numpy as np

if TYPE_CHECKING:
    from master_thesis.task_assignment.ta_strategies import StrategyABC

@dataclass(frozen=False, slots=True)
class AssignmentContextState:
    """Mutable state for assignment context - holds strategy outputs"""

    # Outputs of the strategy
    scores: np.ndarray | None = None
    matches: list[tuple[int, int]] | None = None

    # Reference to the strategy that produced this result
    strategy: "StrategyABC | None" = None


@dataclass(frozen=True, slots=True)
class AssignmentContextConfig:
    """Immutable configuration for assignment context - holds input information

    For centralized strategies:
        - self_state: None (no single agent perspective)
        - nearby_agents: all agent containers (full information)
        - nearby_tasks: all task containers (full information)

    For decentralized strategies:
        - self_state: the agent container making the decision
        - nearby_agents: list of visible/communicable agent containers (limited information)
        - nearby_tasks: list of visible task containers (limited information)
    """

    # For decentralized: the agent making the decision. For centralized: None
    self_state: FRODOAgentContainer | None = None

    # For centralized: all agents. For decentralized: visible/communicable neighbors
    nearby_agents: dict[str, FRODOAgentContainer] = field(default_factory=dict)

    # For centralized: all tasks. For decentralized: visible tasks
    nearby_tasks: dict[str, TaskContainer] = field(default_factory=dict)


@dataclass(slots=True)
class AssignmentContextContainer(BaseContainer):
    """Container for assignment strategy context and results.

    Holds both input information (config) and strategy outputs (state).
    This container is created when running a strategy, passed to solve() methods,
    and returned as the result.
    """
    config: AssignmentContextConfig = field(default_factory=AssignmentContextConfig)
    state: AssignmentContextState = field(default_factory=AssignmentContextState)

    def get_assignment_matrix(self) -> np.ndarray:
        """Compute assignment matrix from matches.

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
