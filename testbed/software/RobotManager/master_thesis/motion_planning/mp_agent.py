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

from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config
from master_thesis.general.configuration_containers import EnvironmentConfig
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.motion_planning.helper.ompl_planner import OMPLPlannerFRODOKino, OMPLPlannerFRODOGeo, OMPLPlannerFRODOBase
from master_thesis.general.general_agents import InputPhaseRunner, InputPhase
from master_thesis.general.configuration_containers import MotionPlanningConfig

# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)

class MPAgentModule():
    env_config: EnvironmentConfig
    agent_config: FRODO_Agent_Config

    def __init__(self,agent_config: FRODO_Agent_Config, env_config: EnvironmentConfig, runner: InputPhaseRunner, logger: Logger) -> None:
        self.agent_config = agent_config
        self.env_config = env_config
        self.runner = runner
        self.logger = logger

    def plan_motion(self, phase_key: str, start_config, goal_config, motion_planner: Type[OMPLPlannerFRODOBase] = OMPLPlannerFRODOKino):
        if self.runner is None:
            self.logger.warning("Runner not initialized, Solution is not added as executable phase")

        if isinstance(motion_planner, str):
            raise NotImplementedError
        
        mp_config = MotionPlanningConfig(
            start=start_config,
            goal=goal_config,
        )

        self.motion_planner = motion_planner(mp_config=mp_config, agent_config= self.agent_config, env= self.env_config)# TODO: initialize the planner once, but still be able to dynamically handle obstacles in the environment to enable obstacle creation after agent creation
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
            self.logger.warning(f"No solution found! timeout reached")

class FRODO_MotionPlanning_Agent(FRODOGeneralAgent):
    mpi: MPAgentModule
 
    def __init__(self, env_config, agent_id: str, Ts=None, agent_config: FRODO_Agent_Config | None = None, start_config=(0.0,0.0,0.0), *args, **kwargs) -> None:
        super().__init__(agent_id=agent_id, Ts=Ts, agent_config=agent_config, start_config=start_config, *args, **kwargs)

        # motion_planning interface for OMPL configuration
        self.mpi = MPAgentModule(
            agent_config= self.agent_config,
            env_config=env_config,
            runner=self.runner,
            logger=self.logger
        )


if __name__ == '__main__':
    sim = FRODO_general_Simulation(Ts=0.1, env=FrodoGeneralEnvironment)
    sim.init()
    sim.start()
    start_config = [0.0, 0.0, 0.0]
    goal_config = [1.0, 1.0, np.pi]
    agent = FRODO_MotionPlanning_Agent(
        env_config=sim.environment.environment_configuration, 
        agent_id='frodo1_v', 
        Ts=0.1,
        start_config=start_config
    )
    sim.add_agent(agent)
    agent.mpi.plan_motion(phase_key='test_phase', start_config=start_config, goal_config=goal_config)
    
    agent.runner.activate_phase('test_phase')

    sleep(3)
    print(agent._configuration)
