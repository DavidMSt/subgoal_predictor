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

from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.motion_planning.helper.ompl_planner import OMPLPlannerFRODOKino, OMPLPlannerFRODOGeo, OMPLPlannerFRODOBase
from master_thesis.general.general_agents import InputPhaseRunner, InputPhase
from master_thesis.containers.mp_container import AgentMPConfig, AgentMPContainer
from master_thesis.containers.task_container import TaskContainer
from master_thesis.containers.base_container import BaseContainer

# TODO: Apply offset bidirectional from ompl to simulation and from simulation back (initialization of start config)

class MPAgentModule():
    env_config: EnvironmentContainer
    agent_cont: FRODOAgentContainer

    def __init__(self,agent_cont: FRODOAgentContainer, env_container: EnvironmentContainer, runner: InputPhaseRunner, logger: Logger, mp_type: Type[OMPLPlannerFRODOBase] = OMPLPlannerFRODOKino) -> None:
        self.agent_cont = agent_cont
        self.env_config = env_container
        self.runner = runner
        self.logger = logger
        self.mp_type = mp_type
        self.motion_planner = None
        self.mp_container = self.setup_mp_container()

    def plan_motion(self, phase_key: str, goal_task: TaskContainer| None, start_task: TaskContainer | None = None):
        def extract_config_from_cont(container: BaseContainer):
            state = [container.x, container.y, container.psi]
            return state

        if self.runner is None:
            self.logger.warning("Runner not initialized, Solution is not added as executable phase")

        if self.motion_planner is None:
            self.motion_planner = self.setup_motion_planner()
        
        # if no start specified use the current agent config
        if start_task == None:
            # use current agent state as start config
            agent_state = extract_config_from_cont(self.agent_cont)
            start_config = np.ndarray(agent_state)

        # if start specified, e.g. to predict path between two tasks
        else: 
            task_state = extract_config_from_cont(start_task)
            start_config = np.ndarray(task_state)

        assert isinstance(goal_task, TaskContainer)
        goal_config = np.ndarray(extract_config_from_cont(goal_task))
        
        # update the mp container
        self.mp_container.start = start_config
        self.mp_container.goal = goal_config

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

    def setup_mp_container(self):
        config = AgentMPConfig() # TODO: Offer choice to make more adjustments when calling the function
        mp_container = AgentMPContainer(config = config)
        return mp_container

    def setup_motion_planner(self):
        # TODO: initialize the planner once, but still be able to dynamically handle obstacles in the environment to enable obstacle creation after agent creation
        motion_planner = self.mp_type(mp_container=self.mp_container, agent_container= self.agent_cont, env_container= self.env_config)
        return motion_planner

class FRODO_MotionPlanning_Agent(FRODOGeneralAgent):
    mpi: MPAgentModule
 
    def __init__(self, env_container: EnvironmentContainer, agent_id: str, Ts=None, start_config=(0,0,0), *args, **kwargs):
        super().__init__(agent_id=agent_id, Ts=Ts, start_config=start_config, *args, **kwargs)

        # MPAgent module
        self.mpi = MPAgentModule(
            agent_cont=self.container,   # now built by general agent itself
            env_container=env_container,            # MUST match new env container
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
        env_container=sim.environment.environment_container, 
        agent_id='frodo1_v', 
        Ts=0.1,
        start_config=start_config
    )
    sim.add_agent(agent)
    agent.mpi.plan_motion(phase_key='test_phase', start_config=start_config, goal_config=goal_config)
    
    agent.runner.activate_phase('test_phase')

    sleep(3)
    print(agent._configuration)
