"""Trivial passthrough planner: returns the task goal directly as a subgoal."""

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer


class DirectGoalPlanner(PathPlannerBase):
    """Passes the task goal straight through as a reactive subgoal (for MPPI/MPC)."""

    def __init__(self, agent_cont: FRODOAgentContainer, lwr_cont: LocalWorldContainer | None, logger: Logger):
        super().__init__(agent_cont, lwr_cont, logger)

    def plan(self, goal_task: TaskContainer, phase_key: str = 'default',
             explicit_start=None, use_roadmap: bool = True) -> PlanResult:
        subgoal = np.array([goal_task.x, goal_task.y, goal_task.psi])
        self.logger.debug(f"DirectGoalPlanner: subgoal = {subgoal}")
        return PlanResult(success=True, subgoal=subgoal, requires_reactive=True)

    def needs_replan(self) -> bool:
        return False
