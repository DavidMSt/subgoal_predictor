from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING
import numpy as np

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer

if TYPE_CHECKING:
    from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer


# ── Plan result ─────────────────────────────────────────────────────

@dataclass
class PlanResult:
    """Unified output from any path planner."""
    success: bool
    phase_container: 'MPPhaseContainer | None' = None  # for trajectory planners (OMPL)
    subgoal: np.ndarray | None = None                   # for reactive planners [x, y, psi]
    requires_reactive: bool = False


# ── Abstract base ───────────────────────────────────────────────────

class PathPlannerBase(ABC):
    """Abstract base for path planning / subgoal prediction modules."""

    def __init__(self, agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger):
        self.agent_cont = agent_cont
        self.lwr_cont = lwr_cont
        self.logger = logger

    @abstractmethod
    def plan(self, goal_task: TaskContainer, phase_key: str = 'default') -> PlanResult:
        """Compute a plan toward the goal task."""
        ...

    @abstractmethod
    def needs_replan(self) -> bool:
        """Whether the planner should be called again."""
        ...

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        """Called by simulation after agent is registered."""
        self.lwr_cont = lwr_cont
