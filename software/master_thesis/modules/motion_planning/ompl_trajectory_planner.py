"""OMPLTrajectoryPlanner — PathPlannerBase using OMPL geometric planning.

Merges the former OMPLPlannerAdapter + MPAgentModule into a single class
that directly wraps OMPLSmoothPathPlanner.
"""

import numpy as np

from core.utils.logging_utils import Logger

from master_thesis.modules.motion_planning.path_planner_base import PathPlannerBase, PlanResult
from master_thesis.modules.motion_planning.mp_functions.ompl_planner import OMPLSmoothPathPlanner, PlannerRoadmap
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig, AgentMPPlannerContainer


# ── Adapter helpers ───────────────────────────────────────────────────────────

def _obs_to_dicts(lwr_cont: LocalWorldContainer) -> list[dict]:
    return [c.to_geometry_dict() for c in lwr_cont.state.obstacles.values()]


def _agents_to_dicts(agent_conts: list) -> list[dict]:
    return [c.to_geometry_dict() for c in agent_conts]


def _traj_dict_to_container(traj: dict) -> MPPhaseContainer:
    """Convert raw trajectory dict from OMPLSmoothPathPlanner.get_solution() to MPPhaseContainer."""
    dt = traj['dt']
    inputs = list(traj['inputs'])
    states = list(traj['states'])
    N = len(inputs)
    return MPPhaseContainer(config=MPPhaseConfig(
        inputs=inputs,
        states=states,
        durations=[dt] * N,
        delta_t=dt,
    ))


# ── Planner ───────────────────────────────────────────────────────────────────

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
    ):
        super().__init__(agent_cont, lwr_cont, logger)
        self._motion_planner = None
        self._planner_cont = self._setup_mp_container()
        # Agent containers to freeze as static obstacles on the next plan().
        # Set by the collision prevention action; cleared after each plan.
        self._freeze_agents: list = []

    # ── PathPlannerBase interface ───────────────────────────────────

    _MAX_BEZIER_RETRIES: int = 5

    def plan(
        self,
        goal_task: TaskContainer,
        phase_key: str = 'default',
        roadmap: PlannerRoadmap | None = None,
    ) -> PlanResult:
        """Plan a trajectory to goal_task.

        Args:
            goal_task:  Target task container.
            phase_key:  Key under which the result is stored in planner_cont.phases.
            roadmap:    Pre-built PlannerRoadmap from RoadmapBuilder.build().
                        If provided, queries the PRM* graph (fast multi-query).
                        If None, runs a fresh RRT solve.
        """
        if self._motion_planner is None:
            self._motion_planner = self._setup_motion_planner()

        frozen = self._freeze_agents
        self._freeze_agents = []

        start = np.array([self.agent_cont.x, self.agent_cont.y, self.agent_cont.psi])
        goal  = np.array([goal_task.x, goal_task.y, goal_task.psi])

        # If frozen agents are present we must fall back to RRT regardless,
        # since the shared roadmap was built without them.
        active_roadmap = None if frozen else roadmap

        obs_dicts    = _obs_to_dicts(self.lwr_cont)
        frozen_dicts = _agents_to_dicts(frozen) if frozen else None
        self._motion_planner._collision_checker.refresh_env_manager(
            obstacles=obs_dicts,
            frozen_agents=frozen_dicts,
        )

        for attempt in range(self._MAX_BEZIER_RETRIES):
            try:
                solved, path_length = self._motion_planner.solve(start, goal, roadmap=active_roadmap)
            except ValueError as e:
                self.logger.warning(f"OMPL problem invalid: {e}")
                return PlanResult(success=False)

            if solved:
                solution_dict = self._motion_planner.get_solution()
                solution_cont = _traj_dict_to_container(solution_dict)
                self._planner_cont.phases[phase_key] = solution_cont
                self.logger.info(
                    f"Found solution with {len(solution_cont.states)} states, "
                    f"total length {path_length}, end config: {solution_cont.states[-1]}"
                )
                return PlanResult(
                    success=True,
                    phase_container=solution_cont,
                    waypoints=solution_dict.get('waypoints'),
                )

            opt = getattr(self._motion_planner, '_opt', None)
            if opt is not None and not opt.feasible:
                # Bézier infeasible for this OMPL path.
                # PRM* returns the same path deterministically — fall back to RRT.
                if active_roadmap is not None:
                    self.logger.warning("Bézier infeasible on PRM* path — falling back to RRT")
                    active_roadmap = None
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
        # Static environment changed → recreate the motion planner on next plan().
        self._motion_planner = None

    # ── Internal ─────────────────────────────────────────────────────

    def _setup_mp_container(self) -> AgentMPPlannerContainer:
        config = AgentMPPlannerConfig()
        return AgentMPPlannerContainer(config=config, logger=self.logger)

    def _setup_motion_planner(self) -> OMPLSmoothPathPlanner:
        return OMPLSmoothPathPlanner(
            limits=self.lwr_cont.config.limits,
            obstacles=_obs_to_dicts(self.lwr_cont),
            agent_dims=(self.agent_cont.length, self.agent_cont.width, self.agent_cont.height),
            config=self._planner_cont.config.planner_config,
        )
