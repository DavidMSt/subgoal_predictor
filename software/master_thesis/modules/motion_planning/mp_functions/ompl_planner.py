import os
import sys

try:
    import ompl
except ModuleNotFoundError:
    print(
        "OMPL module not found. Download from\n"
        "  https://github.com/ompl/ompl/releases\n"
        "then install via:\n"
        "  pip install ompl-<version>.whl\n"
        "Or use Docker: docker pull kavrakilab/ompl",
        file=sys.stderr,
    )
    sys.exit(1)

from ompl import base as ob
from ompl import geometric as og
from ompl import util as ou
from typing import Any
from dataclasses import dataclass

import math
import time
import numpy as np

from master_thesis.modules.motion_planning.mp_functions.collisions_fcl import AgentCollisionChecker
from master_thesis.modules.motion_planning.mp_functions.opt_safe import FRODOFlatOpt, OptimizationData


@dataclass
class OMPLPlannerConfig:
    """Planner tuning and robot kinematics for OMPLSmoothPathPlanner."""
    Ts: float = 0.1
    v_max: float = 0.3
    psi_dot_max: float = np.pi / 3
    # Safety factor applied to v_max and psi_dot_max in the Bézier optimizer only.
    # Keeps planned trajectories below the kinematic limits so Euler integration
    # errors and minor disturbances don't push the agent past the limits.
    bezier_safety_factor: float = 0.66
    timelimit: float = 10.0
    query_timelimit: float = 1.0   # time budget for PRM* queries — A* on existing graph is ~free
    roadmap_time: float = 300.0    # invest here: denser roadmap = better paths for all queries
    planner: str = 'rrt_connect'
    goal_bias: float = 0.1
    goal_eps: float = 0.1
    so_r2_weight: float = 0.0


@dataclass
class PlannerRoadmap:
    """Pre-built PRM* roadmap for reuse across solve() calls.

    Created by OMPLSmoothPathPlanner.build_roadmap() or RoadmapBuilder.build().
    Holds a reference to the SI and SVC to prevent GC/SIGSEGV.
    """
    prm: Any   # og.PRMstar
    si:  Any   # ob.SpaceInformation — must be the one used to build the roadmap
    _svc: Any  # FCLStateValidityChecker — keeps Python object alive (boost::python GC pin)


class FCLStateValidityChecker(ob.StateValidityChecker):  # type: ignore[misc]
    """Class-based SVC so OMPL can invoke clearance() for MaximizeMinClearanceObjective."""

    def __init__(self, si: ob.SpaceInformation, checker: AgentCollisionChecker):  # type: ignore[attr-defined]
        super().__init__(si)
        self._checker = checker

    def isValid(self, state) -> bool:
        return self._checker.check_state_ompl(state)

    def clearance(self, state) -> float:
        return self._checker.clearance_for_state(
            state.getX(), state.getY(), state.getYaw()
        )


