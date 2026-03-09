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
from ompl import control as oc
from ompl import util as ou # used to supress OMPL outputs
from typing import Any
from numpy.typing import NDArray
from enum import Enum, auto
from abc import ABC, abstractmethod
from ompl.base import PathLengthOptimizationObjective
from typing import List

import math
import numpy as np
import argparse

from master_thesis.modules.motion_planning.helper.nearest_neighbor import NearestNeighbor # TODO: Use scikit-learn kd tree here
from master_thesis.modules.motion_planning.helper.collisions_fcl import AgentCollisionChecker
from master_thesis.modules.motion_planning.helper.opt_safe import FRODOFlatOpt, OptimizationData

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.local_world_container import LocalWorldContainer
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer
from master_thesis.containers.module_containers.mp_containers.mp_phase_container import MPPhaseContainer, MPPhaseConfig


class FCLStateValidityChecker(ob.StateValidityChecker):  # type: ignore[misc]
    """Class-based SVC so OMPL can invoke clearance() for MaximizeMinClearanceObjective."""

    def __init__(self, si: ob.SpaceInformation, checker: "AgentCollisionChecker"):  # type: ignore[attr-defined]
        super().__init__(si)
        self._checker = checker

    def isValid(self, state) -> bool:
        return self._checker.check_state_ompl(state)

    def clearance(self, state) -> float:
        return self._checker.clearance_for_state(
            state.getX(), state.getY(), state.getYaw()
        )


class SamplerType(Enum):
    UNIFORM = ob.UniformValidStateSampler # type: ignore[attr-defined]
    GAUSSIAN = ob.GaussianValidStateSampler # type: ignore[attr-defined]
    OBSTACLE = ob.ObstacleBasedValidStateSampler # type: ignore[attr-defined]
    BRIDGE = ob.BridgeTestValidStateSampler # type: ignore[attr-defined]

    @classmethod
    def from_string(cls, name: str):
        key = name.strip().upper()
        try: 
            return cls[key]
        except KeyError:
            raise ValueError(f"Invalid sampler type: {name}. Valid options: {[e.name for e in cls]}") from None

    def __call__(self, si: ob.SpaceInformation) -> ob.ValidStateSampler: # type: ignore[attr-defined]
        return self.value(si)

    
