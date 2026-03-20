"""Coordinates planner and executor: assign task → plan → execute → replan."""

import numpy as np
from types import SimpleNamespace
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

    RL subgoal mode (optional):
        Call set_subgoals() with a list of (x, y, psi) arrays before starting execution.
        The manager will plan to each subgoal in sequence, then to the final task.
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
        self._recovery_needed: bool = False  # set when start-in-collision; agent reads and handles

        # Flag set by sim-level trigger (sim.start_mp → sets this to a phase key string)
        self.start_planning_flag: str | None = None

        # RL subgoal queue — set via set_subgoals() before execution
        self._subgoal_queue: list[np.ndarray] = []
        self._subgoal_idx: int = 0
        # Wait-time support: ticks to hold at each subgoal before replanning
        self._wait_ticks_per_subgoal: list[int] = []
        self._current_wait_ticks: int = 0
        self._subgoal_wait_started: bool = False

        # Count of OMPL planning failures in the current episode (used for RL reward shaping)
        self._failed_plans: int = 0
        # Count of subgoals skipped due to planning failure (excludes final-task failures)
        self._skipped_subgoals: int = 0
        # Countdown for retrying after a final-task planning failure (0 = no retry pending)
        self._retry_ticks: int = 0

    @property
    def current_task(self) -> TaskContainer | None:
        """Read assigned task from the TA container (single source of truth)."""
        return self._ta_cont.assigned_task

    @property
    def last_plan_result(self) -> PlanResult | None:
        """Last successful plan result (for visualization)."""
        return self._last_result

    # ── RL subgoal interface ─────────────────────────────────────────

    def set_subgoals(self, subgoals: list[np.ndarray], wait_ticks: list[int] | None = None):
        """Load RL-predicted subgoal sequence.

        Each entry is a (3,) array [x, y, psi].  The manager will plan to
        each subgoal in order, then fall back to the final assigned task.

        Args:
            subgoals: List of (3,) arrays [x, y, psi].
            wait_ticks: Number of sim ticks to hold at each subgoal before
                replanning.  Defaults to [0] * len(subgoals).
        """
        self._subgoal_queue = list(subgoals)
        self._subgoal_idx = 0
        self._wait_ticks_per_subgoal = list(wait_ticks) if wait_ticks else [0] * len(subgoals)
        self._current_wait_ticks = 0
        self._subgoal_wait_started = False
        self.logger.debug(f"SubgoalManager: {len(subgoals)} subgoals loaded")

    @property
    def _has_pending_subgoal(self) -> bool:
        return self._subgoal_idx < len(self._subgoal_queue)

    def _current_target(self):
        """Return the current planning target — next subgoal or the final task."""
        if self._has_pending_subgoal:
            sg = self._subgoal_queue[self._subgoal_idx]
            return SimpleNamespace(x=float(sg[0]), y=float(sg[1]), psi=float(sg[2]))
        return self.current_task

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

    def agent_reached_task(self) -> bool:
        """True when the agent is within the assigned task's goal_tolerance_xy."""
        task = self.current_task
        if task is None:
            return False
        agent_cont = self.planner.agent_cont
        dx = task.x - agent_cont.x
        dy = task.y - agent_cont.y
        tol = task.goal_tolerance_xy
        return (dx * dx + dy * dy) <= tol * tol

    def tick(self):
        """Called every LOGIC step.  Handles automatic re-planning."""
        # Position-based task completion — runs regardless of execution state
        # so it catches manual (joystick) driving as well as planned execution.
        if self.agent_reached_task():
            self._complete_task()
            return

        if not self._execution_enabled:
            return
        if not self._plan_active:
            if self._retry_ticks > 0:
                self._retry_ticks -= 1
                if self._retry_ticks == 0:
                    self._do_plan()
            return
        if self.current_task is None:
            return

        if self.executor.is_goal_reached():
            # Wait-time countdown: hold position, don't replan yet
            if self._current_wait_ticks > 0:
                self._current_wait_ticks -= 1
                return
            if self._has_pending_subgoal:
                # Initiate wait at this subgoal if not yet started
                if not self._subgoal_wait_started:
                    w = self._wait_ticks_per_subgoal[self._subgoal_idx]
                    if w > 0:
                        self._current_wait_ticks = w
                        self._subgoal_wait_started = True
                        return
                self._subgoal_idx += 1
                self._subgoal_wait_started = False
                self.logger.debug(
                    f"SubgoalManager: subgoal reached, advancing to "
                    f"{self._subgoal_idx}/{len(self._subgoal_queue)}"
                )
            self._do_plan()

    # ── Internal ────────────────────────────────────────────────────

    def _complete_task(self):
        """Mark current task as completed: clear assignment, stop executor, log."""
        task_id = self.current_task.object_id if self.current_task is not None else '?'
        self.logger.info(f"Task '{task_id}' completed")
        self._ta_cont.assigned_task = None
        self._plan_active = False
        self.executor.clear()

    def _do_plan(self, phase_key: str = 'default'):
        target = self._current_target()

        # TODO: remove - since this is handled by the motion planner anyway? 
        if target is None:
            self.logger.warning("SubgoalManager: _do_plan called but no task assigned")
            return

        result = self.planner.plan(target, phase_key)
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
            self._failed_plans += 1
            if result.start_in_collision:
                # Transient failure: agent's position overlaps a frozen agent.
                # Signal the agent to reverse its recent inputs to physically
                # separate before replanning.  tick() will not interfere since
                # _plan_active stays False; the agent re-triggers planning via
                # start_planning_flag once recovery is complete.
                self.logger.warning("SubgoalManager: start-in-collision — requesting input-reversal recovery")
                self._plan_active = False
                self._recovery_needed = True
            elif self._has_pending_subgoal:
                # Skip the unreachable RL-predicted subgoal and try the next one.
                # Bounded by the remaining subgoal count — recursion terminates when
                # the queue is exhausted or a reachable target is found.
                self.logger.warning(
                    f"SubgoalManager: planning failed, skipping subgoal "
                    f"{self._subgoal_idx} → trying {self._subgoal_idx + 1}"
                )
                self._skipped_subgoals += 1
                self._subgoal_idx += 1
                self._do_plan(phase_key)
            else:
                # Final task is currently unreachable (e.g. path blocked by other agents).
                # Schedule a retry after ~10 s so the agent recovers once congestion clears.
                self.logger.warning("SubgoalManager: planner returned success=False — will retry in 5 ticks")
                self._plan_active = False
                self._retry_ticks = 5

    def reset(self):
        """Full reset (used between episodes in RL training)."""
        self._plan_active = False
        self._execution_enabled = False
        self._last_result = None
        self.start_planning_flag = None
        self._subgoal_queue = []
        self._subgoal_idx = 0
        self._wait_ticks_per_subgoal = []
        self._current_wait_ticks = 0
        self._subgoal_wait_started = False
        self._failed_plans = 0
        self._skipped_subgoals = 0
        self._recovery_needed = False
        self._retry_ticks = 0
        self.executor.clear()
