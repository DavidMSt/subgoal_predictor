from dataclasses import dataclass, field
from master_thesis.containers.base_container import OverarchingContainer
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.task_container import TaskContainer
import numpy as np

@dataclass(frozen=False, slots=True)
class AssignmentContextState:
    """Mutable state for assignment context - holds strategy outputs"""

    # Outputs of the strategy
    scores: np.ndarray | None = None
    matches: list[tuple[int, int]] | None = None


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
    nearby_agents: tuple[FRODOAgentContainer, ...] = field(default_factory=tuple)

    # For centralized: all tasks. For decentralized: visible tasks
    nearby_tasks: tuple[TaskContainer, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class AssignmentContextContainer(OverarchingContainer):
    """Container for assignment strategy context.

    Holds both input information (config) and strategy outputs (state).
    This container is created when running a strategy and passed to solve() methods.
    """
    config: AssignmentContextConfig = field(default_factory=AssignmentContextConfig)
    state: AssignmentContextState = field(default_factory=AssignmentContextState)