class OMPLPlannerFRODOBase(ABC):
    def __init__(self, mp_container: AgentMPPlannerContainer,
                 agent_container: FRODOAgentContainer,
                 lwr_container: LocalWorldContainer,
                 sampler: SamplerType = SamplerType.UNIFORM):

        self.mp_container = mp_container
        self.agent_container = agent_container
        self.sampler = sampler
        self.lwr_container = lwr_container

        # self._solution_exporter = SolutionExporter(self.agent_type, path_out_yaml, path_out_tree)
        self._collision_checker = self._create_checker()
        self.ompl_setup()
    
    def _get_state_sampler(self, si):
        try:
            sampler = SamplerType.from_string(self.mp_container.sampler)
        except AttributeError:
            print("No sampler type specified, using default UniformValidStateSampler")
            sampler = SamplerType.UNIFORM.value(si)
        return sampler
        
    def ompl_setup(self):
        self._space = self._create_space()
        self._si = self._create_space_info()
        # self._pdef = self._create_pdef()
        
        # self._planner = self.create_planner()

    @abstractmethod
    def select_planner_type(self, si) -> Any:
        ...

    def create_planner(self):
        # create a planner for the defined space
        planner = self.select_planner_type(self._si)
        # set the problem we are trying to solve for the planner
        planner.setProblemDefinition(self._pdef)

        if hasattr(planner, "setGoalBias"):
            planner.setGoalBias(self.mp_container.goal_bias)
        else:
            print("Planner does not support goal bias, skipping setting it.")
        # surpress OMPL log outputs
        ou.setLogLevel(ou.LogLevel.LOG_NONE)
        # perform setup steps for the planner
        planner.setup()
        return planner
        
    def _create_pdef(self):
        # Allocate two independent state objects
        self._start = self._space.allocState() # type: ignore[attr-defined]
        self._goal  = self._space.allocState() # type: ignore[attr-defined]


        # SE2StateSpace: must use setters
        start_x, start_y, s_psi = self.mp_container.start
        goal_x, goal_y, goal_psi = self.mp_container.goal
        self._start.setX(float(start_x))
        self._start.setY(float(start_y))
        self._start.setYaw(float(s_psi))
        self._goal.setX(float(goal_x))
        self._goal.setY(float(goal_y))
        self._goal.setYaw(float(goal_psi))

        # Build the ProblemDefinition
        pdef = ob.ProblemDefinition(self._si)  # type: ignore[attr-defined]
        self._si.enforceBounds(self._start)
        self._si.enforceBounds(self._goal)
        # pdef.setStartAndGoalStates(self._start, self._goal,
        #                            self.planning_config.goal_eps)
  
        pdef.setStartAndGoalStates(self._start, self._goal,
                                   self.mp_container.goal_eps)
        pdef.setOptimizationObjective(
            ob.PathLengthOptimizationObjective(self._si)  # type: ignore[attr-defined]
        )
        return pdef
    
    def _print_state_frodo(self, state) -> str:
        # Cast to SE2StateSpace.StateType
        se2_state = state.get() if hasattr(state, "get") else state
        return f"(x={se2_state.getX():.3f}, y={se2_state.getY():.3f}, yaw={se2_state.getYaw():.3f})"

    def _print_bounds(self):
        b = self._si.getStateSpace().getBounds()
        return f"Bounds: [({b.low[0]:.3f}, {b.low[1]:.3f}), ({b.high[0]:.3f}, {b.high[1]:.3f})]"

    def check_pdef_validity(self):
        # Bounds checks against the SI used by the planner
        if not self._si.satisfiesBounds(self._start):
            raise ValueError(f"Invalid ProblemDefinition: Start state: {self._print_state_frodo(self._start)} is out of bounds: {self._print_bounds()}.")
        if not self._si.satisfiesBounds(self._goal):
            raise ValueError(f"Invalid ProblemDefinition: Goal state: {self._print_state_frodo(self._goal)} is out of bounds: {self._print_bounds()}.")

        # Validity checks via the state validity checker
        if not self._si.isValid(self._start):
            raise ValueError("Invalid ProblemDefinition: Start state is invalid.")
        if not self._si.isValid(self._goal):
            raise ValueError("Invalid ProblemDefinition: Goal state is invalid.")

    @abstractmethod
    def solve_problem(self, verbose = False) -> tuple[bool, float]:

        ...

    @property
    def _solution_path_states(self) -> tuple[np.ndarray, ...]:
        path_states = []
        for i in range(self._solution_path.getStateCount()): # type: ignore[attr-defined]
            assert self._solution_path is not None, "No solution path currently available, must be computed first!"
            ompl_state = self._solution_path.getState(i)
            self._si.enforceBounds(ompl_state)
            extracted_state = self._extract_ompl_state(ompl_state)
            path_states.append(extracted_state)
        return tuple(path_states)

    @abstractmethod
    def _create_space_info(self) -> ob.SpaceInformation: # type: ignore[attr-defined]
        ...

    def _create_space(self):
        # Extract limits from local world container config
        env_min = []
        env_max = []

        for limit in self.lwr_container.config.limits:
            env_min.append(limit[0])
            env_max.append(limit[1])

        space = ob.SE2StateSpace() # type: ignore[attr-defined]
        # only for the car, we need the bounds since SE2 is already bounded 0,2pi
        bounds = ob.RealVectorBounds(2) # type: ignore[attr-defined]
        # set lower and upper bounds
        for i in range(2):
            bounds.setLow(i, env_min[i])
            bounds.setHigh(i, env_max[i])
        space.setBounds(bounds)

        space.setSubspaceWeight(0, 1.0)  # set R2 weight to 1.0
        space.setSubspaceWeight(1, self.mp_container.so_r2_weight)
        return space

    def _extract_ompl_state(self, ompl_state) -> list:
        x = ompl_state.getX()
        y = ompl_state.getY()
        yaw = ompl_state.getYaw()
        return [float(x), float(y), float(yaw)]

    @abstractmethod
    def _create_solution_cont(self) -> MPPhaseContainer:
        ...

    def getCost(self, si: ob.SpaceInformation) -> ob.OptimizationObjective: # type: ignore[attr-defined]
        """
        Return the optimization objective to minimize path length.
        Called by the benchmark setup.
        """
        return PathLengthOptimizationObjective(si)
    
    def _create_checker(self):
        L, W, H = self.agent_container.length, self.agent_container.width, self.agent_container.height
        if L is None or W is None or H is None or L <= 0 or W <= 0 or H <= 0:
            raise ValueError("Dimensions L, W, H must be provided for FRODO collision checking and must be valid positive numbers.")

        checker = AgentCollisionChecker(lwr_container=self.lwr_container, agent_container=self.agent_container)
        checker.initialize_env_manager(self.lwr_container)
        return checker
    

