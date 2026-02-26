"""Wraps LocalControlModule + a reactive controller (MPPI/MPC) into MotionExecutorBase."""

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase
from master_thesis.modules.motion_planning.path_planner_base import PlanResult
from master_thesis.modules.local_control.local_control_module import LocalControlModule
from master_thesis.modules.local_control.local_controller import LocalController
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer


class ReactiveExecutor(MotionExecutorBase):
    """Online reactive execution via LocalControlModule (MPPI, MPC, etc.).

    ``replan_interval`` controls how often the controller is queried.
    A value of 1 means every simulation tick (default), 5 means every
    5th tick, etc.  Between replans the last computed control is held.
    """

    def __init__(
        self,
        agent_cont: FRODOAgentContainer,
        controller: LocalController,
        lwr_cont: LocalWorldContainer | None,
        logger: Logger,
        replan_interval: int = 1,
    ):
        super().__init__(agent_cont, logger)
        self._lcm = LocalControlModule(agent_cont=agent_cont, controller=controller, logger=logger)
        self.lwr_cont = lwr_cont
        self.replan_interval = max(1, replan_interval)
        self._tick = 0
        self._last_control = np.zeros(2)

    # ── MotionExecutorBase interface ────────────────────────────────

    def step(self) -> np.ndarray:
        if self.lwr_cont is None:
            return np.zeros(2)

        self._tick += 1
        if self._tick % self.replan_interval == 0:
            self._last_control = self._lcm.step(self.lwr_cont)

        return self._last_control

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
        self._tick = 0
        self._last_control = np.zeros(2)

    @property
    def last_trajectory(self):
        """Best trajectory from the last controller step (for visualization)."""
        return getattr(self._lcm.controller, 'last_trajectory', None)

    # ── Helpers ─────────────────────────────────────────────────────

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        self.lwr_cont = lwr_cont
