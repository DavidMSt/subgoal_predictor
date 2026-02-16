"""Wraps LocalControlModule + a reactive controller (MPPI/MPC) into MotionExecutorBase."""

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase
from master_thesis.modules.motion_planning.path_planner_base import PlanResult
from master_thesis.modules.local_control.local_control_module import LocalControlModule
from master_thesis.modules.local_control.local_controller import LocalController
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class ReactiveExecutor(MotionExecutorBase):
    """Online reactive execution via LocalControlModule (MPPI, MPC, etc.)."""

    def __init__(
        self,
        agent_cont: FRODOAgentContainer,
        controller: LocalController,
        lwr_cont: LocalWorldContainer | None,
        logger: Logger,
    ):
        super().__init__(agent_cont, logger)
        self._lcm = LocalControlModule(agent_cont=agent_cont, controller=controller, logger=logger)
        self.lwr_cont = lwr_cont

    # ── MotionExecutorBase interface ────────────────────────────────

    def step(self) -> np.ndarray:
        if self.lwr_cont is None:
            return np.zeros(2)
        return self._lcm.step(self.lwr_cont)

    def set_plan(self, plan_result: PlanResult, phase_key: str = 'default'):
        if plan_result.subgoal is not None:
            self._lcm.set_goal(plan_result.subgoal)
        else:
            self.logger.warning("ReactiveExecutor received PlanResult without subgoal")

    def is_active(self) -> bool:
        return self._lcm.current_goal is not None

    def is_goal_reached(self) -> bool:
        return self._lcm.is_goal_reached()

    def clear(self):
        self._lcm.clear_goal()

    # ── Helpers ─────────────────────────────────────────────────────

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        self.lwr_cont = lwr_cont