class OMPLPlannerFRODOKino(OMPLPlannerFRODOBase):
    def __init__(self, mp_container: AgentMPPlannerContainer,
                 agent_container: FRODOAgentContainer,
                 lwr_container: LocalWorldContainer,
                 sampler: SamplerType = SamplerType.UNIFORM):

        super().__init__(mp_container=mp_container, agent_container=agent_container, lwr_container=lwr_container, sampler=sampler)
    
    def select_planner_type(self, si) -> Any:
        try:
            self.planner_type = self.mp_container.planner
            if self.planner_type == "rrt":
                return oc.RRT(si) # type: ignore[attr-defined]
            elif self.planner_type == "sst":
                return oc.SST(si) # type: ignore[attr-defined]
            else:
                raise ValueError(f"Unsupported planner type for the motion problem: {self.planner_type}")
        except AttributeError:
            print("No planner type specified, using default RRT")
            return oc.RRT(si) # type: ignore[attr-defined]
    
    def _state_propagator(self, start, control, duration, target):
        # extract individual controls
        s = control[0] 
        psi_dot = control[1] 

        # get current configuration
        x = start.getX()
        y = start.getY()
        psi = start.getYaw()

        # calculate delta_state
        dx = s * np.cos(psi) * duration
        dy = s * np.sin(psi) * duration
        dtheta = psi_dot*duration

        # apply delta state
        target.setX(x + dx)
        target.setY(y + dy)
        target.setYaw(psi + dtheta)

        return target
    
    def _create_space_info(self) -> ob.SpaceInformation: # type: ignore[attr-defined]
        self._control_space = oc.RealVectorControlSpace(self._space, 2) # type: ignore[attr-defined]
        control_bounds = ob.RealVectorBounds(2) # type: ignore[attr-defined]
        v_lo, v_hi = self.mp_container.v_bounds
        w_lo, w_hi = self.mp_container.theta_dot_bounds
        control_bounds.setLow(0, v_lo)
        control_bounds.setHigh(0, v_hi)
        control_bounds.setLow(1, w_lo)
        control_bounds.setHigh(1, w_hi)
        self._control_space.setBounds(control_bounds)

        # Space information for (collision checking, interpolation, etc.)
        si = oc.SpaceInformation(self._space, self._control_space) # type: ignore[attr-defined]
        # set state validity checking for this space
        si.setStateValidityChecker(ob.StateValidityCheckerFn(self._collision_checker.check_state_ompl)) # type: ignore[attr-defined]
        # set the state sampler for this space
        si.setValidStateSamplerAllocator(ob.ValidStateSamplerAllocator(self._get_state_sampler)) # type: ignore[attr-defined]
        si.setStatePropagator(oc.StatePropagatorFn(self._state_propagator))  # type: ignore[attr-defined]
        
        # Set min and max duration for the planning, always have max duration #timesteps equal one second
        min_duration = 1
        max_duration = int(1.0 / self.agent_container.Ts)
        assert(min_duration <= max_duration)
        si.setMinMaxControlDuration(min_duration, max_duration) # TODO: keep it like this? 
        si.setPropagationStepSize(self.agent_container.Ts)

        return si

    @property
    def _solution_inputs_durations(self, verbose = False) -> tuple[tuple[NDArray, ...], tuple[int, ...]]:
        # get the number of inputs in the solution path
        no_inputs = self._solution_path.getControlCount() # type: ignore[attr-defined]

        if verbose:
            print(f'this is the step size: {self._si.getPropagationStepSize()}')
            print(no_inputs)

        inputs: list[NDArray] = []
        durations: list[int] = []

        # loop through all inputs, get input and duration it is applied
        for i in range(no_inputs):
            # extract control inputs
            c = self._solution_path.getControl(i) # type: ignore[attr-defined]
            s = float(c[0])
            theta = float(c[1])
            # Get the duration (number of timesteps) each input is applied

            dur_in_time = self._solution_path.getControlDuration(i) # type: ignore[attr-defined]

            inputs.append(np.array([s, theta]))
            durations.append(dur_in_time)

        return tuple(inputs), tuple(durations)
    
    def _create_solution_cont(self)-> MPPhaseContainer:
        path_states = self._solution_path_states
        path_actions, path_durations = self._solution_inputs_durations

        config = MPPhaseConfig(
            inputs = path_actions,
            states = path_states,
            durations = path_durations,
            delta_t= self.agent_container.Ts
        )
        
        cont = MPPhaseContainer(config=config)

        return cont
    
    def solve_problem(self, verbose = False) -> tuple[bool, float]:
        self._pdef = self._create_pdef() # update the pdef with current start goal from the container
        self._planner = self.create_planner() # TODO: This should not have to be recreated each time?
        self._planner.setProblemDefinition(self._pdef) # tell the planner about the new problem definition
        self.check_pdef_validity()
        self._solution_path = None

        solved = self._planner.solve(self.mp_container.timelimit)
        exact = self._pdef.hasExactSolution() # type: ignore[attr-defined]
        approx = self._pdef.hasApproximateSolution() # type: ignore[attr-defined]

        if verbose:
            print(f"Solved: {solved}, Exact: {exact}, Approx: {approx}")

        if solved:
            self._solution_path = self._pdef.getSolutionPath()
            path_length = self._solution_path.length()
            return True, path_length
            # Print a concise summary instead of the full path details
            # num_states = self._solution_path.getStateCount()  # type: ignore[attr-defined]
            # path_length = self._solution_path.length()       # type: ignore[attr-defined]
            # print(f"Found solution with {num_states} states, total length {path_length:.3f}") # TODO: Put this into logger
        
        return False, 0