class OMPLSmoothPathPlanner:
    """Geometric path planner (PRM* or RRT) + Bézier trajectory optimisation.

    Raw-data interface: accepts plain Python scalars/arrays, no containers.

    Typical usage
    -------------
    # One-time setup
    planner = OMPLSmoothPathPlanner(limits, obstacles, agent_dims, config)

    # Optional: build roadmap once for multi-query use
    roadmap = planner.build_roadmap()

    # Plan (pass roadmap to reuse it, omit for fresh RRT)
    solved, length = planner.solve(start, goal, roadmap=roadmap)
    if solved:
        solution = planner.get_solution()
    """

    def __init__(
        self,
        limits: tuple,
        obstacles: list[dict],
        agent_dims: tuple[float, float, float],
        config: OMPLPlannerConfig = None,
    ):
        """
        Args:
            limits:      ((x_min, x_max), (y_min, y_max))
            obstacles:   list of dicts with keys: x, y, psi, length, width, height
            agent_dims:  (length, width, height)
            config:      planner tuning; defaults to OMPLPlannerConfig()
        """
        self.limits = limits
        self.obstacles = obstacles
        self.agent_dims = agent_dims
        self.config = config or OMPLPlannerConfig()

        self._collision_checker = AgentCollisionChecker(agent_dims, obstacles)
        self._space = self._create_space()
        self._si    = self._create_space_info()

        self._opt:           FRODOFlatOpt | None = None
        self._solution_path                      = None
        self._last_start_psi: float              = 0.0
        self._active_si                          = self._si  # SI used in last solve()

    # ── Public interface ─────────────────────────────────────────────

    def build_roadmap(self) -> PlannerRoadmap:
        """Grow a PRM* roadmap over the static environment.

        Returns a PlannerRoadmap that can be passed to solve() repeatedly.
        """
        self._si.setup()
        prm = og.PRMstar(self._si)  # type: ignore[attr-defined]

        # PRMstar.growRoadmap() requires a problem definition to fully initialise
        # its internal sampler.  Sample two valid placeholder states; they are
        # replaced by clearQuery() before every real solve() call.
        sampler = self._si.allocValidStateSampler()
        s1 = self._si.allocState()
        s2 = self._si.allocState()
        sampler.sample(s1)
        sampler.sample(s2)
        pdef = ob.ProblemDefinition(self._si)  # type: ignore[attr-defined]
        pdef.setStartAndGoalStates(s1, s2, self.config.goal_eps)
        prm.setProblemDefinition(pdef)

        ptc = ob.timedPlannerTerminationCondition(self.config.roadmap_time)  # type: ignore[attr-defined]
        prm.growRoadmap(ptc)  # type: ignore[attr-defined]
        return PlannerRoadmap(prm=prm, si=self._si, _svc=self._svc)

    def save_roadmap(self, roadmap: PlannerRoadmap, filepath: str) -> None:
        """Save PRM* vertex positions to a .npy file for later reloading."""
        pd = ob.PlannerData(roadmap.si)  # type: ignore[attr-defined]
        roadmap.prm.getPlannerData(pd)
        verts = []
        for i in range(pd.numVertices()):
            s = pd.getVertex(i).getState()
            if s is not None:
                verts.append([s.getX(), s.getY(), s.getYaw()])
        arr = np.array(verts, dtype=np.float64)
        dirpath = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dirpath, exist_ok=True)
        np.save(filepath, arr)

    def load_roadmap(self, filepath: str) -> PlannerRoadmap:
        """Reconstruct a PRM* roadmap from a saved .npy vertex file.

        Each saved vertex is re-inserted via PRMstar.addMilestone(), which
        re-establishes edges to nearby vertices automatically.  This is far
        faster than a fresh growRoadmap() call (~seconds vs 60 s).
        """
        verts = np.load(filepath)
        self._si.setup()
        prm = og.PRMstar(self._si)  # type: ignore[attr-defined]
        sampler = self._si.allocValidStateSampler()
        s1 = self._si.allocState()
        s2 = self._si.allocState()
        sampler.sample(s1)
        sampler.sample(s2)
        pdef = ob.ProblemDefinition(self._si)  # type: ignore[attr-defined]
        pdef.setStartAndGoalStates(s1, s2, self.config.goal_eps)
        prm.setProblemDefinition(pdef)
        prm.setup()
        for v in verts:
            state = self._si.allocState()
            state.setX(float(v[0]))
            state.setY(float(v[1]))
            state.setYaw(float(v[2]))
            prm.addMilestone(state)
        return PlannerRoadmap(prm=prm, si=self._si, _svc=self._svc)

    def solve(
        self,
        start: np.ndarray,
        goal: np.ndarray,
        roadmap: PlannerRoadmap | None = None,
    ) -> tuple[bool, float]:
        """Plan a path from start to goal.

        Args:
            start:   [x, y, psi]
            goal:    [x, y, psi]
            roadmap: Pre-built PlannerRoadmap from build_roadmap().
                     If provided, queries the roadmap (fast).
                     If None, runs a fresh RRT solve.

        Returns:
            (solved, path_length)
        """
        start = np.asarray(start, dtype=float)
        goal  = np.asarray(goal,  dtype=float)
        self._last_start_psi = float(start[2])

        si = roadmap.si if roadmap is not None else self._si
        self._active_si = si

        pdef, ompl_start, ompl_goal = self._create_pdef(start, goal, si)
        self._check_pdef_validity(pdef, ompl_start, ompl_goal, si)
        self._solution_path = None

        if roadmap is not None:
            solved = self._query_roadmap(roadmap.prm, pdef, si)
        else:
            solved = self._solve_rrt(pdef)

        if not solved:
            return False, 0.0

        self._solution_path = pdef.getSolutionPath()  # type: ignore[attr-defined]
        waypoints = self._extract_waypoints()
        self._last_waypoints: list[list[float]] = waypoints
        if not self._run_bezier_pipeline(waypoints, start, goal):
            return False, 0.0

        return True, self._solution_path.length()  # type: ignore[attr-defined]

    def get_solution(self) -> dict:
        """Return raw trajectory data from the last successful solve() call.

        Returns a dict with keys: 'states' (np.ndarray, shape N+1×3),
        'inputs' (np.ndarray, shape N×2), 'dt' (float).
        """
        if self._opt is None:
            raise RuntimeError("solve() must succeed before get_solution()")
        dt = self.config.Ts
        states_np, actions_np = self._opt.get_trajectory(dt)

        agent_psi  = self._last_start_psi
        flat_psi_0 = float(states_np[0, 2])
        delta_psi  = (flat_psi_0 - agent_psi + math.pi) % (2 * math.pi) - math.pi

        pre_states:  list[np.ndarray] = []
        pre_actions: list[np.ndarray] = []

        if abs(delta_psi) > 0.05:   # ~3°
            n_rot = math.ceil(abs(delta_psi) / (self.config.psi_dot_max * self.config.bezier_safety_factor * dt))
            psi_dot_rot = delta_psi / (n_rot * dt)
            x0, y0 = states_np[0, 0], states_np[0, 1]
            for k in range(n_rot):
                psi_k = agent_psi + k * psi_dot_rot * dt
                pre_states.append(np.array([x0, y0, psi_k]))
                pre_actions.append(np.array([0.0, psi_dot_rot]))

        if pre_actions:
            all_states  = np.vstack([np.array(pre_states), states_np])
            all_actions = np.vstack([np.array(pre_actions), actions_np])
        else:
            all_states  = states_np
            all_actions = actions_np

        return {
            'states': all_states,
            'inputs': all_actions,
            'dt': dt,
            'waypoints': getattr(self, '_last_waypoints', []),
        }

    # ── OMPL helpers ─────────────────────────────────────────────────

    def _create_space(self):
        env_min = [lim[0] for lim in self.limits]
        env_max = [lim[1] for lim in self.limits]

        space = ob.SE2StateSpace()  # type: ignore[attr-defined]
        bounds = ob.RealVectorBounds(2)  # type: ignore[attr-defined]
        for i in range(2):
            bounds.setLow(i, env_min[i])
            bounds.setHigh(i, env_max[i])
        space.setBounds(bounds)
        space.setSubspaceWeight(0, 1.0)
        space.setSubspaceWeight(1, self.config.so_r2_weight)
        return space

    def _create_space_info(self) -> ob.SpaceInformation:  # type: ignore[attr-defined]
        si = ob.SpaceInformation(self._space)  # type: ignore[attr-defined]
        # Store as instance attribute — prevents GC while C++ holds vtable pointer.
        self._svc = FCLStateValidityChecker(si, self._collision_checker)
        si.setStateValidityChecker(self._svc)
        si.setValidStateSamplerAllocator(
            ob.ValidStateSamplerAllocator(ob.UniformValidStateSampler)  # type: ignore[attr-defined]
        )
        return si

    def _create_pdef(
        self,
        start: np.ndarray,
        goal: np.ndarray,
        si: ob.SpaceInformation,  # type: ignore[attr-defined]
    ) -> tuple:
        space = si.getStateSpace()
        ompl_start = space.allocState()
        ompl_goal  = space.allocState()

        ompl_start.setX(float(start[0])); ompl_start.setY(float(start[1])); ompl_start.setYaw(float(start[2]))
        ompl_goal.setX(float(goal[0]));   ompl_goal.setY(float(goal[1]));   ompl_goal.setYaw(float(goal[2]))

        si.enforceBounds(ompl_start)
        si.enforceBounds(ompl_goal)

        pdef = ob.ProblemDefinition(si)  # type: ignore[attr-defined]
        pdef.setStartAndGoalStates(ompl_start, ompl_goal, self.config.goal_eps)
        return pdef, ompl_start, ompl_goal

    def _check_pdef_validity(self, pdef, ompl_start, ompl_goal, si):
        def _fmt(s) -> str:
            return f"(x={s.getX():.3f}, y={s.getY():.3f}, yaw={s.getYaw():.3f})"
        def _bounds() -> str:
            b = si.getStateSpace().getBounds()
            return f"[({b.low[0]:.3f},{b.low[1]:.3f}), ({b.high[0]:.3f},{b.high[1]:.3f})]"

        if not si.satisfiesBounds(ompl_start):
            raise ValueError(f"Start {_fmt(ompl_start)} out of bounds {_bounds()}")
        if not si.satisfiesBounds(ompl_goal):
            raise ValueError(f"Goal {_fmt(ompl_goal)} out of bounds {_bounds()}")
        if not si.isValid(ompl_start):
            raise ValueError(f"Start state {_fmt(ompl_start)} is in collision")
        if not si.isValid(ompl_goal):
            raise ValueError(f"Goal state {_fmt(ompl_goal)} is in collision")

    def _solve_rrt(self, pdef) -> bool:
        """Single-query RRT solve."""
        planner = self._make_rrt_planner(self._si)
        planner.setProblemDefinition(pdef)
        ou.setLogLevel(ou.LogLevel.LOG_NONE)  # type: ignore[attr-defined]
        planner.setup()
        solved = planner.solve(self.config.timelimit)
        return bool(solved and pdef.hasExactSolution())

    def _query_roadmap(self, prm, pdef, si) -> bool:
        """Multi-query PRM* solve using a pre-built roadmap."""
        obj = ob.MultiOptimizationObjective(si)  # type: ignore[attr-defined]
        obj.addObjective(ob.PathLengthOptimizationObjective(si), 1.0)  # type: ignore[attr-defined]
        obj.addObjective(ob.MaximizeMinClearanceObjective(si), 0.5)  # type: ignore[attr-defined]
        pdef.setOptimizationObjective(obj)

        prm.clearQuery()
        prm.setProblemDefinition(pdef)
        solved = prm.solve(ob.timedPlannerTerminationCondition(self.config.query_timelimit))  # type: ignore[attr-defined]
        return bool(solved and pdef.hasExactSolution())

    def _make_rrt_planner(self, si):
        planner_type = self.config.planner
        if planner_type == 'rrt':
            p = og.RRT(si)  # type: ignore[attr-defined]
        elif planner_type == 'rrt*':
            p = og.RRTStar(si)  # type: ignore[attr-defined]
        elif planner_type in ('rrt-connect', 'rrt_connect'):
            p = og.RRTConnect(si)  # type: ignore[attr-defined]
        else:
            raise ValueError(f"Unsupported planner: {planner_type}")
        if hasattr(p, 'setGoalBias'):
            p.setGoalBias(self.config.goal_bias)
        return p

    # RDP perpendicular tolerance and LOS sampling resolution.
    _RDP_EPS: float = 0.03             # RDP perpendicular tolerance — small enough to only remove collinear points
    _LOS_STEP: float = 0.05            # sampling resolution — must be < wall half-width (0.05m)
    _LOS_MIN_CLEARANCE: float = 0.03   # FCL clearance required at every sample (rejects near-misses)

    def _extract_waypoints(self) -> list[list[float]]:
        simplifier = og.PathSimplifier(self._active_si)  # type: ignore[attr-defined]
        simplifier.collapseCloseVertices(self._solution_path)  # type: ignore[attr-defined]
        simplifier.simplifyMax(self._solution_path)  # type: ignore[attr-defined]
        n = self._solution_path.getStateCount()  # type: ignore[attr-defined]
        raw = [
            [self._solution_path.getState(i).getX(),  # type: ignore[attr-defined]
             self._solution_path.getState(i).getY()]
            for i in range(n)
        ]
        return self._los_shortcut(raw)

    def _rdp_simplify(self, waypoints: list[list[float]], eps: float) -> list[list[float]]:
        """Ramer-Douglas-Peucker: remove intermediate points with perp deviation < eps."""
        if len(waypoints) <= 2:
            return waypoints
        start, end = np.array(waypoints[0]), np.array(waypoints[-1])
        chord = end - start
        chord_len = float(np.linalg.norm(chord))
        if chord_len < 1e-9:
            dists = [float(np.linalg.norm(np.array(p) - start)) for p in waypoints[1:-1]]
        else:
            u = chord / chord_len
            dists = [float(np.linalg.norm((np.array(p) - start) - np.dot(np.array(p) - start, u) * u))
                     for p in waypoints[1:-1]]
        max_dist = max(dists)
        max_idx  = dists.index(max_dist) + 1
        if max_dist >= eps:
            left  = self._rdp_simplify(waypoints[:max_idx + 1], eps)
            right = self._rdp_simplify(waypoints[max_idx:], eps)
            return left[:-1] + right
        return [waypoints[0], waypoints[-1]]

    def _los_shortcut(self, waypoints: list[list[float]]) -> list[list[float]]:
        """Remove waypoints where a straight-line A→C shortcut is collision-free.

        Iterates until no further removals are possible.
        """
        pts = list(waypoints)
        changed = True
        while changed:
            changed = False
            i = 0
            while i < len(pts) - 2:
                if self._check_los(pts[i], pts[i + 2]):
                    del pts[i + 1]
                    changed = True
                else:
                    i += 1
        return pts

    def _check_los(self, a: list[float], c: list[float]) -> bool:
        dx, dy = c[0] - a[0], c[1] - a[1]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1e-6:
            return True
        psi = math.atan2(dy, dx)
        n_steps = max(2, int(dist / self._LOS_STEP) + 1)
        for k in range(n_steps + 1):
            t = k / n_steps
            x, y = a[0] + t * dx, a[1] + t * dy
            clearance = self._collision_checker.clearance_for_state(x, y, psi)
            if clearance < self._LOS_MIN_CLEARANCE:
                return False
        return True

    # ── Bézier pipeline ───────────────────────────────────────────────

    def _run_bezier_pipeline(
        self, waypoints: list[list[float]], start: np.ndarray, goal: np.ndarray
    ) -> bool:
        sf = self.config.bezier_safety_factor
        self._opt = FRODOFlatOpt(
            self._build_opt_data(waypoints, start, goal),
            dt=self.config.Ts,
            v_max=self.config.v_max * sf,
            psi_dot_max=self.config.psi_dot_max * sf,
        )
        self._opt.find_hyperplanes()
        self._opt.create_optimization_vars()
        self._opt.create_bezier()
        if not self._opt.feasible:
            return False
        self._opt.bezier_to_configurations()
        return True

    def _build_opt_data(
        self, waypoints: list[list[float]], start: np.ndarray, goal: np.ndarray
    ) -> OptimizationData:
        """Build OptimizationData from raw environment data.

        Obstacles are converted to axis-aligned bounding boxes (AABBs).
        AABB formula for a rotated rectangle:
            half_x = |cos ψ| · L/2  +  |sin ψ| · W/2
            half_y = |sin ψ| · L/2  +  |cos ψ| · W/2
        """
        def _aabb(obs: dict) -> list[float]:
            psi = float(obs['psi'])
            cos_a, sin_a = abs(np.cos(psi)), abs(np.sin(psi))
            hw = obs['length'] / 2 * cos_a + obs['width'] / 2 * sin_a
            hh = obs['length'] / 2 * sin_a + obs['width'] / 2 * cos_a
            return [obs['x'] - hw, obs['x'] + hw, obs['y'] - hh, obs['y'] + hh]

        return OptimizationData(
            bound_min=[self.limits[0][0], self.limits[1][0]],
            bound_high=[self.limits[0][1], self.limits[1][1]],
            start=[float(start[0]), float(start[1])],
            goal=[float(goal[0]),   float(goal[1])],
            path=waypoints,
            obstacles=[_aabb(obs) for obs in self.obstacles],
            start_psi=float(start[2]),
        )


class RoadmapBuilder:
    """Builds a PRM* roadmap for a static environment, shareable across agents.

    Keeps the underlying planner alive so the SI/SVC aren't GC'd while the
    returned PlannerRoadmap is in use.

    Typical usage (RL scenario or multi-agent sim)::

        builder = RoadmapBuilder(limits, obs_dicts, agent_dims)
        prm = builder.build()          # ~30 s once per episode layout

        for agent in agents:
            agent.planner.plan(goal_task, roadmap=prm)
    """

    def __init__(
        self,
        limits: tuple,
        obstacles: list[dict],
        agent_dims: tuple[float, float, float],
        config: OMPLPlannerConfig | None = None,
    ):
        self._planner = OMPLSmoothPathPlanner(limits, obstacles, agent_dims, config)

    def build(self) -> PlannerRoadmap:
        """Grow a PRM* roadmap and return it.  May be called multiple times to rebuild."""
        return self._planner.build_roadmap()
