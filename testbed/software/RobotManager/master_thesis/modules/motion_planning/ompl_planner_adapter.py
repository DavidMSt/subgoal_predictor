"""Adapter wrapping the existing MPAgentModule into the PathPlannerBase interface."""

from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.modules.motion_planning.mp_agent_module import MPAgentModule
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer


class OMPLPlannerAdapter(PathPlannerBase):
    """Wraps the existing OMPL-based MPAgentModule into PathPlannerBase."""

    def __init__(self, agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger: Logger):
        super().__init__(agent_cont, lwr_cont, logger)
        self._mpm = MPAgentModule(
            agent_cont=agent_cont,
            lwr_cont=lwr_cont,
            logger=logger,
        )

    # ── PathPlannerBase interface ───────────────────────────────────

    def plan(self, goal_task: TaskContainer, phase_key: str = 'default') -> PlanResult:
        self._mpm.plan_motion(phase_key=phase_key, goal_task=goal_task)

        phase = self._mpm.planner_cont.phases.get(phase_key)
        if phase is not None:
            return PlanResult(success=True, phase_container=phase)
        return PlanResult(success=False)

    def needs_replan(self) -> bool:
        return False

    # ── Delegation helpers ──────────────────────────────────────────

    @property
    def planner_cont(self) -> AgentMPPlannerContainer:
        """Expose the underlying planner container (needed by simulation)."""
        return self._mpm.planner_cont

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        super().set_lwr_cont(lwr_cont)
        self._mpm.lwr_cont = lwr_cont