class OMPLSmoothPathPlanner(OMPLPlannerFRODOBase):
    """Geometric OMPL planner + Bézier flat-output post-processor for FRODO.

    Pipeline
    --------
    1. OMPL og.RRT (geometric) → list of (x, y) waypoints
    2. FRODOFlatOpt:
       a. find_hyperplanes()          — SVM safe-region per path segment
       b. create_bezier()             — cvxpy min-length optimisation s.t. SVM + C²
       c. bezier_to_configurations()  — flat-output inversion + temporal scaling
    3. _create_solution_cont()        — pack into MPPhaseContainer

    Control bounds are read from AgentMPPlannerConfig (single source of truth).
    """

    # ── Shared PRM roadmap (class-level) ──────────────────────────────────────
    # Built once by the first agent that plans; reused by all subsequent agents
    # in the same environment.  Invalidated when the static environment changes.
    _shared_prm: Any = None
    _shared_si:  Any = None
    # Explicit Python-level reference to the SVC so it is never GC'd while the
    # shared SI (and therefore the shared PRM) is alive.  boost::python virtual
    # dispatch on a GC'd Python subclass causes SIGSEGV.
    _shared_svc: Any = None

    @classmethod
    def invalidate_roadmap(cls) -> None:
        """Discard the shared roadmap (call when the static environment changes)."""
        cls._shared_prm = None
        cls._shared_si  = None
        cls._shared_svc = None

    def __init__(self, mp_container: AgentMPPlannerContainer,
                 agent_container: FRODOAgentContainer,
                 lwr_container: LocalWorldContainer,
                 sampler: SamplerType = SamplerType.UNIFORM):

        super().__init__(mp_container=mp_container, agent_container=agent_container,
                         lwr_container=lwr_container, sampler=sampler)
        self._opt: FRODOFlatOpt | None = None

    def select_planner_type(self, si) -> Any:
        try:
            self.planner_type = self.mp_container.planner
            if self.planner_type == "rrt":
                return og.RRT(si)  # type: ignore[attr-defined]
            elif self.planner_type == "rrt*":
                return og.RRTStar(si)  # type: ignore[attr-defined]
            elif self.planner_type == "rrt-connect":
                return og.RRTConnect(si)  # type: ignore[attr-defined]
            else:
                raise ValueError(f"Unsupported planner type: {self.planner_type}")
        except (AttributeError, KeyError):
            return og.RRT(si)  # type: ignore[attr-defined]

    def _create_space_info(self) -> ob.SpaceInformation:  # type: ignore[attr-defined]
        si = ob.SpaceInformation(self._space)  # type: ignore[attr-defined]
        # Store SVC as instance attribute so the Python object is not GC'd while
        # the C++ SI holds a raw vtable pointer into it (boost::python SIGSEGV).
        self._svc = FCLStateValidityChecker(si, self._collision_checker)
        si.setStateValidityChecker(self._svc)
        si.setValidStateSamplerAllocator(
            ob.ValidStateSamplerAllocator(self.sampler)  # type: ignore[attr-defined]
        )
        return si

    def _build_opt_data(self, waypoints: list[list[float]]) -> OptimizationData:
        """Convert simulation state into OptimizationData for FRODOFlatOpt.

        Obstacles are given as axis-aligned bounding boxes (AABBs) computed
        from the obstacle's actual yaw.

        AABB formula for a 2-D rotated rectangle (standard tight AABB):
            half_x = |cos(ψ)| · L/2  +  |sin(ψ)| · W/2
            half_y = |sin(ψ)| · L/2  +  |cos(ψ)| · W/2
        """
        lims = self.lwr_container.config.limits

        def _aabb(container) -> list[float]:
            psi = float(container.psi)
            cos_a = abs(np.cos(psi))
            sin_a = abs(np.sin(psi))
            hw = container.length / 2 * cos_a + container.width / 2 * sin_a
            hh = container.length / 2 * sin_a + container.width / 2 * cos_a
            return [container.x - hw, container.x + hw, container.y - hh, container.y + hh]

        obstacles = []
        for obs in self.lwr_container.state.obstacles.values():
            obstacles.append(_aabb(obs))

        return OptimizationData(
            bound_min=[lims[0][0], lims[1][0]],
            bound_high=[lims[0][1], lims[1][1]],
            start=[float(self.mp_container.start[0]), float(self.mp_container.start[1])],
            goal=[float(self.mp_container.goal[0]),  float(self.mp_container.goal[1])],
            path=waypoints,
            obstacles=obstacles,
            start_psi=float(self.mp_container.start[2]),
        )

    def _extract_waypoints(self) -> list[list[float]]:
        """Simplify solution path and return waypoints as [[x, y], ...]."""
        simplifier = og.PathSimplifier(self._si)  # type: ignore[attr-defined]
        # Collapse near-duplicate nodes first (common in PRM* paths), then simplify.
        simplifier.collapseCloseVertices(self._solution_path)  # type: ignore[attr-defined]
        simplifier.simplifyMax(self._solution_path)  # type: ignore[attr-defined]
        n = self._solution_path.getStateCount()
        return [
            [self._solution_path.getState(i).getX(),
             self._solution_path.getState(i).getY()]
            for i in range(n)
        ]

    def _run_bezier_pipeline(self, waypoints: list[list[float]]) -> bool:
        """Run Bézier SVM optimisation + TOPP on waypoints. Returns feasibility."""
        _, v_hi = self.mp_container.v_bounds
        _, w_hi = self.mp_container.theta_dot_bounds
        self._opt = FRODOFlatOpt(
            self._build_opt_data(waypoints),
            dt=self.agent_container.Ts,
            v_max=v_hi,
            psi_dot_max=w_hi,
        )
        self._opt.find_hyperplanes()
        self._opt.create_optimization_vars()
        self._opt.create_bezier()
        if not self._opt.feasible:
            return False
        self._opt.bezier_to_configurations()
        return True

    def solve_problem(self, verbose: bool = False,
                      use_prm: bool = False) -> tuple[bool, float]:
        if use_prm:
            return self._solve_prm()
        return self._solve_rrt()

    def _solve_rrt(self) -> tuple[bool, float]:
        """Single-query RRT-based solve (used for replanning with frozen agents)."""
        self._pdef = self._create_pdef()
        self._planner = self.create_planner()
        self._planner.setProblemDefinition(self._pdef)
        self.check_pdef_validity()
        self._solution_path = None

        solved = self._planner.solve(self.mp_container.timelimit)
        if not solved or not self._pdef.hasExactSolution():  # type: ignore[attr-defined]
            return False, 0

        self._solution_path = self._pdef.getSolutionPath()
        waypoints = self._extract_waypoints()
        if not self._run_bezier_pipeline(waypoints):
            return False, 0
        return True, self._solution_path.length()

    def _solve_prm(self) -> tuple[bool, float]:
        """Multi-query PRM* solve (used for initial plans against static env).

        The roadmap is shared across all OMPLSmoothPathPlanner instances (class-level).
        The first agent builds it; subsequent agents reuse it via clearQuery().
        A combined termination condition exits as soon as a path is found, making
        per-query latency independent of the roadmap growth budget.
        """
        cls = OMPLSmoothPathPlanner

        if cls._shared_prm is None:
            # First planner to run: build roadmap using this instance's SI.
            self._si.setup()  # type: ignore[attr-defined]
            cls._shared_si  = self._si
            cls._shared_svc = self._svc   # pin Python object → no GC while PRM lives
            cls._shared_prm = og.PRMstar(self._si)  # type: ignore[attr-defined]
            time_budget = self.mp_container.roadmap_time
        else:
            # Reuse the shared SI so the pdef is compatible with the existing PRM.
            self._si    = cls._shared_si
            self._space = cls._shared_si.getStateSpace()
            cls._shared_prm.clearQuery()
            time_budget = self.mp_container.timelimit

        self._pdef = self._create_pdef()
        self.check_pdef_validity()
        self._solution_path = None

        # Clearance-weighted objective: prefer paths away from walls.
        obj = ob.MultiOptimizationObjective(self._si)  # type: ignore[attr-defined]
        obj.addObjective(ob.PathLengthOptimizationObjective(self._si), 1.0)  # type: ignore[attr-defined]
        obj.addObjective(ob.MaximizeMinClearanceObjective(self._si), 0.5)  # type: ignore[attr-defined]
        self._pdef.setOptimizationObjective(obj)

        cls._shared_prm.setProblemDefinition(self._pdef)

        # PRM* adds solutions only after its main loop ends, so the timer is the
        # only effective termination condition.  Use the full budget on first call
        # (roadmap_time) and a short query limit on subsequent calls (timelimit).
        solved = cls._shared_prm.solve(ob.timedPlannerTerminationCondition(time_budget))  # type: ignore[attr-defined]

        if not solved or not self._pdef.hasExactSolution():  # type: ignore[attr-defined]
            return False, 0

        self._solution_path = self._pdef.getSolutionPath()
        waypoints = self._extract_waypoints()
        if not self._run_bezier_pipeline(waypoints):
            return False, 0
        return True, self._solution_path.length()

    def _create_solution_cont(self) -> MPPhaseContainer:
        if self._opt is None:
            raise RuntimeError("solve_problem() must succeed before _create_solution_cont()")

        dt = self.agent_container.Ts
        states_np, actions_np = self._opt.get_trajectory(dt)

        # Pre-rotation: align agent heading with the Bézier's initial tangent direction.
        #
        # Without the heading constraint in create_bezier(), the Bézier's initial
        # tangent (psi = atan2(dot_y(0), dot_x(0))) may differ from the agent's
        # actual heading.  We prepend spin-in-place steps (v=0, constant psi_dot)
        # to rotate the agent to the Bézier's starting direction before forward
        # motion begins.  This keeps flat-output inversion exact from step 1.
        agent_psi   = float(self.agent_container.psi)
        flat_psi_0  = float(states_np[0, 2])
        delta_psi   = (flat_psi_0 - agent_psi + math.pi) % (2 * math.pi) - math.pi

        _, psi_dot_max = self.mp_container.theta_dot_bounds

        pre_states:  list[np.ndarray] = []
        pre_actions: list[np.ndarray] = []

        if abs(delta_psi) > 0.05:   # threshold ~3°
            n_rot       = math.ceil(abs(delta_psi) / (psi_dot_max * dt))
            psi_dot_rot = delta_psi / (n_rot * dt)   # exact rate to reach flat_psi_0
            x0, y0      = states_np[0, 0], states_np[0, 1]
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

        N = len(all_actions)
        config = MPPhaseConfig(
            inputs=list(all_actions),    # N × [v, psi_dot]
            states=list(all_states),     # (N+1) × [x, y, psi]
            durations=[dt] * N,          # each input applied for exactly one Ts tick
            delta_t=dt,
        )
        return MPPhaseContainer(config=config)


