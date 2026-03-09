"""OMPLTrajectoryPlanner — PathPlannerBase using OMPL kinodynamic planning.

Merges the former OMPLPlannerAdapter + MPAgentModule into a single class
that directly wraps OMPLPlannerFRODOKino.
"""

import numpy as np
from typing import Type

from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.modules.motion_planning.helper.ompl_planner import (
    OMPLPlannerFRODOKino,
    OMPLSmoothPathPlanner,
    OMPLPlannerFRODOBase,
)
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig, AgentMPPlannerContainer
from master_thesis.containers.base_container import BaseContainer


class OMPLTrajectoryPlanner(PathPlannerBase):
    """OMPL-based trajectory planner implementing PathPlannerBase.

    Directly manages the OMPL planner and its container, removing the
    previous indirection through MPAgentModule.
    """

    def __init__(
        self,
        agent_cont: FRODOAgentContainer,
        lwr_cont: LocalWorldContainer | None,
        logger: Logger,
        mp_type: Type[OMPLPlannerFRODOBase] = OMPLSmoothPathPlanner,
        # mp_type: Type[OMPLPlannerFRODOBase] = OMPLPlannerFRODOKino,
    ):
        super().__init__(agent_cont, lwr_cont, logger)
        self.mp_type = mp_type
        self._motion_planner = None
        self._planner_cont = self._setup_mp_container()
        # Agent containers to freeze as static obstacles on the next plan().
        # Set by the collision prevention action; cleared after each plan.
        self._freeze_agents: list = []

    # ── PathPlannerBase interface ───────────────────────────────────

    _MAX_BEZIER_RETRIES: int = 5

    def plan(self, goal_task: TaskContainer, phase_key: str = 'default') -> PlanResult:
        if self._motion_planner is None:
            self._motion_planner = self._setup_motion_planner()

        # Freeze only the specific agents that caused a prospective collision.
        # Empty on initial plans → static-only FCL → valid PRM* roadmap queries.
        frozen = self._freeze_agents
        self._freeze_agents = []

        self._planner_cont.start = np.array([self.agent_cont.x, self.agent_cont.y, self.agent_cont.psi])
        self._planner_cont.goal  = np.array([goal_task.x, goal_task.y, goal_task.psi])

        # Initial plan → PRM* (static obstacles only — shared roadmap valid for all agents).
        # Replan after collision → RRT (frozen agents + neighbors baked into FCL).
        use_prm = len(frozen) == 0
        self._motion_planner._collision_checker.refresh_env_manager(
            frozen_agents=frozen,
            static_only=use_prm,
        )

        for attempt in range(self._MAX_BEZIER_RETRIES):
            try:
                solved, path_length = self._motion_planner.solve_problem(use_prm=use_prm)
            except ValueError as e:
                self.logger.warning(f"OMPL problem invalid: {e}")
                return PlanResult(success=False)

            if solved:
                solution_cont = self._motion_planner._create_solution_cont()
                self._planner_cont.phases[phase_key] = solution_cont
                self.logger.info(
                    f"Found solution with {len(solution_cont.states)} states, "
                    f"total length {path_length}, end config: {solution_cont.states[-1]}"
                )
                return PlanResult(success=True, phase_container=solution_cont)

            opt = getattr(self._motion_planner, '_opt', None)
            if opt is not None and not opt.feasible:
                # Bézier infeasible for this OMPL path.
                # PRM* returns the same path deterministically — fall back to RRT.
                if use_prm:
                    self.logger.warning("Bézier infeasible on PRM* path — falling back to RRT")
                    use_prm = False
                else:
                    self.logger.warning(
                        f"Bézier infeasible (attempt {attempt + 1}/{self._MAX_BEZIER_RETRIES})"
                        " — retrying with new RRT path"
                    )
            else:
                self.logger.warning("OMPL timeout: no geometric path found within time limit")
                return PlanResult(success=False)

        self.logger.warning(
            f"Bézier optimisation infeasible after {self._MAX_BEZIER_RETRIES} attempts — giving up"
        )
        return PlanResult(success=False)

    def needs_replan(self) -> bool:
        return False

    # ── Public properties ────────────────────────────────────────────

    @property
    def planner_cont(self) -> AgentMPPlannerContainer:
        """Expose the underlying planner container (needed by simulation)."""
        return self._planner_cont

    # ── Override ─────────────────────────────────────────────────────

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        super().set_lwr_cont(lwr_cont)
        # Static environment changed → discard shared roadmap so it's rebuilt next plan().
        OMPLSmoothPathPlanner.invalidate_roadmap()
        self._motion_planner = None

    # ── Internal ─────────────────────────────────────────────────────

    def _setup_mp_container(self) -> AgentMPPlannerContainer:
        config = AgentMPPlannerConfig()
        return AgentMPPlannerContainer(config=config, logger=self.logger)

    def _setup_motion_planner(self):
        return self.mp_type(
            mp_container=self._planner_cont,
            agent_container=self.agent_cont,
            lwr_container=self.lwr_cont,
        )
