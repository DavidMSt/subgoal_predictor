import abc
from dataclasses import dataclass, field, replace
from time import sleep
import math
import threading
import time
import numpy as np
from typing import Type, cast, List, Callable
import logging

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_ENVIRONMENT_ACTIONS
import extensions.simulation.src.core as core
from core.utils.logging_utils import Logger
from applications.FRODO.simulation.frodo_simulation import FrodoEnvironment

from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_General_Config
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.motion_planning.helper.ompl_planner import OMPLPlannerFRODOKino, OMPLPlannerBase
from master_thesis.general.general_agents import InputPhaseRunner, InputPhase

# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)


@dataclass(frozen = True)
class MotionPlanningConfig:
    # timestep duration
    dt: float

    # physical dimensions
    L: float
    W: float
    H: float

    # start/ goal configurations
    start: np.ndarray
    goal: np.ndarray | None

    # samplingn boundaries
    # env_min: np.ndarray
    # env_max: np.ndarray
    env_limits: List[List[float]]
    obstacles: list

    type: str = "frodo"

    # hyperparameters
    # planner type selected
    planner: str = 'rrt'
    # timelimit for each motion planning problem
    timelimit: float = 60.0
    # bias for goal sampling
    goal_bias: float = 0.1
    # size of the goal region
    goal_eps: float = 0.1
    # weight of so2 relative to r2 in distance metric
    so_r2_weight: float = 1.0

    # control bounds
    theta_dot_bounds: tuple = (-np.pi/3, np.pi/3)
    v_bounds: tuple = (-1.0, 1.0)

class MPAgentModule():
    dt: float  | None # delta_t timestep used during sampling
    env: FrodoGeneralEnvironment
    id: str # mainly used for optional plotting of start/ goal configurations in the GUi

    # physical dimensions for all FRODOs # TODO: Use the general agent config to extract this in the future
    # length: float = 0.157
    # width: float = 0.115
    # height: float = 0.052  

    def __init__(self,robot_config, env: FrodoGeneralEnvironment, runner: InputPhaseRunner, id: str, logger: Logger, plotting_group = None) -> None:
        self.env = env
        self.runner = runner
        self.id = id
        self.plotting_group = plotting_group
        self.logger = logger
        self.length = robot_config.length
        self.width = robot_config.width
        self.heigth = robot_config.height


        # runner: "PhaseRunner | None" = None
        # algorithm: str = 'kinodynamic_rrt'
        # motion_planner: OMPLPlannerBase| None = None

    def plot_goal_config(self, goal_config: np.ndarray):
        """Plots a given goal config inside the GUI

        Args:
            goal_config (np.ndarray): _description_
        """
        # self.goal_config = goal_config
        if self.plotting_group: #TODO: Move this again to the simulation, since it will decide which agent to assign which goal? 
            self.plotting_group.add_point(
                id=f"goal_{self.id}",
                x=goal_config[0],
                y=goal_config[1],
                color=[0, 1, 0],  
                size=0.7         
            )

    def plan_motion(self, phase_key: str, start_config, goal_config, motion_planner = OMPLPlannerFRODOKino):
        if self.runner is None:
            self.logger.warning("Runner not initialized, Solution is not added as executable phase")

        if isinstance(motion_planner, str):
            raise NotImplementedError
        self.motion_planner = motion_planner(self.export_config(start_config, goal_config))# TODO: initialize the planner once, but still be able to dynamically handle obstacles in the environment to enable obstacle creation after agent creation
        solved, path_length = self.motion_planner.solve_problem()

        if solved:
            solution_dict = self.motion_planner.export_solution_dict()
            phase = InputPhase(
                inputs=solution_dict["actions"],
                states=solution_dict["states"],
                durations=solution_dict["durations"],
                delta_t=float(solution_dict["delta_t"]),
            )

            
            self.runner.add_phase(phase_key, phase)


            self.logger.info(
                f"Found solution with {len(phase.states)} states, "
                f"total length {path_length}, end config: {phase.states[-1]}"
            )
        else:
            self.logger.warning(f"No solution found! timeout after {self.export_config().timelimit} s")
    
    def export_config(self, start_config, goal_config) -> MotionPlanningConfig:
        # if self.env is None:
        #     error_message = "The Motion Planning Interface needs the environment instance used in the simulation to plan a path! Provide during initializaion or use bin_environment method."

        #     if self.logger is not None:
        #         self.logger.error(error_message)
        #     else:
        #         raise AttributeError(error_message)

        return MotionPlanningConfig(
            dt=self.env.Ts,
            L=self.length,
            W=self.width,
            H=self.heigth,
            start=start_config,
            goal=goal_config,
            env_limits = self.env.limits,
            obstacles=self.env.obstacles
        )

class FRODO_MotionPlanning_Agent(FRODOGeneralAgent):
    mp_interface: MPAgentModule
 
    def __init__(self, env, agent_id: str, Ts=None, config: FRODO_General_Config | None = None, start_config=[0,0,0], *args, **kwargs) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, agent_config=config, start_config=start_config, *args, **kwargs)

        # motion_planning interface for OMPL configuration
        self.mpi = MPAgentModule(
            robot_config= self.agent_config,
            env=env,
            id=self.agent_id,
            runner=self.runner,
            plotting_group=None,
            logger=self.logger
        )


if __name__ == '__main__':
    sim = FRODO_general_Simulation(Ts=0.1, env=FrodoGeneralEnvironment)
    sim.init()
    sim.start()
    start_config = [0.0, 0.0, 0.0]
    goal_config = [1.0, 1.0, np.pi]
    agent = FRODO_MotionPlanning_Agent(
        env=sim.environment, 
        agent_id='frodo1_v', 
        Ts=0.1,
        start_config=start_config
    )
    sim.add_agent(agent)
    agent.mpi.plan_motion(phase_key='test_phase', start_config=start_config, goal_config=goal_config)
    
    agent.runner.activate_phase('test_phase')

    sleep(3)
    print(agent._configuration)
