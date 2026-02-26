"""Adapter wrapping the existing EXEAgentModule into the MotionExecutorBase interface."""

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase
from master_thesis.modules.execution.exe_agent_module import EXEAgentModule
from master_thesis.modules.motion_planning.path_planner_base import PlanResult
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer


class TrajectoryExecutor(MotionExecutorBase):
    """Wraps the existing EXEAgentModule for trajectory playback.

    Phases are staged via set_plan() but only activated when
    start_execution() is called (matching the old sim.start_exe() flow).
    """

    def __init__(self, agent_cont: FRODOAgentContainer, logger: Logger):
        super().__init__(agent_cont, logger)
        self._exi = EXEAgentModule(agent_cont=agent_cont, logger=logger)

    # ── MotionExecutorBase interface ────────────────────────────────

    def step(self) -> np.ndarray:
        return self._exi.step()

    def set_plan(self, plan_result: PlanResult, phase_key: str = 'default'):
        if plan_result.phase_container is None:
            self.logger.warning("TrajectoryExecutor received PlanResult without phase_container")
            return

        phase = plan_result.phase_container

        # Remove old phase with same key if it exists (re-plan scenario)
        if phase_key in self._exi.phases and phase_key != 'idle':
            del self._exi._phases[phase_key]

        self._exi.add_phase(phase_key, phase)
        # Don't activate yet — wait for start_execution()
        self.exe_cont.state.pending_phase = phase_key

    def is_active(self) -> bool:
        return self._exi.active_phase != 'idle'

    def is_goal_reached(self) -> bool:
        return not self.is_active() and self.exe_cont.state.pending_phase is None

    def clear(self):
        # Remove all non-idle phases and go back to idle
        for name in list(self._exi._phases.keys()):
            if name != 'idle':
                del self._exi._phases[name]
        self.exe_cont.state.active_phase = 'idle'
        self.exe_cont.state.queued_phases.clear()
        self._exi._pending_end = False
        self._exi.exe_cont.state.execution_mode = 'idle'
        self.exe_cont.state.pending_phase = None

    # ── Delegation helpers ──────────────────────────────────────────

    @property
    def exe_cont(self) -> AgentExeContainer:
        """Expose the underlying execution container (needed by simulation)."""
        return self._exi.exe_cont

    @property
    def phases(self):
        return self._exi.phases

    def start_execution(self):
        """Activate any staged phase (mirrors sim-level sim.start_exe() trigger)."""
        self._exi.exe_cont.start_execution = True
        if self.exe_cont.state.pending_phase is not None:
            self._exi.activate_phase(self.exe_cont.state.pending_phase)
            self.logger.info(f"Activated pending phase '{self.exe_cont.state.pending_phase}'")
            self.exe_cont.state.pending_phase = None
