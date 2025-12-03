from dataclasses import dataclass, field, replace
import time
import numpy as np
from typing import Type, cast, overload
from logging import Logger

# bilbolab
import extensions.simulation.src.core as core

from master_thesis.motion_planning.mp_agent import FRODO_MotionPlanning_Agent
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.motion_planning.mp_agent import FRODO_MotionPlanning_Agent, MPAgentModule
from master_thesis.motion_planning.helper.ompl_planner import OMPLPlannerFRODOKino, OMPLPlannerFRODOGeo
from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.general.general_obstacles import GeneralObstacle

class MPSimulationModule():
    agents: dict[str, FRODOGeneralAgent]
    logger: Logger

    def __init__(self, agents: dict[str, FRODOGeneralAgent], logger: Logger) -> None:
        self.agents = agents
        self.logger = logger

    def agent_motion_planning(self, agent: str | FRODOGeneralAgent, 
                              solution_phase_name: str, *, goal_config: tuple[float, ...], 
                              start_config: tuple[float, ...] | None = None, motion_planner = OMPLPlannerFRODOKino): # TODO: specify planner on this level already
        if isinstance(agent, str):
            agent = self.agents[agent]
        
        mpi = getattr(agent, 'mpi', None)
        if mpi is not None and isinstance(mpi, MPAgentModule):
            mpi.plan_motion(phase_key=solution_phase_name, start_config=start_config, goal_config=goal_config, motion_planner= motion_planner)
        else:
            if hasattr(agent, 'agent_id'):
                self.logger.error(f'Tried to plan motion for agent: {agent.agent_id}, no Motion planning interface present')
            else:
                self.logger.error(f'Tried to plan motion for agent, no Motion planning interface present')

    # def multiple_agents_motion_planning(self, goal_configs: list, start_configs: list |None = None):
    #     raise NotImplementedError
    #     agents = self.agents

    #     for agent in agents.values():
    #         if start_configs == None:
    #             start_config = agent.configuration

class FRODO_MP_Simulation(FRODO_general_Simulation):
    def __init__(self, Ts=0.05, env=FrodoGeneralEnvironment, limits: tuple[tuple[int, int], ...] = ((-3,3),(-3,3)), *args, **kwargs):
        super().__init__(Ts=Ts, env=env, limits=limits, *args, **kwargs)
        self.mpi = MPSimulationModule(agents=self.agents, logger=self.logger)  # type: ignore


def mp_task_2ag_0obs():
    sim = FRODO_MP_Simulation()
    sim.init()

    # define start and goal
    ag1_start = (2.0, 0.0, np.pi)
    ag1_goal = (-1.0, 0.0, np.pi)
    ag2_start = (2, 0, np.pi)
    ag2_goal = (3.0, 0, 0)


    ag1 = FRODO_MotionPlanning_Agent(
        env_container=sim.environment.environment_container,
        agent_id="frodo1_v",
        Ts=sim.Ts,
        start_config=ag1_start
    )
    sim.add_agent(ag1)
    sim.mpi.agent_motion_planning(ag1, solution_phase_name="goal", start_config=ag1_start, goal_config= ag1_goal)

    ag2 = FRODO_MotionPlanning_Agent(
        env_container=sim.environment.environment_container,
        agent_id="frodo2_v",
        Ts=sim.Ts,
        start_config=ag2_start
    )
    sim.add_agent(ag2)
    sim.mpi.agent_motion_planning(ag2, solution_phase_name="goal", start_config=tuple(ag2_start), goal_config=tuple(ag2_goal))

    sim.start()

    sim.activate_phase_all_agents(phase="goal")

    while True:
        time.sleep(1)

def mp_task_1ag_1obs():
    sim = FRODO_MP_Simulation()
    sim.init()

    # define start and goal
    ag1_start = (0.0, 0.0, np.pi)
    ag1_goal = (4.0, 0.0, np.pi)



    ag1 = FRODO_MotionPlanning_Agent(
        env_container=sim.environment.environment_container,
        agent_id="frodo1_v",
        Ts=sim.Ts,
        start_config=ag1_start
    )

    obs1 = GeneralObstacle(
        obstacle_id= 'obs1',
        x = 2,
        y= 0, 
        psi = 0.0,
        length=1,
        width= 1,
        height=1,
    )

    # add agent and obstacle
    sim.add_agent(ag1)
    sim.add_obstacle(obs1)

    sim.mpi.agent_motion_planning(ag1, solution_phase_name="goal", start_config=ag1_start, goal_config= ag1_goal)

    sim.start()

    sim.activate_phase_all_agents(phase="goal")

    while True:
        time.sleep(1)
    

if __name__ == '__main__':
    # mp_task_2ag_0obs()
    mp_task_1ag_1obs()