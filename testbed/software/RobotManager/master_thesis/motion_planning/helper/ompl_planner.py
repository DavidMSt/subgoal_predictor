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
from master_thesis.motion_planning.helper.nearest_neighbor import NearestNeighbor # TODO: Use scikit-learn kd tree here
from master_thesis.motion_planning.helper.collisions_fcl import AgentCollisionChecker
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.containers.mp_container import AgentMPContainer

from enum import Enum, auto
from abc import ABC, abstractmethod
from ompl.base import PathLengthOptimizationObjective
from typing import List


import numpy as np
import argparse


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
    def __init__(self, mp_container: AgentMPContainer, 
                 agent_container: FRODOAgentContainer, 
                 env_container: EnvironmentContainer, 
                 sampler: SamplerType = SamplerType.UNIFORM):
        
        self.mp_container = mp_container
        self.agent_container = agent_container
        self.sampler = sampler
        self.env_container = env_container

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
        self._pdef = self._create_pdef()
        self._planner = self.create_planner()

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

    def export_solution_dict(self) -> dict[str, tuple[np.ndarray, ...]]:
        return self._create_solution_dict()

    @abstractmethod
    def _create_space_info(self) -> ob.SpaceInformation: # type: ignore[attr-defined]
        ...

    def _create_space(self):
        # extract limits of the environment
        env_min = []
        env_max = []

        for limit in self.env_container.limits:
            env_min.append(limit[0])
            env_max.append(limit[1])

        space = ob.SE2StateSpace() # type: ignore[attr-defined]
        # only for the car, we need the bounds since SE2 is already bounded 0,2pi
        bounds = ob.RealVectorBounds(2) # type: ignore[attr-defined]
        # set lower and upper bounds
        for i in range(2):
            # bounds.setLow(i, self.config.env_min[i])
            # bounds.setHigh(i, self.config.env_max[i])
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
    def _create_solution_dict(self) -> dict[str, tuple[np.ndarray, ...]| float]:
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

        checker = AgentCollisionChecker(env_container = self.env_container, agent_container=self.agent_container)
        checker.initialize_env_manager(self.env_container)
        return checker
    

class OMPLPlannerFRODOKino(OMPLPlannerFRODOBase):
    def __init__(self, mp_container: AgentMPContainer, 
                 agent_container: FRODOAgentContainer, 
                 env_container: EnvironmentContainer, 
                 sampler: SamplerType = SamplerType.UNIFORM):
        
        super().__init__(mp_container=mp_container, agent_container=agent_container, env_container=env_container, sampler=sampler)
    
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
        control_bounds.setLow(0, -1)
        control_bounds.setHigh(0, +1) 
        control_bounds.setLow(1, -np.pi / 3) # TODO: how fast should i allow here? 
        control_bounds.setHigh(1, +np.pi / 3)
        self._control_space.setBounds(control_bounds)

        # Space information for (collision checking, interpolation, etc.)
        si = oc.SpaceInformation(self._space, self._control_space) # type: ignore[attr-defined]
        # set state validity checking for this space
        si.setStateValidityChecker(ob.StateValidityCheckerFn(self._collision_checker.check_state_ompl)) # type: ignore[attr-defined]
        # set the state sampler for this space
        si.setValidStateSamplerAllocator(ob.ValidStateSamplerAllocator(self._get_state_sampler)) # type: ignore[attr-defined]
        si.setStatePropagator(oc.StatePropagatorFn(self._state_propagator))  # type: ignore[attr-defined]
        si.setMinMaxControlDuration(1, 1)
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

            dur = self._solution_path.getControlDuration(i) # type: ignore[attr-defined]

            inputs.append(np.array([s, theta]))
            durations.append(dur)

        return tuple(inputs), tuple(durations)
    
    # def _extract_ompl_state(self, ompl_state) -> list:
    #     x = ompl_state.getX()
    #     y = ompl_state.getY()
    #     yaw = ompl_state.getYaw()
    #     return [float(x), float(y), float(yaw)]
    
    def _create_solution_dict(self)-> dict[str, tuple[np.ndarray, ...]| float]:
        path_states = self._solution_path_states
        path_actions, path_durations = self._solution_inputs_durations

        # print(f'these are inputs and durations: {path_actions}, {path_durations}')
        solution_dict = {
            "states": path_states,
            "actions": path_actions,
            "durations": path_durations,
            "delta_t": self.agent_container.Ts
        }
        return solution_dict
    
    def solve_problem(self, verbose = False) -> tuple[bool, float]:

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

