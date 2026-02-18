"""Coordinates planner and executor: assign task → plan → execute → replan."""

import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.modules.execution.motion_executor_base import MotionExecutorBase
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer


class SubgoalManager:
    """
    Thin coordinator sitting between the planner and executor.

    Reads the assigned task from the TA container (single source of truth)
    rather than maintaining its own copy.

    Lifecycle (same for every pipeline mode):
        1. sim.start_ta()  → TA module sets ta_cont.assigned_task
        2. sim.start_mp()  → sets sgm.start_planning_flag  → _action_planning picks it up
        3. sim.start_exe() → sets sgm._execution_enabled    → executor starts producing controls
        4. tick() each step → handles automatic re-planning for reactive modes
    """

    def __init__(self, planner: PathPlannerBase, executor: MotionExecutorBase,
                 ta_cont: AgentTAContainer, logger: Logger):
        self.planner = planner
        self.executor = executor
        self._ta_cont = ta_cont
        self.logger = logger

        self._plan_active: bool = False
        self._execution_enabled: bool = False
        self._last_result: PlanResult | None = None

        # Flag set by sim-level trigger (sim.start_mp → sets this to a phase key string)
        self.start_planning_flag: str | None = None

    @property
    def current_task(self) -> TaskContainer | None:
        """Read assigned task from the TA container (single source of truth)."""
        return self._ta_cont.assigned_task

    @property
    def last_plan_result(self) -> PlanResult | None:
        """Last successful plan result (for visualization)."""
        return self._last_result

    # ── External triggers ───────────────────────────────────────────

    def start_planning(self, phase_key: str = 'default'):
        """Explicit trigger from sim level (sim.start_mp()).  Runs planner once."""
        self.executor.clear()
        self._do_plan(phase_key)

    def start_execution(self):
        """Explicit trigger from sim level (sim.start_exe()). Activates executor."""
        self._execution_enabled = True

        # For TrajectoryExecutor: activate any staged (but not yet active) phase
        if hasattr(self.executor, 'start_execution'):
            self.executor.start_execution()

        self.logger.debug("SubgoalManager: execution enabled")

    # ── Per-tick call ───────────────────────────────────────────────

    def tick(self):
        """Called every LOGIC step.  Handles automatic re-planning for reactive modes."""
        if not self._execution_enabled:
            return
        if not self._plan_active:
            return
        if self.current_task is None:
            return

        # Re-plan when the executor reports goal reached AND the planner wants to replan
        if self.executor.is_goal_reached() and self.planner.needs_replan():
            self.logger.debug("SubgoalManager: replanning (executor reached subgoal)")
            self._do_plan()

    # ── Internal ────────────────────────────────────────────────────

    def _do_plan(self, phase_key: str = 'default'):
        if self.current_task is None:
            self.logger.warning("SubgoalManager: _do_plan called but no task assigned")
            return

        result = self.planner.plan(self.current_task, phase_key)
        if result.success:
            self._last_result = result
            self.executor.set_plan(result, phase_key=phase_key)
            self._plan_active = True
            self.logger.debug(f"SubgoalManager: plan succeeded (phase_key={phase_key})")

            # Auto-activate if execution was already enabled (handles the
            # race in runPipeline where start_exe() is called before planning
            # completes — pending_phase would otherwise never be activated).
            if self._execution_enabled and hasattr(self.executor, 'start_execution'):
                self.executor.start_execution()
        else:
            self.logger.warning("SubgoalManager: planner returned success=False")

    def reset(self):
        """Full reset (used between episodes in RL training)."""
        self._plan_active = False
        self._execution_enabled = False
        self._last_result = None
        self.start_planning_flag = None
        self.executor.clear()
