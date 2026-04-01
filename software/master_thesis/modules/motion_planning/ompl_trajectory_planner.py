"""OMPLTrajectoryPlanner — PathPlannerBase using OMPL geometric planning.

Merges the former OMPLPlannerAdapter + MPAgentModule into a single class
that directly wraps OMPLSmoothPathPlanner.
"""

import time
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
        # PRM* roadmap: loaded lazily on the first plan() call after the
        # motion planner is (re-)created.
        self._roadmap: PlannerRoadmap | None = None
        self._roadmap_filepath: str | None = None
        self._roadmap_load_attempted: bool = False

    # ── PathPlannerBase interface ───────────────────────────────────

    _MAX_BEZIER_RETRIES: int = 5

    def plan(
        self,
        goal_task: TaskContainer,
        phase_key: str = 'default',
        roadmap: PlannerRoadmap | None = None,
        explicit_start: np.ndarray | None = None,
        use_roadmap: bool = True,
    ) -> PlanResult:
        """Plan a trajectory to goal_task.

        Args:
            goal_task:      Target task container.
            phase_key:      Key under which the result is stored in planner_cont.phases.
            roadmap:        Pre-built PlannerRoadmap from RoadmapBuilder.build().
                            If provided, queries the PRM* graph (fast multi-query).
                            If None, runs a fresh RRT solve.
            explicit_start: If provided, use this [x, y, psi] as the plan start
                            instead of the agent's current position.  Used by
                            SubgoalManager for upfront pre-planning of subsequent
                            segments (e.g. subgoal → final task).
        """
        _t_plan_start = time.perf_counter()

        if self._motion_planner is None:
            self._motion_planner = self._setup_motion_planner()
            self._roadmap_load_attempted = False  # new planner → always retry load

        # Lazy roadmap load: triggered on first plan() after the motion planner is
        # created OR after set_roadmap_file() registers a new file on an already-live
        # planner (e.g. user builds roadmap after running one episode first).
        if self._roadmap is None and self._roadmap_filepath is not None and not self._roadmap_load_attempted:
            self._roadmap_load_attempted = True
            try:
                self._roadmap = self._motion_planner.load_roadmap(self._roadmap_filepath)
                self.logger.info(f"PRM* roadmap auto-loaded from '{self._roadmap_filepath}'")
            except Exception as exc:
                self.logger.warning(f"PRM* roadmap load failed: {exc}")

        # Use stored roadmap if none passed explicitly — but only for initial
        # planning (use_roadmap=True).  Mid-episode replans pass use_roadmap=False
        # so they always run a fresh RRT solve rather than querying PRM*.
        if use_roadmap and roadmap is None:
            roadmap = self._roadmap

        frozen = self._freeze_agents
        self._freeze_agents = []

        if explicit_start is not None:
            start = np.asarray(explicit_start, dtype=float)
        else:
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

        # Start-in-collision nudge: only for actual agent positions, not pre-planned starts
        # (pre-planned starts are endpoints of a previously validated trajectory).
        if explicit_start is None and self._motion_planner._collision_checker.check_state(start.tolist()):
            psi = start[2]
            escape_dirs = [
                psi + np.pi,          # backward
                psi,                  # forward
                psi + np.pi / 2,      # left
                psi - np.pi / 2,      # right
            ]
            escaped = False
            for dist in [0.05, 0.10, 0.15, 0.20]:
                for angle in escape_dirs:
                    candidate = start.copy()
                    candidate[0] += dist * np.cos(angle)
                    candidate[1] += dist * np.sin(angle)
                    if not self._motion_planner._collision_checker.check_state(candidate.tolist()):
                        self.logger.info(
                            f"Start nudged {dist:.2f}m (angle={angle:.2f}rad) to escape start-in-collision"
                        )
                        start = candidate
                        escaped = True
                        break
                if escaped:
                    break
            if not escaped:
                self.logger.warning("Start-in-collision: could not find free start position")
                return PlanResult(success=False, start_in_collision=True,
                                  wall_time=time.perf_counter() - _t_plan_start)

        for attempt in range(self._MAX_BEZIER_RETRIES):
            try:
                solved, path_length = self._motion_planner.solve(start, goal, roadmap=active_roadmap)
            except ValueError as e:
                self.logger.warning(f"OMPL problem invalid: {e}")
                return PlanResult(success=False, start_in_collision=False,
                                  wall_time=time.perf_counter() - _t_plan_start)

            if solved:
                solution_dict = self._motion_planner.get_solution()
                solution_cont = _traj_dict_to_container(solution_dict)
                self._planner_cont.phases[phase_key] = solution_cont
                self.logger.debug(
                    f"Found solution with {len(solution_cont.states)} states, "
                    f"total length {path_length}, end config: {solution_cont.states[-1]}"
                )
                return PlanResult(
                    success=True,
                    phase_container=solution_cont,
                    waypoints=solution_dict.get('waypoints'),
                    wall_time=time.perf_counter() - _t_plan_start,
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
                return PlanResult(success=False, wall_time=time.perf_counter() - _t_plan_start)

        self.logger.warning(
            f"Bézier optimisation infeasible after {self._MAX_BEZIER_RETRIES} attempts — giving up"
        )
        return PlanResult(success=False, wall_time=time.perf_counter() - _t_plan_start)

    def needs_replan(self) -> bool:
        return False

    def set_roadmap(self, roadmap: PlannerRoadmap | None) -> None:
        """Inject a pre-loaded PlannerRoadmap directly (no file I/O).

        Used to share one loaded roadmap instance across all agents in the
        same process, avoiding repeated ~5-min load_roadmap() calls.
        Setting roadmap_load_attempted=True prevents the lazy-load path in
        plan() from overwriting the injected object.
        """
        self._roadmap = roadmap
        self._roadmap_load_attempted = roadmap is not None

    def load_roadmap_from_file(self, filepath: str) -> PlannerRoadmap:
        """Force-load a PRM* roadmap file immediately (not lazily).

        Creates the motion planner if needed, loads the roadmap, stores it,
        and returns the PlannerRoadmap so the caller can share it with other
        agents via set_roadmap().
        """
        if self._motion_planner is None:
            self._motion_planner = self._setup_motion_planner()
        roadmap = self._motion_planner.load_roadmap(filepath)
        self._roadmap = roadmap
        self._roadmap_filepath = filepath
        self._roadmap_load_attempted = True
        self.logger.info(f"PRM* roadmap force-loaded from '{filepath}'")
        return roadmap

    def set_roadmap_file(self, filepath: str | None) -> None:
        """Register a .npy roadmap file to auto-load on the next plan() call.

        Passing None disables the stored roadmap.  If the filepath is the
        same as the currently registered one, the in-memory roadmap is kept.
        """
        if filepath != self._roadmap_filepath:
            self._roadmap_filepath = filepath
            self._roadmap = None
            self._roadmap_load_attempted = False  # allow load on next plan()

    def build_and_save_roadmap(self, filepath: str, roadmap_time: float | None = None) -> PlannerRoadmap:
        """Build a fresh PRM* roadmap, save it to *filepath*, and store it.

        Args:
            filepath:     Destination .npy file path.
            roadmap_time: Override for PRM* grow time in seconds.
                          If None, uses the planner config default (60 s).

        Intended to be called from a background thread.
        """
        if self._motion_planner is None:
            self._motion_planner = self._setup_motion_planner()
        if roadmap_time is not None:
            import dataclasses
            self._motion_planner.config = dataclasses.replace(
                self._motion_planner.config, roadmap_time=roadmap_time
            )
        roadmap = self._motion_planner.build_roadmap()
        self._motion_planner.save_roadmap(roadmap, filepath)
        # Register filepath without clearing the just-built roadmap.
        self._roadmap_filepath = filepath
        self._roadmap = roadmap
        return roadmap

    # ── Public properties ────────────────────────────────────────────

    @property
    def planner_cont(self) -> AgentMPPlannerContainer:
        """Expose the underlying planner container (needed by simulation)."""
        return self._planner_cont

    # ── Override ─────────────────────────────────────────────────────

    def set_lwr_cont(self, lwr_cont: LocalWorldContainer):
        super().set_lwr_cont(lwr_cont)
        # Recreate the motion planner so the collision checker picks up the new
        # environment.  The PRM* roadmap only encodes static geometry (walls/gaps)
        # and is NOT cleared — it stays valid across episode resets as long as the
        # scenario obstacles do not change.  Reloading 26k milestones on every
        # episode reset would make RL training prohibitively slow.
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
