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
    waypoints: list | None = None                       # simplified geometric waypoints [[x,y], ...]
    start_in_collision: bool = False                    # True when OMPL rejected start state (transient — agent inside wall)
    wall_time: float = 0.0                              # actual wall-clock seconds spent in plan() (for RL reward shaping)


# ── Abstract base ───────────────────────────────────────────────────

class PathPlannerBase(ABC):
    """Abstract base for path planning / subgoal prediction modules."""

    def __init__(self, agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger):
        self.agent_cont = agent_cont
        self.lwr_cont = lwr_cont
        self.logger = logger

    @abstractmethod
    def plan(self, goal_task: TaskContainer, phase_key: str = 'default',
             explicit_start: np.ndarray | None = None,
             use_roadmap: bool = True) -> PlanResult:
        """Compute a plan toward the goal task.

        Args:
            goal_task:      Target task or subgoal.
            phase_key:      Storage key in the planner container.
            explicit_start: If provided, use this [x, y, psi] as the plan
                            start instead of the agent's current position.
                            Used by SubgoalManager for upfront pre-planning.
            use_roadmap:    If False, skip any stored PRM* roadmap and run a
                            fresh RRT solve.  Set to False by SubgoalManager
                            for mid-episode replans so only the initial
                            plan_all_upfront() uses the roadmap.
        """
        ...

    @abstractmethod
    def needs_replan(self) -> bool:
        """Whether the planner should be called again."""
        ...

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        """Called by simulation after agent is registered."""
        self.lwr_cont = lwr_cont