class OMPLPlannerFRODOGeo(OMPLPlannerFRODOBase):

    def __init__(self, mp_container: AgentMPContainer, 
                 agent_container: FRODOAgentContainer, 
                 env_container: EnvironmentContainer, 
                 sampler: SamplerType = SamplerType.UNIFORM):
        
        super().__init__(mp_container = mp_container, agent_container=agent_container, env_container = env_container, sampler= sampler)

    def select_planner_type(self, si) -> Any:
        L, W, H = self.agent_container.length, self.agent_container.width, self.agent_container.height
        if L is None or W is None or H is None or L <= 0 or W <= 0 or H <= 0:
            raise ValueError("Dimensions L, W, H must be provided for FRODO collision checking and must be v")
                             
        try:
                self.planner_type = self.mp_container.planner
                if self.planner_type == "rrt": # car and arm
                    return og.RRT(si) # type: ignore[attr-defined]
                elif self.planner_type == "rrt*":
                    return og.RRTStar(si) # type: ignore[attr-defined]
                elif self.planner_type == "rrt-connect": # car and arm
                    return og.RRTConnect(si) # type: ignore[attr-defined]
                elif self.planner_type == "sst": # Only car case
                    return og.SST(si) # type: ignore[attr-defined]
                else:
                    raise ValueError(f"Unsupported planner type the motion problem: {self.planner_type}")

        except KeyError:
            print("No planner type specified, using default RRT")
            return og.RRT(si) # type: ignore[attr-defined]
    
    # def _create_space(self):

    #     space = ob.SE2StateSpace() # type: ignore[attr-defined]
    #     # only for the car, we need the bounds since SE2 is already bounded 0,2pi
    #     bounds = ob.RealVectorBounds(2) # type: ignore[attr-defined]
    #     for i in range(2):
    #         bounds.setLow(i, 0.0)
    #         bounds.setHigh(i, 2*np.pi)  # Assuming angles in radians, adjust as necessary
    #     space.setBounds(bounds)
    #     # space = ob.CompoundStateSpace() # type: ignore[attr-defined]

    #     # for link in self.mp["L"]:
    #     #     space.addSubspace(ob.SO2StateSpace(), 1)  # One rotation per link # type: ignore[attr-defined]

    #     return space
    
    def _create_space_info(self) -> ob.SpaceInformation: # type: ignore[attr-defined]
        # Space information for (collision checking, interpolation, etc.)
        si = ob.SpaceInformation(self._space) # type: ignore[attr-defined]
        # set state validity checking for this space
        si.setStateValidityChecker(ob.StateValidityCheckerFn(self._collision_checker.check_state_ompl)) # type: ignore[attr-defined]
        # set the state sampler for this space
        sampler = self._get_state_sampler(si)
        si.setValidStateSamplerAllocator(ob.ValidStateSamplerAllocator(self.sampler)) # type: ignore[attr-defined]

        return si
    
    # def _extract_ompl_state(self, ompl_state) -> list:
    #     # Extract joint angles from flat RealVectorStateSpace
    #     return [float(ompl_state[i]) for i in range(len(self.mp["L"]))]
    
    def _create_solution_dict(self)-> dict:
        path_states = self._solution_path_states
        solution_dict = {
            "plan": {
                "states": path_states
            }
        }
        return solution_dict
    
    def solve_problem(self, verbose = False) -> tuple[bool, float]:

        self.check_pdef_validity()
        self._solution_path = None

        solved = self._planner.solve(self.mp_container.timelimit)
        exact = self._pdef.hasExactSolution() # type: ignore[attr-defined]
        approx = self._pdef.hasApproximateSolution() # type: ignore[attr-defined]

        if verbose:
            print(f"Solved: {solved}, Exact: {exact}, Approx: {approx}")

        if solved:
            self._solution_path = self._pdef.getSolutionPath()

            print('this is the solution path! ', self._solution_path_states)
            print(len(self._solution_path_states))
            start_config,  = self._solution_path_states
            raise NotImplementedError
            path_length = self._solution_path.length()
            return True, path_length
            # Print a concise summary instead of the full path details
            # num_states = self._solution_path.getStateCount()  # type: ignore[attr-defined]
            # path_length = self._solution_path.length()       # type: ignore[attr-defined]
            # print(f"Found solution with {num_states} states, total length {path_length:.3f}") # TODO: Put this into logger
        
        return False, 0
    

if __name__ == "__main__":
    ...