if __name__ == "__main__":
    import matplotlib.pyplot as plt

    from master_thesis.modules.motion_planning.helper.opt_safe import Plotter

    from master_thesis.containers.general_containers.frodo_agent_container import (
        FRODOAgentContainer, FRODO_AgentState, FRODO_Agent_Config,
    )
    from master_thesis.containers.module_containers.mp_containers.mp_planner_container import (
        AgentMPPlannerContainer, AgentMPPlannerConfig,
    )
    from master_thesis.containers.general_containers.local_world_container import (
        LocalWorldContainer, LocalWorldConfig, LocalWorldState,
    )
    from master_thesis.containers.general_containers.obstacle_container import (
        ObstacleContainer, Obstacle_Config,
    )

    # ── Scenario ──────────────────────────────────────────────────────────────
    limits = ((0.0, 3.0), (-1.0, 1.0))
    start  = np.array([0.25,  0.75, 0.0])
    goal   = np.array([2.75, -0.75, 0.0])

    walls = [
        dict(id='wall-1', x=2.5,  y=-0.5,  length=1.0, width=0.05, psi=-np.pi    ),
        dict(id='wall-2', x=1.5,  y=-0.5,  length=1.0, width=0.05, psi=-np.pi/2  ),
        dict(id='wall-3', x=0.5,  y=-0.25, length=0.5, width=0.05, psi=-np.pi/2  ),
        dict(id='wall-4', x=0.75, y=-0.5,  length=0.5, width=0.05, psi=0.0       ),
        dict(id='wall-5', x=1.0,  y=0.5,   length=1.0, width=0.05, psi=np.pi/2   ),
        dict(id='wall-6', x=0.25, y=-0.5,  length=0.5, width=0.05, psi=-np.pi    ),
        dict(id='wall-7', x=2.5,  y=0.0,   length=1.0, width=0.05, psi=0.0       ),
        dict(id='wall-8', x=1.75, y=0.75,  length=0.5, width=0.05, psi=-np.pi/2  ),
    ]

    # ── Containers ────────────────────────────────────────────────────────────
    agent_cont = FRODOAgentContainer(
        agent_id='frodo-1',
        config=FRODO_Agent_Config(Ts=0.1),
        state=FRODO_AgentState(x=start[0], y=start[1], v=0.0, psi=start[2], psi_dot=0.0),
    )

    mp_cont = AgentMPPlannerContainer(config=AgentMPPlannerConfig(timelimit=10.0))
    mp_cont.start = start
    mp_cont.goal  = goal

    obs_dict = {
        w['id']: ObstacleContainer(
            object_id=w['id'],
            config=Obstacle_Config(x=w['x'], y=w['y'], psi=w['psi'],
                                   length=w['length'], width=w['width']),
        )
        for w in walls
    }
    lwr_cont = LocalWorldContainer(
        config=LocalWorldConfig(limits=limits),
        state=LocalWorldState(obstacles=obs_dict),
    )

    # ── Plan ──────────────────────────────────────────────────────────────────
    planner = OMPLSmoothPathPlanner(
        mp_container=mp_cont,
        agent_container=agent_cont,
        lwr_container=lwr_cont,
    )

    solved, length = planner.solve_problem()
    if not solved:
        print("Planning failed")
        raise SystemExit(1)

    print(f"Solved! geometric path length: {length:.3f} m")
    solution = planner._create_solution_cont()

    states  = np.array(solution.config.states)   # (N+1, 3)  [x, y, psi]
    actions = np.array(solution.config.inputs)   # (N,   2)  [v, psi_dot]
    t       = np.cumsum([0.0] + list(solution.config.durations))

    print(f"Steps: {len(actions)},  T = {t[-1]:.2f} s")
    print(f"v    [{actions[:,0].min():.3f}, {actions[:,0].max():.3f}] m/s")
    print(f"ψ̇   [{actions[:,1].min():.3f}, {actions[:,1].max():.3f}] rad/s")

    # ── Plot ──────────────────────────────────────────────────────────────────
    opt = planner._opt
    fig, (ax_path, ax_ctrl) = plt.subplots(1, 2, figsize=(12, 5))

    ax_path.set_title('Planned trajectory')
    ax_path.set_aspect('equal')
    ax_path.grid(True, alpha=0.3)
    Plotter.assignment04_plot(ax_path, opt.setup, opt.curve_function_segments, opt.hyperplanes)
    ax_path.plot(states[:, 0], states[:, 1], 'b-', lw=1.5, label='trajectory')
    ax_path.plot(*start[:2], 'go', ms=8, label='start')
    ax_path.plot(*goal[:2],  'r*', ms=10, label='goal')
    ax_path.legend()

    ax_ctrl.set_title('Control inputs')
    ax_ctrl.step(t[:-1], actions[:, 0], where='post', label='v [m/s]')
    ax_ctrl.step(t[:-1], actions[:, 1], where='post', label='ψ̇ [rad/s]')
    ax_ctrl.set_xlabel('time [s]')
    ax_ctrl.legend()
    ax_ctrl.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()

